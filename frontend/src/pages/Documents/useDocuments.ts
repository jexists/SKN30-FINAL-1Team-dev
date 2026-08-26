import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type {
  CustomerCompanyResponse,
  DocumentCategory,
  DocumentResponse,
  DocumentSummaryResponse,
  DocumentVersion,
  OrderResponse,
  PageResponse,
  SalesDealResponse,
  SalesDocument,
} from '@/types'

import { kindOfFile } from './catalog'

const PAGE_LIMIT = 100
const CATEGORY_CODE: Record<DocumentCategory, string> = {
  계약서: 'contract',
  발주서: 'purchase_order',
  상품설명서: 'product_brochure',
  견적서: 'quote',
  기타: 'other',
}
const CATEGORY_BY_CODE = Object.fromEntries(
  Object.entries(CATEGORY_CODE).map(([label, code]) => [code, label]),
) as Record<string, DocumentCategory>

export type DocumentMeta = Pick<
  SalesDocument,
  'title' | 'category' | 'link' | 'description' | 'tags'
>

export interface DocumentDraft extends DocumentMeta {
  file: File
  owner: string
  note: string
}

function versionOf(documentId: string, file: DocumentResponse['files'][number]): DocumentVersion {
  return {
    id: file.id,
    documentId,
    version: file.version_no,
    fileName: file.file_name,
    bytes: file.byte_size,
    owner: file.uploaded_by_display_name,
    uploaded: file.uploaded_at.slice(0, 10),
    note: file.note ?? '',
    processingStatus: file.processing_status,
    processingError: file.processing_error,
  }
}

function toDocument(item: DocumentResponse): SalesDocument {
  const versions = [...item.files]
    .sort((a, b) => a.version_no - b.version_no)
    .map((file) => versionOf(item.id, file))
  const latest = versions.at(-1)
  return {
    id: item.id,
    documentNo: item.document_no,
    title: item.title,
    category: CATEGORY_BY_CODE[item.category_code] ?? '기타',
    kind: kindOfFile({ name: latest?.fileName ?? '' }),
    link: item.customer_company_id
      ? { kind: '고객사', label: item.customer_company_name ?? item.customer_company_id }
      : item.purchase_order_id
        ? { kind: '발주', label: item.purchase_order_id }
        : item.sales_deal_id
          ? { kind: '계약', label: item.sales_deal_id }
          : { kind: 'none', label: '' },
    description: item.description ?? '',
    tags: item.tags,
    versions:
      versions.length > 0
        ? versions
        : [
            {
              documentId: item.id,
              version: 0,
              fileName: '파일 없음',
              bytes: 0,
              owner: item.created_by_display_name,
              uploaded: item.created_at.slice(0, 10),
              note: '',
            },
          ],
  }
}

async function fetchAll<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const result: T[] = []
  let skip = 0
  while (!signal?.aborted) {
    const { data } = await client.get<PageResponse<T>>(path, {
      params: { skip, limit: PAGE_LIMIT },
      signal,
    })
    result.push(...data.items)
    if (!data.has_more || data.next_skip === null) return result
    if (data.next_skip <= skip) throw new Error('invalid_pagination')
    skip = data.next_skip
  }
  return result
}

async function resolveLink(link: SalesDocument['link']) {
  const empty = {
    customer_company_id: null,
    sales_deal_id: null,
    purchase_order_id: null,
  }
  if (link.kind === 'none' || link.label.trim() === '') return empty

  const q = link.label.trim()
  if (link.kind === '고객사') {
    const { data } = await client.get<PageResponse<CustomerCompanyResponse>>(
      '/customer-companies',
      {
        params: { q, skip: 0, limit: PAGE_LIMIT },
      },
    )
    const found = data.items.find((item) => item.id === q || item.name === q)
    if (!found) throw new Error('연결할 고객사를 찾을 수 없습니다.')
    return { ...empty, customer_company_id: found.id }
  }
  if (link.kind === '계약') {
    const { data } = await client.get<PageResponse<SalesDealResponse>>('/sales-deals', {
      params: { q, phase_code: 'contract', skip: 0, limit: PAGE_LIMIT },
    })
    const found = data.items.find((item) => item.id === q || item.deal_no === q)
    if (!found) throw new Error('연결할 계약 딜을 찾을 수 없습니다.')
    return { ...empty, sales_deal_id: found.id }
  }

  const { data } = await client.get<PageResponse<OrderResponse>>('/orders', {
    params: { q, skip: 0, limit: PAGE_LIMIT },
  })
  const found = data.items.find((item) => item.id === q || item.order_no === q)
  if (!found) throw new Error('연결할 발주를 찾을 수 없습니다.')
  return { ...empty, purchase_order_id: found.id }
}

async function uploadFile(documentId: string, file: File, note: string) {
  const form = new FormData()
  form.append('upload', file)
  if (note) form.append('note', note)
  await client.post(`/documents/${documentId}/files`, form)
}

function mutationMessage(reason: unknown, fallback: string): string {
  if (reason instanceof Error && reason.message.endsWith('찾을 수 없습니다.')) return reason.message
  return errorMessage(reason, fallback)
}

export default function useDocuments() {
  const [documents, setDocuments] = useState<SalesDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void fetchAll<DocumentResponse>('/documents', controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setDocuments(items.map(toDocument))
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setDocuments([])
          setError(errorMessage(reason, '자료 목록을 불러오지 못했습니다.'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [reloadKey])

  const findDocument = useCallback(
    (id: string) => documents.find((document) => document.id === id),
    [documents],
  )

  const addDocument = useCallback(async (draft: DocumentDraft) => {
    setPending(true)
    setError(null)
    try {
      const links = await resolveLink(draft.link)
      const { data: created } = await client.post<DocumentResponse>('/documents', {
        category_code: CATEGORY_CODE[draft.category],
        title: draft.title,
        description: draft.description || null,
        ...links,
        tags: draft.tags,
      })
      await uploadFile(created.id, draft.file, draft.note)
      const { data } = await client.get<DocumentResponse>(`/documents/${created.id}`)
      setDocuments((current) => [toDocument(data), ...current])
      return data.id
    } catch (reason: unknown) {
      setError(mutationMessage(reason, '자료를 등록하지 못했습니다.'))
      throw reason
    } finally {
      setPending(false)
    }
  }, [])

  const addVersion = useCallback(async (id: string, file: File, _owner: string, note: string) => {
    setPending(true)
    setError(null)
    try {
      await uploadFile(id, file, note)
      const { data } = await client.get<DocumentResponse>(`/documents/${id}`)
      const updated = toDocument(data)
      setDocuments((current) =>
        current.map((document) => (document.id === id ? updated : document)),
      )
    } catch (reason: unknown) {
      setError(mutationMessage(reason, '새 버전을 등록하지 못했습니다.'))
      throw reason
    } finally {
      setPending(false)
    }
  }, [])

  const updateDocument = useCallback(
    async (id: string, meta: Partial<DocumentMeta>) => {
      setPending(true)
      setError(null)
      try {
        const current = documents.find((document) => document.id === id)
        if (!current) throw new Error('자료를 찾을 수 없습니다.')
        const next = { ...current, ...meta }
        const links = await resolveLink(next.link)
        const { data } = await client.patch<DocumentResponse>(`/documents/${id}`, {
          category_code: CATEGORY_CODE[next.category],
          title: next.title,
          description: next.description || null,
          ...links,
          tags: next.tags,
        })
        const updated = toDocument(data)
        setDocuments((items) => items.map((document) => (document.id === id ? updated : document)))
      } catch (reason: unknown) {
        setError(mutationMessage(reason, '자료 정보를 수정하지 못했습니다.'))
        throw reason
      } finally {
        setPending(false)
      }
    },
    [documents],
  )

  const summarizeVersion = useCallback(
    async (documentId: string, fileId: string): Promise<DocumentSummaryResponse> => {
      await client.post(`/documents/${documentId}/files/${fileId}/process`)
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const { data } = await client.get<DocumentSummaryResponse>(
          `/documents/${documentId}/files/${fileId}/summary`,
        )
        if (data.processing_status !== 'processing') return data
        await new Promise((resolve) => window.setTimeout(resolve, 1000))
      }
      return client
        .get<DocumentSummaryResponse>(`/documents/${documentId}/files/${fileId}/summary`)
        .then(({ data }) => data)
    },
    [],
  )

  return {
    documents,
    findDocument,
    loading,
    error,
    pending,
    reload: () => setReloadKey((value) => value + 1),
    addDocument,
    addVersion,
    updateDocument,
    summarizeVersion,
  }
}

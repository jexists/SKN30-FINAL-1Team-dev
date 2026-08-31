import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type {
  DocumentCategory,
  DocumentFileResponse,
  DocumentResponse,
  DocumentSummaryResponse,
  DocumentVersion,
  TabbedPageResponse,
  SalesDocument,
} from '@/types'

import { kindOfFile } from './catalog'
import { pollSummary } from './summaryPolling'

// 공통 API 제한(10초)보다 길게 잡습니다. 이 요청은 실제 OCR·요약을 기다리지 않고
// 백그라운드 작업을 시작하므로, 느린 DB 응답만 흡수한 뒤 아래 폴링으로 상태를 확인합니다.
const SUMMARY_START_TIMEOUT_MS = 30_000

/** 등록자 고르는 칸에 세울 사람. 최신 버전을 올린 사람 기준입니다. */
export interface DocumentUploader {
  id: string
  name: string
}

interface DocumentPageResponse extends TabbedPageResponse<DocumentResponse> {
  uploaders: { member_id: string; display_name: string }[]
}
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

export type DocumentMeta = Pick<SalesDocument, 'title' | 'category' | 'link' | 'description'>

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
    link: item.product_id
      ? { kind: '상품', id: item.product_id, label: item.product_name ?? item.product_id }
      : item.sales_deal_id
        ? { kind: '딜', id: item.sales_deal_id, label: item.sales_deal_no ?? item.sales_deal_id }
        : item.customer_company_id
          ? {
              kind: '고객사',
              id: item.customer_company_id,
              label: item.customer_company_name ?? item.customer_company_id,
            }
          : item.purchase_order_id
            ? { kind: '발주', id: item.purchase_order_id, label: item.purchase_order_id }
            : { kind: 'none', id: '', label: '' },
    description: item.description ?? '',
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

/**
 * 고른 연결 대상을 저장할 칸으로 폅니다.
 *
 * 예전에는 사용자가 친 글자를 검색해 그 결과에서 정확히 맞는 것을 골라 냈습니다. q 는
 * 부분 일치라, 같은 글자가 들어간 후보가 한 쪽을 넘으면 있는데도 못 찾았습니다. 이제는
 * 고르는 순간 id 를 들고 오므로 되물을 것이 없습니다.
 */
function linkFields(link: SalesDocument['link']) {
  const empty = {
    customer_company_id: null as string | null,
    sales_deal_id: null as string | null,
    purchase_order_id: null as string | null,
    product_id: null as string | null,
  }
  if (link.kind === 'none' || link.id === '') return empty
  if (link.kind === '상품') return { ...empty, product_id: link.id }
  if (link.kind === '딜') return { ...empty, sales_deal_id: link.id }
  // 고객사와 발주는 새로 고를 수 없지만, 예전 자료를 수정할 때 연결이 날아가면 안 됩니다.
  if (link.kind === '고객사') return { ...empty, customer_company_id: link.id }
  return { ...empty, purchase_order_id: link.id }
}

async function uploadFile(
  documentId: string,
  file: File,
  note: string,
): Promise<DocumentFileResponse> {
  const form = new FormData()
  form.append('upload', file)
  if (note) form.append('note', note)
  const { data } = await client.post<DocumentFileResponse>(`/documents/${documentId}/files`, form)
  return data
}

function mutationMessage(reason: unknown, fallback: string): string {
  if (reason instanceof Error && reason.message.endsWith('찾을 수 없습니다.')) return reason.message
  return errorMessage(reason, fallback)
}

export interface DocumentQuery {
  q: string
  /** 고른 분류 탭. 빈 문자열이면 전체입니다. */
  category: DocumentCategory | ''
  /** 최신 버전을 올린 사람. 빈 문자열이면 전체입니다. */
  uploaderMemberId: string
  /** 최신 버전을 올린 날짜의 하한. null 이면 제한 없음입니다. */
  fromISO: string | null
  skip: number
  limit: number
}

export default function useDocuments(query?: DocumentQuery) {
  const [documents, setDocuments] = useState<SalesDocument[]>([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [uploaders, setUploaders] = useState<DocumentUploader[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  // 조회 조건을 낱개로 펼쳐 둡니다. 효과가 객체가 아니라 값 하나하나를 보게 해야, 화면이
  // 조건 객체를 새로 만들 때마다 다시 받지 않습니다.
  const {
    q: queryText = '',
    category: queryCategory = '',
    uploaderMemberId: queryUploader = '',
    fromISO: queryFrom = null,
    skip: querySkip = 0,
    limit: queryLimit = 30,
  } = query ?? {}

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    const needle = queryText.trim()
    void client
      .get<DocumentPageResponse>('/documents', {
        params: {
          q: needle === '' ? undefined : needle.slice(0, 100),
          category_code: queryCategory === '' ? undefined : CATEGORY_CODE[queryCategory],
          latest_uploader_member_id: queryUploader === '' ? undefined : queryUploader,
          latest_uploaded_from: queryFrom === null ? undefined : `${queryFrom}T00:00:00+09:00`,
          skip: querySkip,
          limit: queryLimit,
        },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setDocuments(data.items.map(toDocument))
        setTotal(data.total)
        setCounts(data.counts)
        setUploaders(
          data.uploaders.map(({ member_id, display_name }) => ({
            id: member_id,
            name: display_name,
          })),
        )
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
  }, [reloadKey, queryText, queryCategory, queryUploader, queryFrom, querySkip, queryLimit])

  const findDocument = useCallback(
    (id: string) => documents.find((document) => document.id === id),
    [documents],
  )

  const addDocument = useCallback(async (draft: DocumentDraft) => {
    setPending(true)
    setError(null)
    try {
      const links = linkFields(draft.link)
      const { data: created } = await client.post<DocumentResponse>('/documents', {
        category_code: CATEGORY_CODE[draft.category],
        title: draft.title,
        description: draft.description || null,
        ...links,
      })
      const uploaded = await uploadFile(created.id, draft.file, draft.note)
      const { data } = await client.get<DocumentResponse>(`/documents/${created.id}`)
      setDocuments((current) => [toDocument(data), ...current])
      return { document: data, fileId: uploaded.id }
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
      const uploaded = await uploadFile(id, file, note)
      const { data } = await client.get<DocumentResponse>(`/documents/${id}`)
      const updated = toDocument(data)
      setDocuments((current) =>
        current.map((document) => (document.id === id ? updated : document)),
      )
      return { document: data, fileId: uploaded.id }
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
        const links = linkFields(next.link)
        const { data } = await client.patch<DocumentResponse>(`/documents/${id}`, {
          category_code: CATEGORY_CODE[next.category],
          title: next.title,
          description: next.description || null,
          ...links,
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
      return pollSummary({
        start: async () => {
          await client.post(`/documents/${documentId}/files/${fileId}/process`, undefined, {
            timeout: SUMMARY_START_TIMEOUT_MS,
          })
        },
        read: async () => {
          const { data } = await client.get<DocumentSummaryResponse>(
            `/documents/${documentId}/files/${fileId}/summary`,
          )
          return data
        },
      })
    },
    [],
  )

  const queueSummaries = useCallback(
    async (files: { documentId: string; fileId: string }[]): Promise<void> => {
      if (files.length === 0) return
      try {
        await client.post('/documents/process-batch', {
          file_ids: files.map(({ fileId }) => fileId),
        })
      } catch (reason: unknown) {
        setError(errorMessage(reason, '문서 요약 작업을 서버에 등록하지 못했습니다.'))
        throw reason
      }
    },
    [],
  )

  const loadSummary = useCallback(
    async (documentId: string, fileId: string): Promise<DocumentSummaryResponse> => {
      const { data } = await client.get<DocumentSummaryResponse>(
        `/documents/${documentId}/files/${fileId}/summary`,
      )
      return data
    },
    [],
  )

  const approveSummary = useCallback(
    async (documentId: string, fileId: string): Promise<DocumentSummaryResponse> => {
      const { data } = await client.post<DocumentSummaryResponse>(
        `/documents/${documentId}/files/${fileId}/approve-summary`,
      )
      return data
    },
    [],
  )

  return {
    documents,
    total,
    counts,
    uploaders,
    findDocument,
    loading,
    error,
    pending,
    reload: () => setReloadKey((value) => value + 1),
    addDocument,
    addVersion,
    updateDocument,
    summarizeVersion,
    queueSummaries,
    loadSummary,
    approveSummary,
  }
}

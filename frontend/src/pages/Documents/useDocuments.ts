// 백엔드가 붙는 지점은 이 파일 하나입니다. 화면은 아래 반환값만 알면 되므로
// 시드를 API 응답으로, 각 mutator 를 요청으로 바꾸면 나머지는 그대로 둘 수 있습니다.
//
// 지금은 올린 파일을 File 객체로 메모리에만 들고 있습니다. 새로고침하면 사라지고
// 시드 문서에는 blob 이 없어 내려받을 수 없습니다. 스토리지가 붙으면 blob 자리에
// 내려받기 URL 이 들어옵니다.
//
// 상태를 모듈 수준에 두는 이유는 useOrderList 와 같습니다. 목록과 드로어가 서로 다른
// 훅 인스턴스를 쓰더라도 한 데이터를 봐야 합니다.
import { useCallback, useSyncExternalStore } from 'react'

import type { DocumentVersion, SalesDocument } from '@/types'
import { TODAY_ISO } from '@/utils/date'

import { initialDocuments, kindOfFile, latestOf, nextDocumentId } from './catalog'

let documents: SalesDocument[] = initialDocuments()
const listeners = new Set<() => void>()

function publish(next: SalesDocument[]) {
  documents = next
  listeners.forEach((notify) => notify())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** 문서 한 건의 메타. 파일과 별개로 사람이 채우는 값입니다. */
export type DocumentMeta = Pick<
  SalesDocument,
  'title' | 'category' | 'link' | 'description' | 'tags'
>

export interface DocumentDraft extends DocumentMeta {
  file: File
  owner: string
  /** 이 버전에서 무엇이 바뀌었는지. 첫 버전은 보통 비어 있습니다. */
  note: string
}

/** 올린 파일 하나를 버전 한 줄로. 등록일은 올린 날입니다. */
function toVersion(version: number, file: File, owner: string, note: string): DocumentVersion {
  return {
    version,
    fileName: file.name,
    bytes: file.size,
    owner,
    uploaded: TODAY_ISO,
    note,
    blob: file,
  }
}

export default function useDocuments() {
  const list = useSyncExternalStore(
    subscribe,
    () => documents,
    () => documents,
  )

  const findDocument = useCallback((id: string) => list.find((doc) => doc.id === id), [list])

  const addDocument = useCallback((draft: DocumentDraft) => {
    const { file, owner, note, ...meta } = draft
    const doc: SalesDocument = {
      ...meta,
      id: nextDocumentId(documents),
      // 파일 종류는 사람이 고르지 않고 올린 파일에서 뽑습니다.
      kind: kindOfFile(file),
      versions: [toVersion(1, file, owner, note)],
    }
    // 새로 올린 문서가 목록 아래로 묻히면 저장됐는지 알 수 없어 맨 위에 둡니다.
    publish([doc, ...documents])
    return doc.id
  }, [])

  /**
   * 같은 문서에 새 파일을 얹습니다. 이전 버전은 이력으로 남습니다.
   * 파일 종류는 늘 현재 버전을 가리켜야 하므로 새 파일에서 다시 뽑습니다.
   */
  const addVersion = useCallback((id: string, file: File, owner: string, note: string) => {
    publish(
      documents.map((doc) =>
        doc.id === id
          ? {
              ...doc,
              kind: kindOfFile(file),
              versions: [...doc.versions, toVersion(latestOf(doc).version + 1, file, owner, note)],
            }
          : doc,
      ),
    )
  }, [])

  /** 파일은 그대로 두고 메타만 고칩니다. */
  const updateDocument = useCallback((id: string, meta: Partial<DocumentMeta>) => {
    publish(documents.map((doc) => (doc.id === id ? { ...doc, ...meta } : doc)))
  }, [])

  const removeDocument = useCallback((id: string) => {
    publish(documents.filter((doc) => doc.id !== id))
  }, [])

  return { documents: list, findDocument, addDocument, addVersion, updateDocument, removeDocument }
}

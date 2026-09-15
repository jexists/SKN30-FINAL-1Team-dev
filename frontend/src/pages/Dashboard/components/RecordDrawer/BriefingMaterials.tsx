import { ChevronRightIcon, FileIcon } from '@/components/icons'
import type { BriefingDocument, BriefingDocuments } from '@/types/agenda'

import InfoHint from './InfoHint'
import styles from './RecordDrawer.module.scss'

interface Props {
  documents?: BriefingDocuments
  citedDocumentIds: Set<string>
  /** 요약과 원본을 옆 패널에 펴 달라고 알립니다. 여는 일은 드로어를 가진 쪽이 합니다. */
  onOpenSource: (document: BriefingDocument) => void
  /** 지금 받아 오는 중인 자료. 그 줄의 버튼만 멈춥니다. */
  openingDocumentId: string | null
  /** 마지막으로 열지 못한 자료와 사유. 그 줄 아래에만 한 줄로 답니다. */
  sourceError: { documentId: string; message: string } | null
}

export default function BriefingMaterials({
  documents,
  citedDocumentIds,
  onOpenSource,
  openingDocumentId,
  sourceError,
}: Props) {
  const row = (document: BriefingDocument) => {
    const opening = openingDocumentId === document.document_id
    const error = sourceError?.documentId === document.document_id ? sourceError.message : null
    return (
      <li key={document.document_id} className={styles.sourceItem}>
        {/* 줄 전체가 버튼입니다. 파일명이 곧 버튼 이름이라 무엇을 여는지가 그대로 읽힙니다. */}
        <button
          type="button"
          className={styles.sourceRow}
          disabled={opening}
          aria-busy={opening}
          onClick={() => onOpenSource(document)}
        >
          <FileIcon className={styles.sourceIcon} width={14} height={14} />
          <span className={styles.sourceName}>{document.file_name}</span>
          {opening && <span className={styles.sourceBusy}>여는 중…</span>}
          {citedDocumentIds.has(document.document_id) && (
            <i className={styles.citedTag}>브리핑에 인용됨</i>
          )}
          <ChevronRightIcon className={styles.sourceChevron} width={14} height={14} />
        </button>
        {/* 발췌와 요약은 옆 패널의 탭으로 옮겼습니다. 목록에는 열지 못한 사유만 답니다. */}
        {error && (
          <p className={`${styles.sourceDetail} ${styles.note}`} role="alert">
            {error}
          </p>
        )}
      </li>
    )
  }
  const search = documents?.search
  const searched = search && ['hybrid', 'keyword'].includes(search.method)
  const productDocs = documents?.product ?? []
  const relatedDocs = documents?.related ?? []
  // 검색이 제대로 돌았는데 걸린 자료가 없을 뿐이라면 알릴 것이 없습니다. "없습니다" 한
  // 줄을 세우는 대신 묶음을 통째로 접습니다. 반대로 검색이 실패했거나 이전 형식의
  // 브리핑이라면 왜 비었는지 말해야 하므로 그때는 묶음을 남깁니다.
  const relatedNotice =
    relatedDocs.length > 0
      ? null
      : search?.status === 'failed'
        ? '관련 자료 검색에 실패했습니다. 다음 갱신에서 다시 시도합니다.'
        : !documents || search?.status === 'legacy'
          ? '이전 브리핑입니다. 다음 갱신부터 참고 자료를 함께 준비합니다.'
          : null
  const showRelated = relatedDocs.length > 0 || !!relatedNotice
  if (!productDocs.length && !showRelated) return null
  return (
    <div aria-label="AI 브리핑 참고 자료">
      {productDocs.length > 0 && (
        <section className={styles.sources} aria-label="제품 자료">
          <h4 className={styles.sourcesTitle}>제품 자료</h4>
          <ul className={styles.sourceList}>{productDocs.map(row)}</ul>
        </section>
      )}
      {showRelated && (
        <section className={styles.sources} aria-label="관련 자료">
          <h4 className={styles.sourcesTitle}>
            관련 자료
            {searched && <span className={styles.ragTag}>RAG 검색</span>}
            {/* 어떻게 찾았는지는 목록이 있을 때만 의미가 있어 제목 옆에 접어 둡니다. */}
            {relatedDocs.length > 0 && search?.method === 'keyword' && (
              <InfoHint text="키워드로 관련 자료를 검색했습니다." />
            )}
          </h4>
          {relatedNotice ? (
            <p className={`${styles.note} ${styles.sourceNote}`}>{relatedNotice}</p>
          ) : (
            <ul className={styles.sourceList}>{relatedDocs.map(row)}</ul>
          )}
          {relatedDocs.length > 0 && search?.status === 'embedding_unavailable' && (
            <p className={`${styles.note} ${styles.sourceNote}`}>
              의미 검색을 사용할 수 없어 키워드 검색 결과를 표시합니다.
            </p>
          )}
        </section>
      )}
    </div>
  )
}

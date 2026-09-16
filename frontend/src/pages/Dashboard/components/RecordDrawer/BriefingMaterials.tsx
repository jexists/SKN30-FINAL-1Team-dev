// 브리핑 끝에 다는 출처. 어느 문단이 무엇을 썼는지는 문단 앞 링크가 이미 말했으므로,
// 여기서는 "이 브리핑이 본 자료 전부"를 중복 없이 작게 한 번만 셉니다.
import { FileIcon } from '@/components/icons'
import type { BriefingDocument, BriefingDocuments } from '@/types/agenda'

import InfoHint from './InfoHint'
import styles from './RecordDrawer.module.scss'

interface Props {
  documents?: BriefingDocuments
  /** 브리핑 문단이 실제로 인용한 자료. 목록에서 앞자리에 세울 때만 씁니다. */
  citedDocumentIds: Set<string>
  /** 요약과 원본을 옆 패널에 펴 달라고 알립니다. 여는 일은 드로어를 가진 쪽이 합니다. */
  onOpenSource: (document: BriefingDocument) => void
  /** 지금 받아 오는 중인 자료. 그 링크만 멈춥니다. */
  openingDocumentId: string | null
  /** 마지막으로 열지 못한 자료와 사유. 목록 아래에 한 줄로 답니다. */
  sourceError: { documentId: string; message: string } | null
}

/**
 * 제품 자료와 관련 자료를 한 줄로 합치고 같은 자료는 한 번만 남깁니다.
 *
 * 한 자료가 두 묶음에 모두 들어 있는 일이 흔합니다(딜 대표 제품이면서 검색에도 걸린 자료).
 * 묶음을 갈라 세우면 같은 파일 이름이 화면에 두 번 섭니다. 브리핑이 실제로 쓴 자료를 앞에
 * 두고, 나머지는 받은 순서를 지킵니다.
 */
function uniqueSources(documents: BriefingDocument[], cited: Set<string>) {
  const unique: BriefingDocument[] = []
  documents.forEach((document) => {
    if (!unique.some((item) => item.document_id === document.document_id)) unique.push(document)
  })
  return [
    ...unique.filter((document) => cited.has(document.document_id)),
    ...unique.filter((document) => !cited.has(document.document_id)),
  ]
}

function pageLabel(pageStart: number | null, pageEnd: number | null) {
  if (!pageStart) return null
  return pageEnd && pageEnd !== pageStart ? `${pageStart}–${pageEnd}페이지` : `${pageStart}페이지`
}

export default function BriefingMaterials({
  documents,
  citedDocumentIds,
  onOpenSource,
  openingDocumentId,
  sourceError,
}: Props) {
  const search = documents?.search
  const searched = search && ['hybrid', 'keyword'].includes(search.method)
  const relatedDocs = documents?.related ?? []
  const sources = uniqueSources([...(documents?.product ?? []), ...relatedDocs], citedDocumentIds)
  // 계약서 값이 계약관리와 다른 것은 출처 목록이 아니라 경고입니다. 목록을 한 줄로 줄이면
  // 파일 아래에 달 자리가 없어, 출처 위에 제 구획으로 세웁니다.
  const compared = sources.filter((document) => (document.contract_differences ?? []).length > 0)
  const failed = sourceError
    ? sources.find((document) => document.document_id === sourceError.documentId)
    : null
  // 검색이 제대로 돌았는데 걸린 자료가 없을 뿐이라면 알릴 것이 없습니다. "없습니다" 한
  // 줄을 세우는 대신 묶음을 통째로 접습니다. 반대로 검색이 실패했거나 이전 형식의
  // 브리핑이라면 왜 비었는지 말해야 하므로 그때는 묶음을 남깁니다.
  const notice =
    relatedDocs.length > 0
      ? null
      : search?.status === 'failed'
        ? '관련 자료 검색에 실패했습니다. 다음 갱신에서 다시 시도합니다.'
        : !documents || search?.status === 'legacy'
          ? '이전 브리핑입니다. 다음 갱신부터 참고 자료를 함께 준비합니다.'
          : null
  if (sources.length === 0 && !notice) return null

  const link = (document: BriefingDocument) => {
    const opening = openingDocumentId === document.document_id
    return (
      <button
        type="button"
        className={styles.sourceLink}
        disabled={opening}
        aria-busy={opening}
        title="원문 열기"
        onClick={() => onOpenSource(document)}
      >
        <FileIcon width={12} height={12} aria-hidden="true" />
        {document.file_name}
        {opening && <span className={styles.sourceBusy}>여는 중…</span>}
      </button>
    )
  }

  return (
    <div aria-label="AI 브리핑 참고 자료">
      {compared.length > 0 && (
        <section className={styles.sources} aria-label="계약서와 계약관리 값 비교">
          <h4 className={styles.sourcesTitle}>계약관리와 다른 값</h4>
          {compared.map((document) => (
            <div key={document.document_id} className={styles.sourceComparisons}>
              <p className={styles.sourceComparisonTitle}>{link(document)}</p>
              <dl>
                {(document.contract_differences ?? []).map((difference) => {
                  const page = pageLabel(difference.page_start, difference.page_end)
                  return (
                    <div key={`${difference.sales_deal_id}-${difference.field_code}`}>
                      <dt>{difference.field_label}</dt>
                      <dd>
                        <span>{difference.current_value ?? '미입력'}</span>
                        <b aria-hidden="true">→</b>
                        <strong>{difference.document_value}</strong>
                      </dd>
                      {page && <small>{page}</small>}
                    </div>
                  )
                })}
              </dl>
              <p className={styles.sourceComparisonHint}>파일을 열어 원문을 확인해 주세요.</p>
            </div>
          ))}
        </section>
      )}
      <section className={styles.sources} aria-label="브리핑 출처">
        <h4 className={styles.sourcesTitle}>
          출처
          {searched && <span className={styles.ragTag}>RAG 검색</span>}
          {/* 어떻게 찾았는지는 목록이 있을 때만 의미가 있어 제목 옆에 접어 둡니다. */}
          {relatedDocs.length > 0 && search?.method === 'keyword' && (
            <InfoHint text="키워드로 관련 자료를 검색했습니다." />
          )}
        </h4>
        {sources.length > 0 && (
          <ul className={styles.sourceLinks}>
            {sources.map((document) => (
              <li key={document.document_id}>{link(document)}</li>
            ))}
          </ul>
        )}
        {notice && <p className={`${styles.note} ${styles.sourceNote}`}>{notice}</p>}
        {sourceError && (
          <p className={`${styles.note} ${styles.sourceNote}`} role="alert">
            {failed ? `${failed.file_name}: ${sourceError.message}` : sourceError.message}
          </p>
        )}
        {relatedDocs.length > 0 && search?.status === 'embedding_unavailable' && (
          <p className={`${styles.note} ${styles.sourceNote}`}>
            의미 검색을 사용할 수 없어 키워드 검색 결과를 표시합니다.
          </p>
        )}
      </section>
    </div>
  )
}

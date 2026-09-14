import type { BriefingDocument, BriefingDocuments } from '@/types/agenda'
import { downloadFile } from '@/pages/Documents/download'
import styles from './RecordDrawer.module.scss'

interface Props {
  documents?: BriefingDocuments
  citedDocumentIds: Set<string>
  hasDeal: boolean
}

export default function BriefingMaterials({ documents, citedDocumentIds, hasDeal }: Props) {
  const row = (document: BriefingDocument) => (
    <li key={document.document_id}>
      <span className={styles.sourceName}>
        {document.file_name}
        <button
          type="button"
          onClick={() =>
            downloadFile({
              id: document.file_id,
              documentId: document.document_id,
              fileName: document.file_name,
              bytes: 0,
              owner: '',
              uploaded: '',
              note: '',
            })
          }
        >
          원문 보기
        </button>
        {citedDocumentIds.has(document.document_id) && (
          <i className={styles.citedTag}>브리핑에 인용됨</i>
        )}
      </span>
      {document.excerpts?.map((excerpt, index) => (
        <blockquote className={styles.excerpt} key={index}>
          {excerpt.page_start && (
            <small>
              {excerpt.page_start}페이지
              {excerpt.page_end && excerpt.page_end !== excerpt.page_start
                ? `–${excerpt.page_end}페이지`
                : ''}
            </small>
          )}
          <p>{excerpt.content}</p>
        </blockquote>
      ))}
      {document.summary_markdown && (
        <details className={styles.sourceSummary}>
          <summary>자료요약 보기</summary>
          <pre>{document.summary_markdown}</pre>
        </details>
      )}
    </li>
  )
  const search = documents?.search
  const searched = search && ['hybrid', 'keyword'].includes(search.method)
  return (
    <div aria-label="AI 브리핑 참고 자료">
      <section className={styles.sources} aria-label="제품 자료">
        <h4 className={styles.sourcesTitle}>📦 제품 자료</h4>
        {documents?.product.length ? (
          <ul className={styles.sourceList}>{documents.product.map(row)}</ul>
        ) : (
          <p className={styles.note}>
            {hasDeal
              ? '이 브리핑에 저장된 제품 자료가 없습니다.'
              : '연결된 영업 건이 없어 제품 자료가 없습니다.'}
          </p>
        )}
      </section>
      <section className={styles.sources} aria-label="관련 자료">
        <h4 className={styles.sourcesTitle}>
          📎 관련 자료
          {searched && <span className={styles.ragTag}>RAG 검색</span>}
        </h4>
        {search?.method === 'keyword' && (
          <p className={styles.note}>키워드로 관련 자료를 검색했습니다.</p>
        )}
        {documents?.related.length ? (
          <ul className={styles.sourceList}>{documents.related.map(row)}</ul>
        ) : (
          <p className={styles.note}>
            {search?.status === 'failed'
              ? '관련 자료 검색에 실패했습니다. 다음 갱신에서 다시 시도합니다.'
              : !documents || search?.status === 'legacy'
                ? '이전 브리핑입니다. 다음 갱신부터 참고 자료를 함께 준비합니다.'
                : '이번 미팅과 관련된 문서 내용이 검색되지 않았습니다.'}
          </p>
        )}
        {search?.status === 'embedding_unavailable' && (
          <p className={styles.note}>의미 검색을 사용할 수 없어 키워드 검색 결과를 표시합니다.</p>
        )}
      </section>
    </div>
  )
}

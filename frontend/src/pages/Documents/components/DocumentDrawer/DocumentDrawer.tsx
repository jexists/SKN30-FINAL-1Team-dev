import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import Drawer from '@/components/Drawer'
import ErrorToast from '@/components/ErrorToast'
import { DownloadIcon } from '@/components/icons'
import type { SalesDocument } from '@/types'
import type { DocumentSummaryResponse } from '@/types'
import { sizeLabel } from '@/utils/attachment'
import { fmtDay, parseISO } from '@/utils/date'

import { KIND_LABEL, fileOf } from '../../catalog'
import { linkLabel } from '../../columns'
import { downloadArtifact, downloadFile, type DocumentArtifact } from '../../download'
import { pollSummary } from '@/api/polling'

import styles from './DocumentDrawer.module.scss'

interface Props {
  doc: SalesDocument
  onClose: () => void
  onSummarize: (fileId: string) => Promise<DocumentSummaryResponse>
  onLoadSummary: (fileId: string) => Promise<DocumentSummaryResponse>
  /** 배치 접수 뒤에는 처리 시작 POST 없이 상태·결과만 조회합니다. */
  autoLoadSummaryFileId?: string
  onSummaryCompleted?: (fileId: string, failureMessage?: string) => void
  onApproveSummary: (fileId: string) => Promise<DocumentSummaryResponse>
}

export default function DocumentDrawer({
  doc,
  onClose,
  onSummarize,
  onLoadSummary,
  autoLoadSummaryFileId,
  onSummaryCompleted,
  onApproveSummary,
}: Props) {
  const [summary, setSummary] = useState<DocumentSummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [summaryLoadError, setSummaryLoadError] = useState<string | null>(null)
  const [summaryLoadRetry, setSummaryLoadRetry] = useState(0)
  const [artifactLoading, setArtifactLoading] = useState<DocumentArtifact | null>(null)
  const [approvalLoading, setApprovalLoading] = useState(false)
  const file = fileOf(doc)
  const rows: [string, string][] = [
    ['메모', doc.description || '—'],
    ['연결', linkLabel(doc) || '연결된 곳 없음'],
    ['파일', file.fileName],
    ['크기', sizeLabel(file.bytes)],
    ['등록자', file.owner],
    ['등록일', fmtDay(parseISO(file.uploaded))],
  ]

  const loadSavedSummary = useCallback(
    (fileId: string) => {
      setSummaryLoadError(null)
      void onLoadSummary(fileId)
        .then((result) => {
          // 아직 처리 전인 정상 응답은 오류가 아니다. 저장된 결과가 있을 때만 표시한다.
          if (result.summary_markdown) setSummary(result)
          else setSummary(null)
        })
        .catch((reason: unknown) => {
          setSummaryLoadError(
            errorMessage(reason, '저장된 요약을 불러오지 못했습니다. 다시 불러와 주세요.'),
          )
        })
    },
    [onLoadSummary],
  )

  useEffect(() => {
    if (!file.id) return
    // 같은 드로어 컴포넌트가 다른 문서로 재사용될 수 있습니다. 새 파일의
    // 결과를 받기 전에 이전 파일의 요약이 잠깐 보이지 않도록 먼저 비웁니다.
    setSummary(null)
    setSummaryError(null)
    setSummaryLoading(false)
    setApprovalLoading(false)
    loadSavedSummary(file.id)
  }, [file.id, loadSavedSummary])

  const requestSummary = useCallback(
    (fileId: string) => {
      setSummaryLoading(true)
      setSummaryError(null)
      setSummaryLoadError(null)
      void onSummarize(fileId)
        .then((result) => {
          setSummary(result)
          if (result.processing_status === 'completed') {
            onSummaryCompleted?.(result.file_id)
          } else if (result.processing_status === 'failed') {
            const message = '문서 요약에 실패했습니다. 잠시 후 다시 시도해 주세요.'
            setSummaryError(message)
            onSummaryCompleted?.(result.file_id, message)
          }
        })
        .catch((reason: unknown) => {
          const message =
            reason instanceof Error && reason.message === 'document_summary_timeout'
              ? '문서 요약 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.'
              : errorMessage(reason, '문서 요약에 실패했습니다. 잠시 후 다시 시도해 주세요.')
          setSummaryError(message)
          onSummaryCompleted?.(fileId, message)
        })
        .finally(() => setSummaryLoading(false))
    },
    [onSummarize, onSummaryCompleted],
  )

  const monitorQueuedSummary = useCallback(
    (fileId: string) => {
      setSummaryLoading(true)
      setSummaryError(null)
      setSummaryLoadError(null)
      void pollSummary({
        // 배치 API가 이미 처리 요청을 접수했으므로 자동 흐름에서는 GET만 수행합니다.
        start: async () => undefined,
        read: () => onLoadSummary(fileId),
      })
        .then((result) => {
          setSummary(result)
          if (result.processing_status === 'completed') {
            onSummaryCompleted?.(result.file_id)
          } else if (result.processing_status === 'failed') {
            const message = '문서 요약에 실패했습니다. 잠시 후 다시 시도해 주세요.'
            setSummaryError(message)
            onSummaryCompleted?.(result.file_id, message)
          }
        })
        .catch((reason: unknown) => {
          const message =
            reason instanceof Error && reason.message === 'document_summary_timeout'
              ? '문서 요약 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.'
              : errorMessage(
                  reason,
                  '문서 요약 결과를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.',
                )
          setSummaryError(message)
          onSummaryCompleted?.(fileId, message)
        })
        .finally(() => setSummaryLoading(false))
    },
    [onLoadSummary, onSummaryCompleted],
  )

  useEffect(() => {
    if (autoLoadSummaryFileId) monitorQueuedSummary(autoLoadSummaryFileId)
  }, [autoLoadSummaryFileId, monitorQueuedSummary])

  async function handleArtifact(artifact: DocumentArtifact) {
    if (!file.id) return
    setArtifactLoading(artifact)
    try {
      await downloadArtifact(doc.id, file.id, artifact)
    } finally {
      setArtifactLoading(null)
    }
  }

  return (
    <Drawer
      title={doc.title}
      sub={doc.documentNo ?? doc.id}
      onClose={onClose}
      meta={
        <>
          <i className={styles.pill}>{doc.category}</i>
          <i className={styles.pill}>{KIND_LABEL[doc.kind]}</i>
        </>
      }
    >
      <ErrorToast
        key={`${file.id ?? 'empty'}-${summaryLoadRetry}`}
        message={summaryLoadError}
        onRetry={() => {
          if (!file.id) return
          setSummaryLoadRetry((value) => value + 1)
          loadSavedSummary(file.id)
        }}
      />
      <dl className={styles.rows}>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      {file.id ? (
        <div className={styles.fileActions}>
          <button type="button" className={styles.download} onClick={() => void downloadFile(file)}>
            <DownloadIcon width={14} height={14} />
            내려받기
          </button>
          <button
            type="button"
            className={styles.summarize}
            disabled={summaryLoading}
            onClick={() => requestSummary(file.id!)}
          >
            {summaryLoading ? '요약 중…' : 'OCR·요약 다시 실행'}
          </button>
        </div>
      ) : (
        <p className={styles.fileActions}>파일 없음</p>
      )}
      {file.note && <p className={styles.note}>{file.note}</p>}

      {(summaryLoading || summaryError || summary?.summary_markdown) && (
        <section className={styles.summary}>
          <h3 className={styles.sectionTitle}>AI 문서 요약</h3>
          {summaryError ? (
            <p className={styles.summaryError}>{summaryError}</p>
          ) : summaryLoading && !summary?.summary_markdown ? (
            <p className={styles.summaryPending} role="status">
              문서 내용을 분석하고 요약하는 중입니다…
            </p>
          ) : (
            <>
              {summary?.processing_status === 'review_required' && (
                <p className={styles.reviewNotice}>
                  OCR·요약 결과를 확인한 뒤 승인해야 최종 DB와 RAG에 저장됩니다.
                </p>
              )}
              <pre>{summary?.summary_markdown}</pre>
              {summary?.processing_status === 'review_required' && (
                <div className={styles.artifactActions}>
                  <button
                    type="button"
                    className={styles.approve}
                    disabled={approvalLoading}
                    onClick={() => {
                      setApprovalLoading(true)
                      void onApproveSummary(summary.file_id)
                        .then(setSummary)
                        .catch(() => setSummaryError('요약을 승인하고 저장하지 못했습니다.'))
                        .finally(() => setApprovalLoading(false))
                    }}
                  >
                    {approvalLoading ? '저장 중…' : '확인하고 최종 저장'}
                  </button>
                </div>
              )}
              {summary?.processing_status === 'completed' && (
                <div className={styles.artifactActions}>
                  {(
                    [
                      ['text', 'TEXT'],
                      ['txt', 'TXT'],
                      ['md', 'Markdown'],
                      ['json', 'JSON'],
                      ['summary', '요약 MD'],
                    ] as [DocumentArtifact, string][]
                  ).map(([artifact, label]) => (
                    <button
                      key={artifact}
                      type="button"
                      className={styles.artifactDownload}
                      disabled={artifactLoading !== null}
                      onClick={() => void handleArtifact(artifact)}
                    >
                      {artifactLoading === artifact ? '준비 중…' : `${label} 다운로드`}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      )}
    </Drawer>
  )
}

import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { DownloadIcon, UploadIcon } from '@/components/icons'
import type { SalesDocument } from '@/types'
import type { DocumentSummaryResponse } from '@/types'
import { sizeLabel } from '@/utils/attachment'
import { fmtDay, parseISO } from '@/utils/date'

import { KIND_LABEL, latestOf } from '../../catalog'
import { linkLabel } from '../../columns'
import { downloadArtifact, downloadVersion, type DocumentArtifact } from '../../download'

import styles from './DocumentDrawer.module.scss'

interface Props {
  doc: SalesDocument
  onClose: () => void
  canUpload: boolean
  onNewVersion: () => void
  onSummarize: (fileId: string) => Promise<DocumentSummaryResponse>
  onLoadSummary: (fileId: string) => Promise<DocumentSummaryResponse>
  autoSummarizeFileId?: string
  onSummaryCompleted?: (fileId: string, failureMessage?: string) => void
  onApproveSummary: (fileId: string) => Promise<DocumentSummaryResponse>
}

export default function DocumentDrawer({
  doc,
  onClose,
  canUpload,
  onNewVersion,
  onSummarize,
  onLoadSummary,
  autoSummarizeFileId,
  onSummaryCompleted,
  onApproveSummary,
}: Props) {
  const [summary, setSummary] = useState<DocumentSummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [artifactLoading, setArtifactLoading] = useState<DocumentArtifact | null>(null)
  const [approvalLoading, setApprovalLoading] = useState(false)
  const latest = latestOf(doc)
  const rows: [string, string][] = [
    ['메모', doc.description || '—'],
    ['연결', linkLabel(doc) || '연결된 곳 없음'],
    ['파일', latest.fileName],
    ['크기', sizeLabel(latest.bytes)],
    ['등록자', latest.owner],
    ['등록일', fmtDay(parseISO(latest.uploaded))],
  ]
  const history = [...doc.versions].reverse()

  useEffect(() => {
    if (!latest.id) return
    void onLoadSummary(latest.id)
      .then((result) => {
        if (result.summary_markdown) setSummary(result)
      })
      .catch(() => {
        // 아직 처리 전인 파일은 빈 상태로 두고, 사용자가 다시 실행할 수 있게 한다.
      })
  }, [latest.id, onLoadSummary])

  const requestSummary = useCallback(
    (fileId: string) => {
      setSummaryLoading(true)
      setSummaryError(null)
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

  useEffect(() => {
    if (autoSummarizeFileId) requestSummary(autoSummarizeFileId)
  }, [autoSummarizeFileId, requestSummary])

  async function handleArtifact(artifact: DocumentArtifact) {
    if (!latest.id) return
    setArtifactLoading(artifact)
    try {
      await downloadArtifact(doc.id, latest.id, artifact)
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
          <i className={`${styles.pill} tnum`}>v{latest.version}</i>
        </>
      }
      footer={
        canUpload && (
          <Button variant="outline" onClick={onNewVersion}>
            <UploadIcon width={14} height={14} />새 버전 올리기
          </Button>
        )
      }
    >
      <dl className={styles.rows}>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      <h3 className={styles.sectionTitle}>버전 이력</h3>
      <ul className={styles.history}>
        {history.map((version) => (
          <li key={version.version} className={styles.version}>
            <div className={styles.versionHead}>
              <strong className="tnum">v{version.version}</strong>
              <span className={styles.fileName}>{version.fileName}</span>
              {version.id ? (
                <>
                  <button
                    type="button"
                    className={styles.download}
                    onClick={() => void downloadVersion(version)}
                  >
                    <DownloadIcon width={14} height={14} />
                    내려받기
                  </button>
                  {version.id === latest.id && (
                    <button
                      type="button"
                      className={styles.summarize}
                      disabled={summaryLoading}
                      onClick={() => requestSummary(version.id!)}
                    >
                      {summaryLoading ? '요약 중…' : 'OCR·요약 다시 실행'}
                    </button>
                  )}
                </>
              ) : (
                <span>파일 없음</span>
              )}
            </div>
            <p className={styles.versionMeta}>
              <span className="tnum">{sizeLabel(version.bytes)}</span>
              <span>{version.owner}</span>
              <span className="tnum">{fmtDay(parseISO(version.uploaded))}</span>
            </p>
            {version.note && <p className={styles.note}>{version.note}</p>}
          </li>
        ))}
      </ul>

      {(summaryError || summary?.summary_markdown) && (
        <section className={styles.summary}>
          <h3 className={styles.sectionTitle}>AI 문서 요약</h3>
          {summaryError ? (
            <p className={styles.summaryError}>{summaryError}</p>
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

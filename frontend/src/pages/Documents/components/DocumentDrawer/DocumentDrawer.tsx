import { useState } from 'react'

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
}

export default function DocumentDrawer({ doc, onClose, canUpload, onNewVersion, onSummarize }: Props) {
  const [summary, setSummary] = useState<DocumentSummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [artifactLoading, setArtifactLoading] = useState<DocumentArtifact | null>(null)
  const latest = latestOf(doc)
  const rows: [string, string][] = [
    ['설명', doc.description || '—'],
    ['연결', linkLabel(doc) || '연결된 곳 없음'],
    ['파일', latest.fileName],
    ['크기', sizeLabel(latest.bytes)],
    ['등록자', latest.owner],
    ['등록일', fmtDay(parseISO(latest.uploaded))],
  ]
  const history = [...doc.versions].reverse()

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

      {doc.tags.length > 0 && (
        <ul className={styles.tags}>
          {doc.tags.map((tag) => (
            <li key={tag}>#{tag}</li>
          ))}
        </ul>
      )}

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
                      onClick={() => {
                        setSummaryLoading(true)
                        setSummaryError(null)
                        void onSummarize(version.id!)
                          .then(setSummary)
                          .catch(() => setSummaryError('문서 요약을 생성하지 못했습니다.'))
                          .finally(() => setSummaryLoading(false))
                      }}
                    >
                      {summaryLoading ? '요약 중…' : 'AI 요약'}
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
              <pre>{summary?.summary_markdown}</pre>
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

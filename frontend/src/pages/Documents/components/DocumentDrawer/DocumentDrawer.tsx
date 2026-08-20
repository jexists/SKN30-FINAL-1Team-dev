import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { DownloadIcon, UploadIcon } from '@/components/icons'
import type { SalesDocument } from '@/types'
import { sizeLabel } from '@/utils/attachment'
import { fmtDay, parseISO } from '@/utils/date'

import { KIND_LABEL, latestOf } from '../../catalog'
import { linkLabel } from '../../columns'
import { downloadVersion } from '../../download'

import styles from './DocumentDrawer.module.scss'

interface Props {
  doc: SalesDocument
  onClose: () => void
  canUpload: boolean
  onNewVersion: () => void
}

export default function DocumentDrawer({ doc, onClose, canUpload, onNewVersion }: Props) {
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
                <button
                  type="button"
                  className={styles.download}
                  onClick={() => void downloadVersion(version)}
                >
                  <DownloadIcon width={14} height={14} />
                  내려받기
                </button>
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
    </Drawer>
  )
}

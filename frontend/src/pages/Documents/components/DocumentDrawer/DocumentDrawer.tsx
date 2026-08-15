// 자료 한 건의 상세입니다. 발주 드로어와 같은 구조에 버전 이력이 하나 더 붙습니다.
//
// 내려받기는 이 세션에서 올린 파일만 됩니다. 시드 문서에는 blob 이 없어 실제로 줄
// 파일이 없으므로 버튼 대신 '시연 데이터'라고 적어 둡니다. 스토리지가 붙으면
// 이 자리가 내려받기 링크가 됩니다.
import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { DownloadIcon, TrashIcon, UploadIcon } from '@/components/icons'
import type { DocumentVersion, SalesDocument } from '@/types'
import { sizeLabel } from '@/utils/attachment'
import { fmtDay, parseISO } from '@/utils/date'

import { KIND_LABEL, latestOf } from '../../catalog'
import { linkLabel } from '../../columns'

import styles from './DocumentDrawer.module.scss'

interface Props {
  doc: SalesDocument
  onClose: () => void
  onNewVersion: () => void
  onDelete: () => void
}

/** 파일을 내려받습니다. 객체 URL 은 쓰고 바로 반납해야 탭이 닫힐 때까지 남지 않습니다. */
function download(version: DocumentVersion) {
  if (!version.blob) return
  const url = URL.createObjectURL(version.blob)
  const link = document.createElement('a')
  link.href = url
  link.download = version.fileName
  link.click()
  URL.revokeObjectURL(url)
}

export default function DocumentDrawer({ doc, onClose, onNewVersion, onDelete }: Props) {
  const latest = latestOf(doc)

  const rows: [string, string][] = [
    ['설명', doc.description || '—'],
    ['연결', linkLabel(doc) || '연결된 곳 없음'],
    ['파일', latest.fileName],
    ['크기', sizeLabel(latest.bytes)],
    ['등록자', latest.owner],
    ['등록일', fmtDay(parseISO(latest.uploaded))],
  ]

  // 이력은 최신이 위로 옵니다. 저장 순서(versions)는 오래된 것부터입니다.
  const history = [...doc.versions].reverse()

  return (
    <Drawer
      title={doc.title}
      sub={doc.id}
      onClose={onClose}
      meta={
        <>
          <i className={styles.pill}>{doc.category}</i>
          <i className={styles.pill}>{KIND_LABEL[doc.kind]}</i>
          <i className={`${styles.pill} tnum`}>v{latest.version}</i>
        </>
      }
      footer={
        <>
          <Button variant="outline" onClick={onNewVersion}>
            <UploadIcon width={14} height={14} />새 버전 올리기
          </Button>
          <Button variant="outline" className={styles.danger} onClick={onDelete}>
            <TrashIcon width={14} height={14} />
            삭제
          </Button>
        </>
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
              {version.blob ? (
                <button type="button" className={styles.download} onClick={() => download(version)}>
                  <DownloadIcon width={14} height={14} />
                  내려받기
                </button>
              ) : (
                <span className={styles.demo}>시연 데이터</span>
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

// 지시 한 건의 수신자별 이행 현황.
//
// 읽기만 합니다. 팀장이 팀원 대신 이행 처리하지 않습니다. 그래야 이행 기록이 실제로 그
// 사람의 말이 되고, 못 한 까닭도 본인이 적은 것이 남습니다.
//
// 목록 응답(GET /notices/manage)이 수신자와 상태를 이미 싣고 오므로 여기서 다시 묻지
// 않습니다.
import Button from '@/components/Button'
import Modal from '@/components/Modal'
import StatusBadge from '@/components/StatusBadge'
import { progressLabel, statusLabel } from '@/shared/noticeStatus'
import type { NoticeManageListResponse } from '@/types'

import styles from './DirectiveStatusModal.module.scss'

interface Props {
  notice: NoticeManageListResponse
  onClose: () => void
}

/** 2026-08-31T09:30:00+09:00 → 2026.08.31 09:30 */
function stamp(value: string | null): string {
  if (value === null) return '—'
  return `${value.slice(0, 10).replaceAll('-', '.')} ${value.slice(11, 16)}`
}

export default function DirectiveStatusModal({ notice, onClose }: Props) {
  return (
    <Modal
      title="이행 현황"
      description={notice.title}
      onClose={onClose}
      footer={
        <Button type="button" variant="outline" onClick={onClose}>
          닫기
        </Button>
      }
    >
      <p className={styles.summary}>{progressLabel(notice.targets)}</p>

      {notice.targets.length === 0 ? (
        <p className={styles.empty}>수신자가 없습니다.</p>
      ) : (
        <ul className={styles.list}>
          {notice.targets.map((target) => {
            const badge = statusLabel(target.status_code)
            return (
              <li key={target.id}>
                <div className={styles.head}>
                  <strong className={styles.name}>{target.display_name}</strong>
                  <StatusBadge label={badge.label} tone={badge.tone} />
                  <span className={`${styles.when} tnum`}>{stamp(target.status_changed_at)}</span>
                </div>
                {/* 미이행일 때만 옵니다. 이행으로 돌리면 서버가 지웁니다. */}
                {target.status_reason !== null && target.status_reason !== '' && (
                  <p className={styles.reason}>{target.status_reason}</p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Modal>
  )
}

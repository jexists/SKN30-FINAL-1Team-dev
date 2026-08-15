// 공지·팀장 지시사항 한 건의 전문입니다.
//
// 목록은 카드 폭에 맞춰 한 줄로 자르므로, 끝까지 읽을 자리가 따로 필요합니다.
// 상세는 전부 오른쪽 드로어로 연다는 대시보드의 약속을 그대로 따릅니다.
import Drawer from '@/components/Drawer'
import { postedFull } from '@/shared/notices'
import type { Notice } from '@/types'

import styles from './NoticeDrawer.module.scss'

interface Props {
  /** 어느 카드에서 왔는지. '공지' 또는 '팀장 지시사항' */
  label: string
  notice: Notice
  onClose: () => void
}

export default function NoticeDrawer({ label, notice, onClose }: Props) {
  return (
    <Drawer
      title={label}
      sub={<span className={styles.when}>{postedFull(notice)}</span>}
      onClose={onClose}
    >
      <h3 className={styles.headline}>{notice.text}</h3>
      <p className={styles.detail}>{notice.detail}</p>
      {/* 이미지는 있는 글에만 붙습니다. 본문을 읽고 난 뒤에 옵니다. */}
      {notice.image && (
        <img className={styles.image} src={notice.image} alt={notice.imageAlt ?? ''} />
      )}
    </Drawer>
  )
}

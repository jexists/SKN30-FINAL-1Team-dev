// 공지·팀장 지시사항 한 건의 전문입니다.
//
// 목록은 카드 폭에 맞춰 한 줄로 자르므로, 끝까지 읽을 자리가 따로 필요합니다.
// 상세는 전부 오른쪽 드로어로 연다는 대시보드의 약속을 그대로 따릅니다.
//
// 티커에는 제목과 올린 시각만 있습니다. 본문은 여기서 받아 옵니다. 첫 응답에 본문까지
// 실으면 열지도 않을 글의 전문을 매번 나르게 됩니다.
import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { InlineLoader } from '@/components/Skeleton'
import { postedFull } from '@/shared/notices'
import type { Notice } from '@/types'

import { useNoticeDetail } from '../../useDashboard'

import styles from './NoticeDrawer.module.scss'

interface Props {
  /** 어느 카드에서 왔는지. '공지' 또는 '팀장 지시사항' */
  label: string
  notice: Notice
  onClose: () => void
}

export default function NoticeDrawer({ label, notice, onClose }: Props) {
  const { body, loading, error, reload } = useNoticeDetail(notice.id ?? null)

  return (
    <Drawer
      title={label}
      sub={<span className={styles.when}>{postedFull(notice)}</span>}
      onClose={onClose}
    >
      {/* 머리말은 목록에서 이미 들고 온 값이라 기다리지 않고 바로 섭니다.
          본문 자리만 비워 두어야 누른 것이 열렸다는 것이 보입니다. */}
      <h3 className={styles.headline}>{notice.text}</h3>

      {error ? (
        <p className={styles.detail} role="alert">
          {error}{' '}
          <Button variant="outline" size="sm" onClick={reload}>
            다시 시도
          </Button>
        </p>
      ) : loading || body === null ? (
        <InlineLoader label="전문을 불러오는 중입니다." />
      ) : (
        /* 본문은 팀장이 편집기로 쓴 HTML 입니다. 서버(app/services/html_sanitize.py)가
           저장할 때 허용 태그만 남기므로 여기서 다시 자르지 않고 그대로 그립니다.
           허용목록을 넓힐 일이 생기면 반드시 서버 쪽을 먼저 봅니다.
           사진도 본문 안에 있습니다. 주소는 서버가 응답할 때마다 새로 발급합니다. */
        // oxlint-disable-next-line react/no-danger
        <div className={styles.detail} dangerouslySetInnerHTML={{ __html: body.body }} />
      )}
    </Drawer>
  )
}

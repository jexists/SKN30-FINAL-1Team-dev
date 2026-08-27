// 대시보드 한 장이 자리를 잡는 동안 세우는 자리표시자입니다.
//
// 카드 한 장이 덩어리 하나입니다. 공지 둘 → KPI 셋과 목표 하나 → 주간 달력 → 오늘 일정
// 순서와 칸 나눔은 실제 화면과 같습니다. 다섯 군데에서 따로 받아 오지만 여기서 한 번에
// 걷어내므로, 자료가 도착하는 동안 화면이 여러 번 들썩이지 않습니다.
import Skeleton from '@/components/Skeleton'

import styles from './DashboardSkeleton.module.scss'

/** 카드별 높이. 실제 카드와 같은 값이어야 자리표시자를 걷을 때 화면이 밀리지 않습니다. */
const NOTICE_H = 168
const TILE_H = 116
const WEEK_H = 176
const AGENDA_H = 300

export default function DashboardSkeleton() {
  return (
    <div role="status">
      <span className="sr-only">대시보드를 불러오는 중입니다.</span>

      <div className={styles.notices}>
        <Skeleton height={NOTICE_H} radius="var(--r-lg)" />
        <Skeleton height={NOTICE_H} radius="var(--r-lg)" />
      </div>

      <div className={styles.summary}>
        {[0, 1, 2].map((at) => (
          <Skeleton key={at} height={TILE_H} radius="var(--r-lg)" />
        ))}
        <Skeleton className={styles.goal} height={TILE_H} radius="var(--r-lg)" />
      </div>

      <Skeleton className={styles.week} height={WEEK_H} radius="var(--r-lg)" />
      <Skeleton height={AGENDA_H} radius="var(--r-lg)" />
    </div>
  )
}

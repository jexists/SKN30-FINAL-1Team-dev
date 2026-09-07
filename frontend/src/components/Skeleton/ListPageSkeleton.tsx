// 목록 화면 한 장이 자리를 잡는 동안 세우는 자리표시자입니다.
//
// 영업·견적·계약·발주·고객·자료실·고객불만은 모두 툴바 → 탭 → 표 → 페이지네이션
// 순서가 같아 한 벌로 씁니다(pages/listPage.module.scss 참고).
//
// 표를 부분만 덮지 않고 화면 전체를 덮는 이유: 툴바·탭은 데이터를 받은 뒤에야
// 개수와 선택지가 정해집니다. 표만 자리표시자로 두면 그 위 줄들이 뒤늦게 나타나
// 화면이 두 번 들썩입니다.
import Skeleton from './Skeleton'
import { CONTROL_H, tableHeight } from './metrics'

import styles from './ListPageSkeleton.module.scss'

interface Props {
  /** 화면 낭독기가 읽을 말 */
  label: string
  /** 검색·필터 줄 */
  toolbar?: boolean
  /** 단계·분류 탭 줄 */
  tabs?: boolean
  /** 표 본문 높이를 정하는 줄 수 */
  rows?: number
  pagination?: boolean
}

export default function ListPageSkeleton({
  label,
  toolbar = true,
  tabs = false,
  rows = 8,
  pagination = true,
}: Props) {
  return (
    <div className={styles.page} role="status">
      <span className="sr-only">{label}</span>

      {toolbar && (
        <div className={styles.toolbar}>
          <Skeleton className={styles.search} height={CONTROL_H} radius="var(--r-sm)" />
          <Skeleton width={132} height={CONTROL_H} radius="var(--r-sm)" />
          <Skeleton width={112} height={CONTROL_H} radius="var(--r-sm)" />
        </div>
      )}

      {tabs && <Skeleton width="62%" height={CONTROL_H} radius="var(--r-pill)" />}

      <Skeleton height={tableHeight(rows)} radius="var(--r-lg)" />

      {pagination && (
        <div className={styles.pagination}>
          <Skeleton width={148} height={CONTROL_H} radius="var(--r-sm)" />
          <Skeleton width={196} height={CONTROL_H} radius="var(--r-sm)" />
        </div>
      )}
    </div>
  )
}

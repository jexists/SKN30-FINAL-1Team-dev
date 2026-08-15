// demo/layout_v3.html 의 #poDrawer 입니다.
// 발주 한 건의 값을 그대로 보여 줍니다. 대시보드(타일·일정)와 발주 목록이 함께 씁니다.
//
// 하단 버튼은 부른 쪽이 정합니다. 대시보드 목록에서 들어왔으면 목록으로 돌아가고,
// 발주 목록에서 들어왔으면 수정·삭제·전체 보기가 붙습니다. 일정 드로어에서 바로
// 들어왔을 때는 돌아갈 목록도 고칠 권한도 없어 아무것도 붙지 않습니다.
import { Link } from 'react-router'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { ChevronRightIcon, TrashIcon } from '@/components/icons'
import { isLate, orderItemLabel, orderTotal } from '@/shared/orders'
import type { PurchaseOrder } from '@/types'
import { fmtDay, parseISO } from '@/utils/date'
import { wonFull } from '@/utils/format'

import styles from './OrderDrawer.module.scss'

interface Props {
  order: PurchaseOrder
  /** 목록에서 들어왔을 때만 있습니다. */
  onBack?: () => void
  onEdit?: () => void
  onDelete?: () => void
  /** 발주 상세 경로. 주면 "전체 보기"가 붙습니다. */
  detailTo?: string
  onClose: () => void
}

export default function OrderDrawer({ order, onBack, onEdit, onDelete, detailTo, onClose }: Props) {
  const late = isLate(order)

  const rows: [string, string][] = [
    ['품목', orderItemLabel(order)],
    ['금액', wonFull(orderTotal(order))],
    ['공급처', order.supplier],
    ['계약', order.contract || '계약 없는 선발주'],
    ['발주일', fmtDay(parseISO(order.ordered))],
    ['납기', fmtDay(parseISO(order.due))],
    ['예상 입고', fmtDay(parseISO(order.expect))],
    ['메모', order.memo || '—'],
  ]

  return (
    <Drawer
      title={order.hospital}
      sub={order.no}
      onClose={onClose}
      meta={
        <>
          <i className={styles.pill}>{order.status}</i>
          {late && (
            <i className={`${styles.pill} ${styles.risk}`}>
              납기 {order.expectOff - order.dueOff}일 초과
            </i>
          )}
        </>
      }
      footer={
        (onBack || onEdit || onDelete || detailTo) && (
          // Drawer 의 하단 줄이 이미 가로로 늘어놓으므로 감싸지 않습니다.
          <>
            {onBack && (
              <Button variant="outline" onClick={onBack}>
                ← 목록으로
              </Button>
            )}
            {onEdit && (
              <Button variant="outline" onClick={onEdit}>
                수정
              </Button>
            )}
            {onDelete && (
              <Button variant="outline" className={styles.danger} onClick={onDelete}>
                <TrashIcon width={14} height={14} />
                삭제
              </Button>
            )}
            {detailTo && (
              <Link className={styles.cta} to={detailTo}>
                전체 보기
                <ChevronRightIcon />
              </Link>
            )}
          </>
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
    </Drawer>
  )
}

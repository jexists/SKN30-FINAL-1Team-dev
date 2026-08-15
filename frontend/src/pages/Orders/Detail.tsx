// 발주 한 건의 전체 화면입니다. Drawer 가 요약이라면 여기는 품목을 줄 단위로 펼치고
// 걸린 계약과 같은 고객사의 다른 발주까지 봅니다.
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import { ChevronLeftIcon } from '@/components/icons'
import { ROUTES, contractPath, orderPath } from '@/constants/routes'
import { isLate, orderItemLabel, orderTotal } from '@/shared/orders'
import type { OrderStatus } from '@/types'
import { fmtDot, fmtDotShort, parseISO } from '@/utils/date'
import { won, wonFull } from '@/utils/format'

import OrderForm from './components/OrderForm'
import { ORDER_STATUSES, TONE_OF } from './pipeline'
import useOrderList from './useOrderList'

import styles from './Detail.module.scss'

export default function OrderDetail() {
  const { orderNo = '' } = useParams()
  const navigate = useNavigate()
  const { orders, findOrder, updateOrder, setStatus, removeOrder } = useOrderList()

  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const order = findOrder(orderNo)

  if (!order) {
    return (
      <section className={styles.missing}>
        <h1>발주를 찾을 수 없습니다.</h1>
        <p>번호가 바뀌었거나 삭제된 발주입니다.</p>
        <Link className={styles.back} to={ROUTES.ORDERS}>
          <ChevronLeftIcon />
          발주 관리로
        </Link>
      </section>
    )
  }

  const late = isLate(order)
  const sameHospital = orders
    .filter((o) => o.hospital === order.hospital && o.no !== order.no)
    .slice(0, 8)

  return (
    <section className={styles.page}>
      <Link className={styles.back} to={ROUTES.ORDERS}>
        <ChevronLeftIcon />
        발주 관리
      </Link>

      <header className={styles.head}>
        <div>
          <p className={`${styles.no} tnum`}>{order.no}</p>
          <h1 className={styles.hospital}>{order.hospital}</h1>
          <p className={styles.supplier}>{order.supplier}</p>
        </div>

        <p className={`${styles.amount} tnum`}>{wonFull(orderTotal(order))}</p>
      </header>

      <div className={styles.actions}>
        <label className={styles.status}>
          <span className={styles.statusLabel}>상태</span>
          <select
            className={styles.select}
            value={order.status}
            onChange={(event) => setStatus(order.no, event.target.value as OrderStatus)}
          >
            {ORDER_STATUSES.map((status) => (
              <option key={status}>{status}</option>
            ))}
          </select>
        </label>

        <Button type="button" variant="outline" onClick={() => setEditing(true)}>
          수정
        </Button>
        <Button type="button" variant="ghost" onClick={() => setDeleting(true)}>
          삭제
        </Button>
      </div>

      <dl className={styles.facts}>
        <div>
          <dt>상태</dt>
          <dd>
            <span className={[styles.pill, styles[TONE_OF[order.status]]].join(' ')}>
              {order.status}
            </span>
          </dd>
        </div>
        <div>
          <dt>계약</dt>
          <dd>
            {order.contract ? (
              <Link className={styles.link} to={contractPath(order.contract)}>
                {order.contract}
              </Link>
            ) : (
              '계약 없는 선발주'
            )}
          </dd>
        </div>
        <div>
          <dt>발주일</dt>
          <dd className="tnum">{fmtDot(parseISO(order.ordered))}</dd>
        </div>
        <div>
          <dt>납기</dt>
          <dd className="tnum">{fmtDot(parseISO(order.due))}</dd>
        </div>
        <div>
          <dt>예상 입고</dt>
          <dd className="tnum">
            {fmtDot(parseISO(order.expect))}
            {late && <i className={styles.late}>{order.expectOff - order.dueOff}일 지연</i>}
          </dd>
        </div>
      </dl>

      {order.memo && <p className={styles.memo}>{order.memo}</p>}

      <section className={styles.block}>
        <h2 className={styles.blockTitle}>품목</h2>
        <ul className={styles.items}>
          {order.items.map((item) => (
            <li key={item.product} className={styles.item}>
              <span className={styles.itemProduct}>{item.product}</span>
              {/* 소모품은 단가가 몇만 원이라 요약 표기로는 ₩0.0M 이 됩니다. */}
              <span className={`${styles.itemQty} tnum`}>
                {item.qty}개 × {wonFull(item.price)}
              </span>
              <span className={`${styles.itemSum} tnum`}>{wonFull(item.qty * item.price)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.block}>
        <h2 className={styles.blockTitle}>{order.hospital}의 다른 발주</h2>
        {sameHospital.length === 0 ? (
          <p className={styles.empty}>다른 발주가 없습니다.</p>
        ) : (
          <ul className={styles.siblings}>
            {sameHospital.map((item) => (
              <li key={item.no}>
                <Link className={styles.sibling} to={orderPath(item.no)}>
                  <span className={`${styles.siblingNo} tnum`}>{item.no}</span>
                  <span className={styles.siblingItems}>{orderItemLabel(item)}</span>
                  <span className={`${styles.siblingAmount} tnum`}>{won(orderTotal(item))}</span>
                  <span className={`${styles.siblingDate} tnum`}>
                    {fmtDotShort(parseISO(item.ordered))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {editing && (
        <OrderForm
          order={order}
          onClose={() => setEditing(false)}
          onSubmit={(draft) => {
            updateOrder(order.no, draft)
            setEditing(false)
          }}
        />
      )}

      {deleting && (
        <Modal
          title="발주를 삭제할까요?"
          description={`${order.no} · ${order.hospital}. 되돌릴 수 없습니다.`}
          onClose={() => setDeleting(false)}
          footer={
            <>
              <Button type="button" variant="outline" onClick={() => setDeleting(false)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  removeOrder(order.no)
                  // 지운 발주의 상세에 머물면 "찾을 수 없습니다" 만 보입니다.
                  navigate(ROUTES.ORDERS, { replace: true })
                }}
              >
                삭제
              </Button>
            </>
          }
        >
          <p className={styles.empty}>
            {orderItemLabel(order)} · {order.supplier}
          </p>
        </Modal>
      )}
    </section>
  )
}

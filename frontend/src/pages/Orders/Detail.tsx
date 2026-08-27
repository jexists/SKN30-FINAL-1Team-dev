// 발주 한 건의 전체 화면입니다. Drawer 가 요약이라면 여기는 품목을 줄 단위로 펼치고
// 걸린 계약과 같은 고객사의 다른 발주까지 봅니다.
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import { SkeletonDetail } from '@/components/Skeleton'
import { ChevronLeftIcon } from '@/components/icons'
import { ROUTES, orderPath } from '@/constants/routes'
import { isLate, orderItemLabel, orderTotal } from '@/shared/orders'
import { fmtDot, fmtDotShort, parseISO } from '@/utils/date'
import { won, wonFull } from '@/utils/format'

import OrderForm from './components/OrderForm'
import useOrderList from './useOrderList'

import styles from './Detail.module.scss'

export default function OrderDetail() {
  const { orderNo = '' } = useParams()
  const navigate = useNavigate()
  const {
    orders,
    statuses,
    suppliers,
    loading,
    error,
    reload,
    detail,
    detailLoading,
    detailError,
    reloadDetail,
    mutationError,
    isPending,
    findOrderByNo,
    updateOrder,
    setStatus,
    removeOrder,
  } = useOrderList(orderNo)

  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const order = detail ?? findOrderByNo(orderNo)

  if ((loading || detailLoading) && !order) {
    return (
      <section>
        <SkeletonDetail label="발주를 불러오는 중입니다." title height={440} actions={2} />
      </section>
    )
  }

  if (error || detailError) {
    return (
      <section className={styles.missing} role="alert">
        <h1>{detailError ?? error}</h1>
        <Button variant="outline" onClick={detailError ? reloadDetail : reload}>
          다시 시도
        </Button>
      </section>
    )
  }

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
    <section className={styles.page} aria-busy={detailLoading || isPending(order.id)}>
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
            value={order.stageCode}
            disabled={isPending(order.id)}
            onChange={(event) => {
              const next = event.target.value
              if (next !== order.stageCode)
                void setStatus(order.id, order.stageCode, next).catch(() => undefined)
            }}
          >
            {!statuses.some(({ code }) => code === order.stageCode) && (
              <option value={order.stageCode}>{order.status} (기존값)</option>
            )}
            {statuses.map((status) => (
              <option key={status.id} value={status.code}>
                {status.name}
              </option>
            ))}
          </select>
        </label>

        <Button
          type="button"
          variant="outline"
          disabled={isPending(order.id)}
          onClick={() => setEditing(true)}
        >
          수정
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={isPending(order.id)}
          onClick={() => setDeleting(true)}
        >
          삭제
        </Button>
      </div>

      <dl className={styles.facts}>
        <div>
          <dt>상태</dt>
          <dd>
            <span className={[styles.pill, styles[order.stageTone]].join(' ')}>{order.status}</span>
          </dd>
        </div>
        <div>
          <dt>영업 딜</dt>
          <dd>
            <Link
              className={styles.link}
              to={`${ROUTES.DEALS}?q=${encodeURIComponent(order.salesDeal)}`}
            >
              {order.salesDeal}
            </Link>
          </dd>
        </div>
        <div>
          <dt>요청부서</dt>
          <dd>{order.requestDepartment}</dd>
        </div>
        <div>
          <dt>협조부서</dt>
          <dd>{order.cooperationDepartment}</dd>
        </div>
        <div>
          <dt>작성자</dt>
          <dd>{order.createdBy}</dd>
        </div>
        <div>
          <dt>납품예상 거래처</dt>
          <dd>{order.expectedCustomerCompany}</dd>
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
            <li key={item.id} className={styles.item}>
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
          statuses={statuses}
          suppliers={suppliers}
          optionsLoading={loading}
          onClose={() => setEditing(false)}
          onSubmit={async (draft) => {
            await updateOrder(order.id, draft)
            setEditing(false)
          }}
        />
      )}

      {deleting && (
        <Modal
          title="발주를 삭제할까요?"
          description={`${order.no} · ${order.hospital}. 되돌릴 수 없습니다.`}
          onClose={isPending(order.id) ? () => {} : () => setDeleting(false)}
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                disabled={isPending(order.id)}
                onClick={() => setDeleting(false)}
              >
                취소
              </Button>
              <Button
                type="button"
                disabled={isPending(order.id)}
                onClick={() => {
                  void removeOrder(order.id)
                    .then(() => navigate(ROUTES.ORDERS, { replace: true }))
                    .catch(() => undefined)
                }}
              >
                {isPending(order.id) ? '삭제 중…' : '삭제'}
              </Button>
            </>
          }
        >
          <p className={styles.empty}>
            {orderItemLabel(order)} · {order.supplier}
          </p>
          {mutationError && <p role="alert">{mutationError}</p>}
        </Modal>
      )}

      {mutationError && !deleting && <p role="alert">{mutationError}</p>}
    </section>
  )
}

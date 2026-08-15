// 계약 한 건의 전체 화면입니다. Drawer 가 요약이라면 여기는 주변 맥락까지 봅니다.
// 관련 발주와 같은 고객사의 다른 계약이 그 맥락입니다.
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import { ChevronLeftIcon } from '@/components/icons'
import { ROUTES, contractPath } from '@/constants/routes'
import { orderItemLabel, orders } from '@/shared/orders'
import { fmtDot, fmtDotShort, parseISO } from '@/utils/date'
import { won, wonFull } from '@/utils/format'

import ContractForm from './components/ContractForm'
import useContractBoard from './useContractBoard'

import styles from './Detail.module.scss'

export default function ContractDetail() {
  const { contractNo = '' } = useParams()
  const navigate = useNavigate()
  const { columns, cards, findContract, moveCard, updateContract, removeContract } =
    useContractBoard()

  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const contract = findContract(contractNo)

  if (!contract) {
    return (
      <section className={styles.missing}>
        <h1>계약을 찾을 수 없습니다.</h1>
        <p>번호가 바뀌었거나 삭제된 계약입니다.</p>
        <Link className={styles.back} to={ROUTES.CONTRACTS}>
          <ChevronLeftIcon />
          계약 현황으로
        </Link>
      </section>
    )
  }

  const column = columns.find((col) => col.id === contract.stageId)
  const related = orders.filter((o) => o.contract === contract.no)
  const sameOrg = cards.filter((c) => c.org === contract.org && c.no !== contract.no).slice(0, 8)

  return (
    <section className={styles.page}>
      <Link className={styles.back} to={ROUTES.CONTRACTS}>
        <ChevronLeftIcon />
        계약 현황
      </Link>

      <header className={styles.head}>
        <div>
          <p className={`${styles.no} tnum`}>{contract.no}</p>
          <h1 className={styles.org}>{contract.org}</h1>
          <p className={styles.product}>
            {contract.product} · {contract.kind}
          </p>
        </div>

        <p className={`${styles.amount} tnum`}>{wonFull(contract.amount)}</p>
      </header>

      <div className={styles.actions}>
        <label className={styles.stage}>
          <span className={styles.stageLabel}>단계</span>
          <select
            className={styles.select}
            value={contract.stageId}
            onChange={(event) => moveCard(contract.no, event.target.value, 0)}
          >
            {columns.map((col) => (
              <option key={col.id} value={col.id}>
                {col.name}
              </option>
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
          <dd>{contract.status}</dd>
        </div>
        <div>
          <dt>단계</dt>
          <dd>{column?.name ?? '-'}</dd>
        </div>
        <div>
          <dt>담당 영업</dt>
          <dd>{contract.owner}</dd>
        </div>
        <div>
          <dt>지역</dt>
          <dd>{contract.region}</dd>
        </div>
        <div>
          <dt>계약일</dt>
          <dd className="tnum">{fmtDot(parseISO(contract.date))}</dd>
        </div>
      </dl>

      {contract.memo && <p className={styles.memo}>{contract.memo}</p>}

      <section className={styles.block}>
        <h2 className={styles.blockTitle}>관련 발주</h2>
        {related.length === 0 ? (
          <p className={styles.empty}>이 계약으로 잡힌 발주가 없습니다.</p>
        ) : (
          <ul className={styles.orders}>
            {related.map((order) => (
              <li key={order.no} className={styles.order}>
                <span className={`${styles.orderNo} tnum`}>{order.no}</span>
                <span className={styles.orderItems}>{orderItemLabel(order)}</span>
                <span className={styles.orderStatus}>{order.status}</span>
                <span className={`${styles.orderDue} tnum`}>
                  납기 {fmtDotShort(parseISO(order.due))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.block}>
        <h2 className={styles.blockTitle}>{contract.org}의 다른 계약</h2>
        {sameOrg.length === 0 ? (
          <p className={styles.empty}>다른 계약이 없습니다.</p>
        ) : (
          <ul className={styles.siblings}>
            {sameOrg.map((item) => (
              <li key={item.no}>
                <Link className={styles.sibling} to={contractPath(item.no)}>
                  <span className={`${styles.siblingNo} tnum`}>{item.no}</span>
                  <span className={styles.siblingProduct}>{item.product}</span>
                  <span className={`${styles.siblingAmount} tnum`}>{won(item.amount)}</span>
                  <span className={`${styles.siblingDate} tnum`}>
                    {fmtDotShort(parseISO(item.date))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {editing && (
        <ContractForm
          contract={contract}
          onClose={() => setEditing(false)}
          onSubmit={(draft) => {
            updateContract(contract.no, draft)
            setEditing(false)
          }}
        />
      )}

      {deleting && (
        <Modal
          title="계약을 삭제할까요?"
          description={`${contract.no} · ${contract.org}. 되돌릴 수 없습니다.`}
          onClose={() => setDeleting(false)}
          footer={
            <>
              <Button type="button" variant="outline" onClick={() => setDeleting(false)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  removeContract(contract.no)
                  // 지운 계약의 상세에 머물면 "찾을 수 없습니다" 만 보입니다.
                  navigate(ROUTES.CONTRACTS, { replace: true })
                }}
              >
                삭제
              </Button>
            </>
          }
        >
          <p className={styles.empty}>
            {contract.product} · {contract.owner}
          </p>
        </Modal>
      )}
    </section>
  )
}

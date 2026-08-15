// 표에서 고객 한 줄을 누르면 서는 상세입니다.
// 왼쪽은 그 사람 자체(연락처·접촉 현황·열린 일감), 오른쪽은 이력과 회사 맥락입니다.
//
// 대시보드의 RecordDrawer 와 같은 2열 wide 드로어입니다. 같은 앱에서 상세가
// 두 가지 모양이면 안 되므로 클래스 어휘까지 그대로 맞췄습니다.
//
// 후속업무·C/S·갱신은 걸리는 사람이 몇 안 됩니다. 없을 때 빈 상자를 그리면
// 드로어가 '없음' 목록이 되므로 섹션째 빼고, 표제인 미팅과 발주만 빈 상태를 남깁니다.
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import Drawer from '@/components/Drawer'
import { KIND_LABEL } from '@/shared/agenda'
import { confirmedTotal } from '@/shared/contracts'
import { relativeDayLabel } from '@/shared/customers'
import { isLate, orderItemLabel } from '@/shared/orders'
import type { AgendaKind, Customer } from '@/types'
import { contractPath } from '@/constants/routes'
import { addDays, ddayLabel, fmtDay, parseISO, TODAY } from '@/utils/date'
import { won } from '@/utils/format'

import {
  colleaguesOf,
  contractsOf,
  csRequestsOf,
  followUpsOf,
  meetingsOf,
  ordersOf,
  renewalsOf,
} from '../../customerProfile'

import styles from './CustomerDrawer.module.scss'

/** 회사 계약은 최근 것부터 이만큼만 보여 줍니다. 나머지는 계약 화면의 몫입니다. */
const CONTRACT_LIMIT = 5

// DayAgenda·RecordDrawer 의 배지 색과 같습니다. 화면마다 색이 바뀌면 안 됩니다.
const KIND_TONE: Partial<Record<AgendaKind, string>> = {
  visit: styles.kindBlue,
  demo: styles.kindPurple,
  booth: styles.kindPurple,
  edu: styles.kindGreen,
  delivery: styles.kindOrange,
}

interface Props {
  customer: Customer
  /** 같은 회사 담당자를 뽑을 목록. 페이지가 들고 있는 rows 를 그대로 받습니다. */
  all: Customer[]
  /** 같은 회사 다른 담당자를 누르면 그 사람으로 갈아탑니다. */
  onOpen: (id: string) => void
  onClose: () => void
}

interface Tag {
  text: string
  tone?: 'risk' | 'good' | 'now'
  /** 일정 종류 배지. 앞에 점이 붙는 다른 모양입니다. */
  kind?: AgendaKind
}

interface EntryProps {
  title: string
  side?: string
  /** 기한을 넘긴 값. 주황으로 세웁니다. */
  sideLate?: boolean
  note?: string
  tags?: Tag[]
}

/** 목록 한 줄. 미팅·발주·계약·후속업무가 전부 이 모양을 씁니다. */
function Entry({ title, side, sideLate, note, tags }: EntryProps) {
  return (
    <div className={styles.entry}>
      <div className={styles.entryHead}>
        <strong>{title}</strong>
        {side !== undefined && (
          <span className={`${styles.side} tnum ${sideLate ? styles.late : ''}`}>{side}</span>
        )}
      </div>
      {note !== undefined && <p className={styles.entryNote}>{note}</p>}
      {tags !== undefined && tags.length > 0 && <Tags tags={tags} />}
    </div>
  )
}

function Tags({ tags }: { tags: Tag[] }) {
  return (
    <div className={styles.tags}>
      {tags.map((t) =>
        t.kind ? (
          <span key={t.text} className={`${styles.kind} ${KIND_TONE[t.kind] ?? ''}`}>
            {t.text}
          </span>
        ) : (
          <i key={t.text} className={`${styles.pill} ${t.tone ? styles[t.tone] : ''}`}>
            {t.text}
          </i>
        ),
      )}
    </div>
  )
}

interface BlockProps {
  title: string
  /** 제목 오른쪽 작은 글씨. 회사 단위 섹션임을 여기서 밝힙니다. */
  note?: string
  children: ReactNode
}

function Block({ title, note, children }: BlockProps) {
  return (
    <section className={styles.block}>
      <h3>
        {title}
        {note !== undefined && <span className={styles.blockNote}>{note}</span>}
      </h3>
      {children}
    </section>
  )
}

export default function CustomerDrawer({ customer, all, onOpen, onClose }: Props) {
  const meetings = meetingsOf(customer)
  const tasks = followUpsOf(customer)
  const cs = csRequestsOf(customer)
  const renewals = renewalsOf(customer)
  const companyContracts = contractsOf(customer)
  const companyOrders = ordersOf(customer)
  const colleagues = colleaguesOf(customer, all)

  // 같은 접촉이 여러 일정에 겹쳐 적혀 있습니다. 한 번씩만 세웁니다.
  const historySeen = new Set<string>()
  const history = meetings
    .flatMap((it) => it.history)
    .filter((h) => {
      const key = `${h.when}|${h.what}`
      if (historySeen.has(key)) return false
      historySeen.add(key)
      return true
    })

  // 이메일·전화는 누를 수 있어야 해 아래에서 따로 그립니다.
  const facts: [string, string][] = [
    ['부서', customer.dept],
    ['직함', customer.title],
    ['담당 영업', customer.owner],
    ['유입 소스', customer.source],
    ['등록일', fmtDay(parseISO(customer.created))],
  ]

  return (
    <Drawer
      wide
      title={customer.name}
      sub={[customer.org, customer.dept, customer.title].filter(Boolean).join(' · ')}
      resetKey={customer.id}
      onClose={onClose}
      meta={
        <>
          <i
            className={`${styles.pill} ${
              customer.status === '계약'
                ? styles.good
                : customer.status === '보류'
                  ? styles.hold
                  : ''
            }`}
          >
            {customer.status}
          </i>
          <i className={styles.pill}>유입 {customer.source}</i>
          <span className={styles.when}>담당 {customer.owner}</span>
          {customer.overdue && <i className={`${styles.pill} ${styles.risk}`}>후속 지연</i>}
        </>
      }
      footer={
        <a className={styles.cta} href={`mailto:${customer.email}`}>
          이메일 보내기
        </a>
      }
    >
      <div className={styles.grid}>
        <div className={styles.col}>
          <Block title="연락처">
            <dl className={styles.facts}>
              <div>
                <dt>이메일</dt>
                <dd>
                  <a className={styles.mail} href={`mailto:${customer.email}`}>
                    {customer.email}
                  </a>
                </dd>
              </div>
              <div>
                <dt>전화</dt>
                <dd>
                  <a className={`${styles.mail} tnum`} href={`tel:${customer.phone}`}>
                    {customer.phone}
                  </a>
                </dd>
              </div>
              {facts.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </Block>

          <Block title="접촉 현황">
            <dl className={styles.facts}>
              <div>
                <dt>최근 접촉</dt>
                <dd>
                  {fmtDay(parseISO(customer.last))}
                  <span className={styles.rel}>{relativeDayLabel(customer.last)}</span>
                </dd>
              </div>
              <div>
                <dt>다음 일정</dt>
                <dd className={customer.overdue ? styles.overdue : undefined}>
                  {customer.next === null ? (
                    '잡힌 일정 없음'
                  ) : (
                    <>
                      {fmtDay(parseISO(customer.next))}
                      <span className={styles.rel}>{relativeDayLabel(customer.next)}</span>
                    </>
                  )}
                </dd>
              </div>
            </dl>
          </Block>

          <Block title="메모">
            <p className={styles.note}>{customer.memo}</p>
          </Block>

          {tasks.length > 0 && (
            <Block title="미완료 후속업무">
              <div className={styles.stack}>
                {tasks.map((f) => (
                  <Entry
                    key={f.task}
                    title={f.task}
                    side={ddayLabel(f.dueOff)}
                    sideLate={f.dueOff < 0}
                    note={f.note}
                    tags={[
                      ...(f.dueOff < 0 ? [{ text: '지연', tone: 'risk' as const }] : []),
                      { text: `마감 ${fmtDay(addDays(TODAY, f.dueOff))}` },
                    ]}
                  />
                ))}
              </div>
            </Block>
          )}

          {cs.length > 0 && (
            <Block title="C/S 대응요청">
              <div className={styles.stack}>
                {cs.map((c) => (
                  <Entry
                    key={c.id}
                    title={c.issue}
                    side={c.ago}
                    sideLate={c.state === '처리중'}
                    note={c.note}
                    tags={[
                      ...(c.urgent ? [{ text: '긴급', tone: 'risk' as const }] : []),
                      {
                        text: c.state,
                        tone: c.state === '처리완료' ? ('good' as const) : undefined,
                      },
                      // 화면에서 등록한 건에는 제품이 없습니다. 빈 배지를 만들지 않습니다.
                      ...(c.product ? [{ text: c.product }] : []),
                    ]}
                  />
                ))}
              </div>
            </Block>
          )}
        </div>

        <div className={styles.col}>
          <Block title="이전 미팅">
            {meetings.length === 0 ? (
              <p className={`${styles.note} ${styles.muted}`}>기록된 미팅이 없습니다.</p>
            ) : (
              <div className={styles.stack}>
                {meetings.map((it) => (
                  <Entry
                    key={it.id}
                    title={it.title}
                    side={fmtDay(parseISO(it.date))}
                    note={`${it.time} · ${it.dur} · ${it.place}`}
                    tags={[
                      { text: KIND_LABEL[it.kind], kind: it.kind },
                      ...(it.stage ? [{ text: it.stage }] : []),
                      { text: it.product },
                    ]}
                  />
                ))}
              </div>
            )}
          </Block>

          {history.length > 0 && (
            <Block title="지난 접촉 기록">
              {history.map((h) => (
                <div key={`${h.when}-${h.what}`} className={styles.history}>
                  <time>{h.when}</time>
                  <p>{h.what}</p>
                </div>
              ))}
            </Block>
          )}

          <Block title="진행 중인 발주" note={`${customer.org} 전체`}>
            {companyOrders.length === 0 ? (
              <p className={`${styles.note} ${styles.muted}`}>진행 중인 발주가 없습니다.</p>
            ) : (
              <div className={styles.stack}>
                {companyOrders.map((o) => (
                  <Entry
                    key={o.no}
                    title={o.no}
                    side={ddayLabel(o.expectOff)}
                    sideLate={isLate(o)}
                    note={`${orderItemLabel(o)} · ${o.supplier}`}
                    tags={[
                      { text: o.status },
                      ...(isLate(o)
                        ? [{ text: `납기 ${o.expectOff - o.dueOff}일 초과`, tone: 'risk' as const }]
                        : []),
                      { text: `납기 ${fmtDay(parseISO(o.due))}` },
                    ]}
                  />
                ))}
              </div>
            )}
          </Block>

          <Block
            title="소속 회사 계약"
            note={`확정 ${won(confirmedTotal(companyContracts))} · ${companyContracts.length}건`}
          >
            {companyContracts.length === 0 ? (
              <p className={`${styles.note} ${styles.muted}`}>등록된 계약이 없습니다.</p>
            ) : (
              <div className={styles.stack}>
                {companyContracts.slice(0, CONTRACT_LIMIT).map((ct) => (
                  <Link key={ct.no} className={styles.link} to={contractPath(ct.no)}>
                    <span>
                      <strong>{ct.no}</strong>
                      <small>
                        {ct.product} · {ct.kind}
                      </small>
                    </span>
                    <span className={`${styles.side} tnum`}>{won(ct.amount)}</span>
                  </Link>
                ))}
                {companyContracts.length > CONTRACT_LIMIT && (
                  <p className={`${styles.note} ${styles.muted}`}>
                    외 {companyContracts.length - CONTRACT_LIMIT}건은 계약 화면에서 볼 수 있습니다.
                  </p>
                )}
              </div>
            )}
          </Block>

          {renewals.length > 0 && (
            <Block title="계약갱신 예정">
              <div className={styles.stack}>
                {renewals.map((r) => (
                  <Entry
                    key={r.contract}
                    title={r.contract}
                    side={ddayLabel(r.expireOff)}
                    note={r.note}
                    tags={[
                      { text: r.kind },
                      { text: won(r.amount) },
                      { text: `만료 ${fmtDay(addDays(TODAY, r.expireOff))}`, tone: 'now' },
                    ]}
                  />
                ))}
              </div>
            </Block>
          )}

          {colleagues.length > 0 && (
            <Block title="같은 회사 다른 담당자" note={`${colleagues.length}명`}>
              <div className={styles.stack}>
                {colleagues.map((other) => (
                  <button
                    key={other.id}
                    type="button"
                    className={styles.link}
                    onClick={() => onOpen(other.id)}
                  >
                    <span>
                      <strong>{other.name}</strong>
                      <small>
                        {other.dept} {other.title}
                      </small>
                    </span>
                    <i className={`${styles.pill} ${other.status === '계약' ? styles.good : ''}`}>
                      {other.status}
                    </i>
                  </button>
                ))}
              </div>
            </Block>
          )}
        </div>
      </div>
    </Drawer>
  )
}

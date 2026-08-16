// demo/layout_v3.html 의 #recordDrawer 입니다.
// 일정 하나에 대해 알아야 할 것을 한 장에 모읍니다. 위는 세부 정보(왼쪽)와
// 지난 접촉(오른쪽), 가운데는 이 건의 계약·발주가 어디까지 왔는지,
// 아래는 브리핑을 한 줄로 넓게 깝니다.
//
// 보고서 작성 폼은 여기 넣지 않습니다. 미팅 기록은 첨부와 AI 구조화가 붙어
// 드로어 한 장에 담기지 않으므로 하단 버튼으로 작성 화면으로 넘깁니다.
// 사내 업무는 미팅보고서가 아니라 그날 일일업무보고로 넘어갑니다(shared/agendaReport).
import { useState } from 'react'
import { Link } from 'react-router'

import Drawer from '@/components/Drawer'
import Popover from '@/components/Popover'
import { EditIcon, MoreIcon, TrashIcon } from '@/components/icons'
import StageBar from '@/components/StageBar'
import { endTime, statusScope } from '@/shared/agenda'
import { contracts } from '@/shared/contracts'
import { activeOrders, orders } from '@/shared/orders'
import type { AgendaItem, Contract } from '@/types'
import { useAgendaReportLink } from '@/shared/agendaReport'
import { contractPath, orderPath } from '@/constants/routes'
import { initialCards, STAGE_NAMES, stageIndexOf } from '@/pages/Visits/board'
import { ORDER_STEPS, stepOf } from '@/pages/Orders/pipeline'
import { won } from '@/utils/format'
import { fmtDay, parseISO } from '@/utils/date'

import styles from './RecordDrawer.module.scss'

/** 히스토리는 최근 것부터 이 개수까지만 폅니다. 나머지는 줄 수로만 알립니다. */
const HISTORY_LIMIT = 3

/**
 * 계약의 단계. 계약 시드에는 단계가 없어 보드가 세우는 배치를 그대로 빌립니다.
 * 보드와 같은 결정적 계산이라 두 화면이 어긋나지 않습니다.
 */
const STAGE_BY_NO = new Map(initialCards().map((card) => [card.no, card.stageId]))

/**
 * 아직 굴러가는 계약인가.
 *
 * 협의 중이면 당연히 진행 중입니다. 확정된 건은 납품이 남았을 때만 진행 중으로 봅니다.
 * 확정인데 발주조차 없는 옛 계약은 이미 끝난 것으로 두고 드로어에 올리지 않습니다.
 */
function isOpenContract(contract: Contract): boolean {
  if (contract.status === '진행중') return true
  if (contract.status !== '확정') return false
  const stage = STAGE_BY_NO.get(contract.no)
  return stage === 'won' && orders.some((o) => o.contract === contract.no && o.status !== '취소')
}

interface Props {
  item: AgendaItem
  done: boolean
  onClose: () => void
  /** 넘기면 머리말에 '...' 메뉴가 붙습니다. 고칠 수 없는 화면에서는 비워 둡니다. */
  onEdit?: (item: AgendaItem) => void
  onDelete?: (id: string) => void
}

export default function RecordDrawer({ item, done, onClose, onEdit, onDelete }: Props) {
  // 펼친 단계. 한 번에 하나만 펴야 드로어가 길어지지 않습니다.
  const [openStage, setOpenStage] = useState(-1)
  const [openStep, setOpenStep] = useState(-1)
  const [menuOpen, setMenuOpen] = useState(false)

  // 이 일정에 이미 쓴 보고서가 있으면 새로 쓰지 않고 그것을 엽니다.
  const report = useAgendaReportLink()(item)
  // 사내 업무는 고객이 없습니다. 고객 쪽 어휘를 쓰는 자리들을 걷어냅니다.
  const task = item.kind === 'internal'
  const until = task ? endTime(item.time, item.dur) : ''

  // 담당자는 '박서준 교수' 처럼 이름과 직책이 한 칸에 붙어 있습니다. 마지막 띄어쓰기에서 가릅니다.
  const at = item.contact.lastIndexOf(' ')
  // 사내 업무는 고객 쪽 칸이 통째로 비어 있습니다. 빈 줄은 아예 걸지 않습니다.
  const facts: [string, string][] = (
    [
      ['부서', item.dept],
      ['담당자', at < 0 ? item.contact : item.contact.slice(0, at)],
      ['직책', item.contact && at >= 0 ? item.contact.slice(at + 1) : ''],
      ['제품', item.product],
      ['장소', item.place],
    ] as [string, string][]
  ).filter(([, value]) => value !== '')

  const history = item.history.slice(0, HISTORY_LIMIT)
  const restCount = item.history.length - history.length

  // 이 병원에서 아직 굴러가는 건만 봅니다. 지난 계약까지 걸면 큰 병원은 서른 줄이 넘습니다.
  const openContracts = contracts.filter((c) => c.org === item.hospital && isOpenContract(c))
  const openOrders = activeOrders().filter(
    (o) => o.hospital === item.hospital && o.status !== '납품 완료',
  )

  const contractsAt = (stage: number) =>
    openContracts.filter((c) => stageIndexOf(STAGE_BY_NO.get(c.no) ?? '') === stage)
  const ordersAt = (step: number) => openOrders.filter((o) => stepOf(o.status) === step)

  return (
    <Drawer
      wide
      title={item.hospital || item.title}
      sub={
        // 업무는 제목이 이미 머리말이라, 아래 줄은 언제 하는 일인지만 말합니다.
        task ? (
          <span className={styles.when}>
            {fmtDay(parseISO(item.date))} {item.time}
            {until && ` – ${until}`}
          </span>
        ) : (
          <>
            {item.title}
            <span className={styles.when}>
              · {fmtDay(parseISO(item.date))} {item.time}
            </span>
          </>
        )
      }
      onClose={onClose}
      actions={
        (onEdit || onDelete) && (
          <Popover
            open={menuOpen}
            onClose={() => setMenuOpen(false)}
            align="end"
            compact
            label="일정 메뉴"
            trigger={
              <button
                type="button"
                className={styles.menuBtn}
                aria-label="일정 메뉴"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((v) => !v)}
              >
                <MoreIcon width={18} height={18} />
              </button>
            }
          >
            <div className={styles.menu}>
              {onEdit && (
                <button type="button" onClick={() => onEdit(item)}>
                  <EditIcon width={15} height={15} />
                  수정
                </button>
              )}
              {onDelete && (
                <button type="button" className={styles.danger} onClick={() => onDelete(item.id)}>
                  <TrashIcon width={15} height={15} />
                  삭제
                </button>
              )}
            </div>
          </Popover>
        )
      }
      meta={
        <>
          {/* 배지는 DayAgenda 목록과 종류·순서·색이 모두 같아야 합니다.
              목록에서 본 줄을 그대로 펼친 것으로 읽혀야 하기 때문입니다. */}
          {task && <i className={`${styles.pill} ${styles.taskTag}`}>업무</i>}
          {item.stage && (
            <i
              className={`${styles.pill} ${statusScope(item.stage) === '외부' ? styles.scopeExternal : ''}`}
            >
              {item.stage}
            </i>
          )}
          {done && <i className={`${styles.pill} ${styles.doneTag}`}>완료</i>}
          {done && !report.written && (
            <i className={`${styles.pill} ${styles.needsReport}`}>보고서 미작성</i>
          )}
        </>
      }
      footer={
        // 완료는 목록 줄의 버튼에서 정합니다. 여기는 읽는 자리라 배지로만 둡니다.
        <Link className={styles.cta} to={report.to}>
          {report.label}
        </Link>
      }
    >
      <div className={styles.grid}>
        {facts.length > 0 && (
          <section className={styles.block}>
            <h3>세부 정보</h3>
            <dl className={styles.facts}>
              {facts.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {history.length > 0 && (
          <section className={styles.block}>
            <h3>최근 미팅 히스토리</h3>
            {history.map((h) => (
              <div key={`${h.when}-${h.what}`} className={styles.history}>
                <time>{h.when}</time>
                <p>{h.what}</p>
              </div>
            ))}
            {restCount > 0 && <p className={styles.more}>외 {restCount}건</p>}
          </section>
        )}

        {/* 단계는 칸이 많아 두 열을 가로질러야 이름이 겹치지 않습니다. */}
        {openContracts.length > 0 && (
          <section className={`${styles.block} ${styles.full}`}>
            <h3>
              계약 진행
              <span className={`${styles.total} tnum`}>{openContracts.length}건</span>
            </h3>
            <StageBar
              steps={STAGE_NAMES}
              counts={STAGE_NAMES.map((_, i) => contractsAt(i).length)}
              selected={openStage}
              onSelect={setOpenStage}
              label="계약 단계별 건수"
            />
            {openStage >= 0 && (
              <ul className={styles.picks}>
                <li className={styles.picksHead}>
                  <b>{STAGE_NAMES[openStage]}</b> 단계 계약 {contractsAt(openStage).length}건
                </li>
                {contractsAt(openStage).map((c) => (
                  <li key={c.no}>
                    <Link className={styles.pick} to={contractPath(c.no)}>
                      <b>{c.product}</b>
                      <span className={styles.sub}>
                        {c.no} · {c.kind} · {c.owner}
                      </span>
                      <span className={`${styles.amount} tnum`}>{won(c.amount)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {openOrders.length > 0 && (
          <section className={`${styles.block} ${styles.full}`}>
            <h3>
              발주 진행
              <span className={`${styles.total} tnum`}>{openOrders.length}건</span>
            </h3>
            <StageBar
              steps={ORDER_STEPS}
              counts={ORDER_STEPS.map((_, i) => ordersAt(i).length)}
              selected={openStep}
              onSelect={setOpenStep}
              label="발주 단계별 건수"
            />
            {openStep >= 0 && (
              <ul className={styles.picks}>
                <li className={styles.picksHead}>
                  <b>{ORDER_STEPS[openStep]}</b> 단계 발주 {ordersAt(openStep).length}건
                </li>
                {ordersAt(openStep).map((o) => (
                  <li key={o.no}>
                    <Link className={styles.pick} to={orderPath(o.no)}>
                      <b>{o.items.map((it) => it.product).join(', ')}</b>
                      <span className={styles.sub}>
                        {o.no} · {o.supplier}
                      </span>
                      <span className={styles.amount}>납기 {fmtDay(parseISO(o.due))}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {/* 브리핑은 문장이 길어 두 열을 가로질러 한 줄로 깝니다. */}
        {item.brief && (
          <section className={`${styles.block} ${styles.full}`}>
            <h3>{task ? '메모' : 'AI 미팅 요약'}</h3>
            <p className={styles.note}>{item.brief}</p>
          </section>
        )}
      </div>
    </Drawer>
  )
}

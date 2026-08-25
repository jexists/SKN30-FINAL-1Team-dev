import { useState } from 'react'
import { Link } from 'react-router'

import Button, { buttonClass } from '@/components/Button'
import Drawer from '@/components/Drawer'
import Popover from '@/components/Popover'
import Skeleton, { InlineLoader } from '@/components/Skeleton'
import { EditIcon, MoreIcon, TrashIcon } from '@/components/icons'
import { orderPath } from '@/constants/routes'
import { endTime, statusScope } from '@/shared/agenda'
import { useAgendaReportLink } from '@/shared/agendaReport'
import type { AgendaItem } from '@/types'
import { fmtDay, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import { useRelatedDeal } from '../../useDashboard'

import styles from './RecordDrawer.module.scss'

interface Props {
  item: AgendaItem
  onClose: () => void
  onEdit?: (item: AgendaItem) => void
  onDelete?: (id: string) => void
}

export default function RecordDrawer({ item, onClose, onEdit, onDelete }: Props) {
  // 관련 영업·발주는 이 드로어를 열 때만 받아 옵니다.
  const {
    deal,
    orders: relatedOrders,
    orderTotal,
    hasMoreOrders,
    loadingMoreOrders,
    loadMoreOrders,
    loading: relatedLoading,
    error: relatedError,
    reload: onRetryRelated,
  } = useRelatedDeal(item.salesDealId ?? null)
  const done = item.done
  const [menuOpen, setMenuOpen] = useState(false)
  // 드로어는 눌러야 열리므로 여기서 물어보는 것이 곧 온디맨드입니다.
  const reportState = useAgendaReportLink(item)
  const task = item.kind === 'internal'
  const until = task ? endTime(item.time, item.dur) : ''
  const at = item.contact.lastIndexOf(' ')
  const facts: [string, string][] = (
    [
      ['부서', item.dept],
      ['담당자', at < 0 ? item.contact : item.contact.slice(0, at)],
      ['직책', item.contact && at >= 0 ? item.contact.slice(at + 1) : ''],
      ['제품', item.product],
      ['장소', item.place],
    ] as [string, string][]
  ).filter(([, value]) => value !== '')
  return (
    <Drawer
      wide
      title={item.hospital || item.title}
      sub={
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
                onClick={() => setMenuOpen((value) => !value)}
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
          {task && <i className={`${styles.pill} ${styles.taskTag}`}>업무</i>}
          {item.stage && (
            <i
              className={`${styles.pill} ${statusScope(item.stage) === '외부' ? styles.scopeExternal : ''}`}
            >
              {item.stage}
            </i>
          )}
          {done && <i className={`${styles.pill} ${styles.doneTag}`}>완료</i>}
          {done && reportState.link && !reportState.link.written && (
            <i className={`${styles.pill} ${styles.needsReport}`}>보고서 미작성</i>
          )}
        </>
      }
      footer={
        reportState.error ? (
          <Button variant="outline" onClick={reportState.reload}>
            보고서 다시 조회
          </Button>
        ) : reportState.link ? (
          <Link className={buttonClass()} to={reportState.link.to}>
            {reportState.link.label}
          </Link>
        ) : (
          <InlineLoader label="보고서 연결을 확인하는 중입니다." />
        )
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

        {relatedError ? (
          <section className={`${styles.block} ${styles.full}`} role="alert">
            <h3>관련 영업·발주</h3>
            <p className={styles.note}>{relatedError}</p>
            <Button variant="outline" size="sm" onClick={onRetryRelated}>
              다시 시도
            </Button>
          </section>
        ) : relatedLoading ? (
          <section className={`${styles.block} ${styles.full}`} role="status">
            <h3>관련 영업·발주</h3>
            <span className="sr-only">관련 영업·발주를 불러오는 중입니다.</span>
            <Skeleton height={104} radius="var(--r-md)" />
          </section>
        ) : (
          <>
            {deal && (
              <section className={`${styles.block} ${styles.full}`}>
                <h3>관련 영업</h3>
                <dl className={styles.facts}>
                  <div>
                    <dt>영업번호</dt>
                    <dd>{deal.no}</dd>
                  </div>
                  <div>
                    <dt>단계</dt>
                    <dd>{deal.stageName}</dd>
                  </div>
                  <div>
                    <dt>계약번호</dt>
                    <dd>{deal.contractNo ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>금액</dt>
                    <dd className="tnum">{won(deal.amount)}</dd>
                  </div>
                </dl>
              </section>
            )}

            {relatedOrders.length > 0 && (
              <section className={`${styles.block} ${styles.full}`}>
                <h3>
                  관련 발주
                  <span className={`${styles.total} tnum`}>{orderTotal}건</span>
                </h3>
                <ul className={styles.picks}>
                  {relatedOrders.map((order) => (
                    <li key={order.id}>
                      <Link className={styles.pick} to={orderPath(order.no)}>
                        <b>{order.items.map((line) => line.product).join(', ') || '상품 미지정'}</b>
                        <span className={styles.sub}>
                          {order.no} · {order.status}
                        </span>
                        <span className={styles.amount}>납기 {fmtDay(parseISO(order.due))}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
                {hasMoreOrders && (
                  <button
                    type="button"
                    className={styles.more}
                    disabled={loadingMoreOrders}
                    onClick={loadMoreOrders}
                  >
                    {loadingMoreOrders
                      ? '불러오는 중입니다…'
                      : `${orderTotal - relatedOrders.length}건 더 보기`}
                  </button>
                )}
              </section>
            )}
          </>
        )}

        {item.brief && (
          <section className={`${styles.block} ${styles.full}`}>
            <h3>{task ? '메모' : '미팅 메모'}</h3>
            <p className={styles.note}>{item.brief}</p>
          </section>
        )}
      </div>
    </Drawer>
  )
}

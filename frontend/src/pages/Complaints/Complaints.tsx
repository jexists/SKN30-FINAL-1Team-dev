// 고객불만관리. 대시보드 KPI 타일 'C/S 대응요청' 이 보여 주는 그 목록의 본화면입니다.
// 목록은 shared/counters.ts 한 곳에 있어, 여기서 등록하거나 상태를 바꾸면 대시보드
// 타일 숫자와 드로어 줄이 함께 바뀝니다.
//
// 조건은 주소에 둡니다(q·status). 걸러 둔 채로 링크를 건네면 받는 쪽도 같은 화면을 봅니다.
import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { ComplaintIcon, PlusIcon, SearchIcon } from '@/components/icons'
import { BP_DESKTOP } from '@/constants/breakpoints'
import { addCsRequest, setCsState, useCsRequests } from '@/shared/counters'
import type { CsRequest, CsState } from '@/types'
import useMediaQuery from '@/hooks/useMediaQuery'
import { addDays, fmtDay, fmtDotShort, TODAY } from '@/utils/date'

import ComplaintFormModal from './components/ComplaintFormModal'

import styles from './Complaints.module.scss'

/** 상태 두 가지. 탭 순서와 배지 색이 여기에 묶여 있습니다. */
const STATES: CsState[] = ['처리중', '처리완료']

// 표가 화면보다 넓으면 이 폭 그대로, 좁으면 이 폭의 비율로 늘어납니다(table-layout: fixed).
// 남는 자리는 잘리면 아쉬운 '내용'이 가져가고 상태·날짜는 좁게 붙잡아 둡니다.
const COLUMNS = [
  { id: 'org', header: '회사', width: 150 },
  { id: 'owner', header: '담당자', width: 90 },
  { id: 'issue', header: '제목', width: 230 },
  { id: 'note', header: '내용', width: 560 },
  { id: 'state', header: '상태', width: 92 },
  { id: 'created', header: '등록날짜', width: 104 },
]

/** 접수한 날. agoOff 가 오늘로부터 며칠 전인지를 들고 있습니다. */
const createdAt = (c: CsRequest) => addDays(TODAY, c.agoOff)

export default function Complaints() {
  const complaints = useCsRequests()

  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const status = params.get('status') ?? ''

  // 타이핑 중에도 입력이 밀리지 않도록 목록 계산만 한 박자 늦춥니다.
  const deferredQuery = useDeferredValue(query)

  const [openId, setOpenId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  const isDesktop = useMediaQuery(`(min-width: ${BP_DESKTOP}px)`)

  // 기본값은 쿼리에서 지웁니다. 주소를 복사했을 때 조건이 그대로 살아나되 짧게 남습니다.
  const setParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params)
      if (value === '') next.delete(key)
      else next.set(key, value)
      setParams(next, { replace: true })
    },
    [params, setParams],
  )

  // 상태를 뺀 나머지 조건까지만 거른 목록입니다. 탭의 건수를 여기서 셉니다.
  const beforeStatus = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase()
    if (needle === '') return complaints
    return complaints.filter((c) =>
      [c.issue, c.org, c.owner, c.note].join(' ').toLowerCase().includes(needle),
    )
  }, [complaints, deferredQuery])

  const rows = useMemo(
    () => (status === '' ? beforeStatus : beforeStatus.filter((c) => c.state === status)),
    [beforeStatus, status],
  )

  // 객체가 아니라 id 를 들고 목록에서 찾습니다. 상태를 바꾸면 새 객체가 되므로
  // 열어 둔 드로어가 바뀐 값을 그대로 받습니다.
  const open = openId ? complaints.find((c) => c.id === openId) : undefined

  const isFiltered = query.trim() !== '' || status !== ''

  return (
    <section className={styles.page}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">고객불만관리</h1>

      <div className={styles.toolbar}>
        <label className={styles.search}>
          <SearchIcon width={16} height={16} />
          <input
            value={query}
            placeholder="제목·회사·담당자·내용 검색"
            aria-label="고객불만 검색"
            onChange={(event) => setParam('q', event.target.value)}
          />
        </label>

        <div className={styles.actions}>
          <Button onClick={() => setAdding(true)}>
            <PlusIcon width={15} height={15} />
            불만 등록
          </Button>
        </div>
      </div>

      <div className={styles.tabs} role="tablist" aria-label="처리 상태">
        <Tab
          label="전체"
          count={beforeStatus.length}
          on={status === ''}
          onSelect={() => setParam('status', '')}
        />
        {STATES.map((state) => (
          <Tab
            key={state}
            label={state}
            count={beforeStatus.filter((c) => c.state === state).length}
            tone={state}
            on={status === state}
            onSelect={() => setParam('status', state)}
          />
        ))}
      </div>

      {rows.length === 0 ? (
        <div className={styles.card}>
          <div className={styles.empty}>
            {isFiltered ? (
              <>
                <SearchIcon width={34} height={34} strokeWidth={1.5} />
                <p>조건에 맞는 고객불만이 없습니다.</p>
                <Button variant="outline" onClick={() => setParams(new URLSearchParams())}>
                  검색·필터 초기화
                </Button>
              </>
            ) : (
              <>
                <ComplaintIcon width={34} height={34} strokeWidth={1.5} />
                <p>접수된 고객불만이 없습니다.</p>
                <Button onClick={() => setAdding(true)}>불만 등록</Button>
              </>
            )}
          </div>
        </div>
      ) : isDesktop ? (
        // 표와 카드는 마크업 자체가 다릅니다. CSS 로는 한쪽을 숨기는 것밖에 못 해
        // 폰에서도 여섯 열짜리 DOM 을 그대로 들고 있게 됩니다.
        <div className={styles.card}>
          <div className={styles.scroller}>
            <table
              className={styles.table}
              style={{ width: COLUMNS.reduce((sum, col) => sum + col.width, 0) }}
            >
              <caption className="sr-only">고객불만 목록. 줄을 누르면 상세가 열립니다.</caption>

              <colgroup>
                {COLUMNS.map((col) => (
                  <col key={col.id} style={{ width: col.width }} />
                ))}
              </colgroup>

              <thead>
                <tr>
                  {COLUMNS.map((col) => (
                    <th key={col.id} scope="col">
                      {col.header}
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className={styles.clickable} onClick={() => setOpenId(c.id)}>
                    <td title={c.org}>
                      {/* 줄 전체를 누르지만 tr 은 키보드로 못 잡습니다. 첫 칸이
                          그 손잡이이고, 하는 일은 줄을 누른 것과 같습니다. */}
                      <button
                        type="button"
                        className={styles.openButton}
                        onClick={(event) => {
                          event.stopPropagation()
                          setOpenId(c.id)
                        }}
                      >
                        {c.org}
                      </button>
                    </td>
                    <td title={c.owner}>{c.owner}</td>
                    <td className={styles.issue} title={c.issue}>
                      {c.issue}
                    </td>
                    <td className={styles.note} title={c.note}>
                      {c.note}
                    </td>
                    <td>
                      <StateBadge state={c.state} />
                    </td>
                    <td className={`${styles.date} tnum`}>{fmtDotShort(createdAt(c))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <ul className={styles.cardList}>
          {rows.map((c) => (
            <li key={c.id} className={styles.miniCard} onClick={() => setOpenId(c.id)}>
              {/* 표와 같은 순서로 읽힙니다 — 회사·담당자 다음에 제목·내용. */}
              <div className={styles.miniHead}>
                <button type="button" className={styles.openButton} onClick={() => setOpenId(c.id)}>
                  {c.org}
                </button>
                <StateBadge state={c.state} />
              </div>
              <p className={styles.miniIssue}>{c.issue}</p>
              <p className={styles.miniNote}>{c.note}</p>
              <div className={styles.miniMeta}>
                <span>{c.owner}</span>
                <span className="tnum">{fmtDotShort(createdAt(c))}</span>
              </div>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <Drawer
          title={open.issue}
          sub={open.org}
          onClose={() => setOpenId(null)}
          meta={
            <>
              <StateBadge state={open.state} />
              {open.urgent && <i className={`${styles.badge} ${styles.risk}`}>긴급</i>}
            </>
          }
          footer={
            open.state === '처리중' ? (
              <Button onClick={() => setCsState(open.id, '처리완료')}>처리완료로 변경</Button>
            ) : (
              <Button variant="outline" onClick={() => setCsState(open.id, '처리중')}>
                처리중으로 되돌리기
              </Button>
            )
          }
        >
          <dl className={styles.rows}>
            {/* 화면에서 등록한 건에는 접수자가 없습니다. 있는 값만 늘어놓습니다. */}
            {(
              [
                ['회사', open.org],
                ['담당자', open.owner],
                ['접수자', open.who],
                ['물품명', open.product],
                ['등록날짜', `${fmtDay(createdAt(open))} · ${open.ago}`],
                ['내용', open.note],
              ] as [string, string][]
            )
              .filter(([, value]) => value !== '')
              .map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
          </dl>
        </Drawer>
      )}

      {adding && (
        <ComplaintFormModal
          onClose={() => setAdding(false)}
          onSubmit={(draft) => {
            const created = addCsRequest(draft)
            setAdding(false)
            // 방금 등록한 건이 걸러져 보이지 않으면 저장됐는지 알 수 없습니다.
            if (status !== '' && status !== created.state) setParam('status', created.state)
          }}
        />
      )}
    </section>
  )
}

function StateBadge({ state }: { state: CsState }) {
  return (
    <i className={`${styles.badge} ${state === '처리완료' ? styles.done : styles.working}`}>
      {state}
    </i>
  )
}

interface TabProps {
  label: string
  count: number
  /** 목록 배지와 같은 색 점. '전체' 탭에는 없습니다. */
  tone?: CsState
  on: boolean
  onSelect: () => void
}

function Tab({ label, count, tone, on, onSelect }: TabProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={on}
      className={[styles.tab, on ? styles.isActive : ''].filter(Boolean).join(' ')}
      onClick={onSelect}
    >
      {tone && (
        <i
          className={`${styles.dot} ${tone === '처리완료' ? styles.done : styles.working}`}
          aria-hidden="true"
        />
      )}
      {label}
      <span className={`${styles.count} tnum`}>{count}</span>
    </button>
  )
}

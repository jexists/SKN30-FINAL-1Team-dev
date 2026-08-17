import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { ComplaintIcon, PlusIcon, SearchIcon } from '@/components/icons'
import SearchInput from '@/components/SearchInput'
import Tabs, { type TabItem } from '@/components/Tabs'
import { BP_DESKTOP } from '@/constants/breakpoints'
import useMediaQuery from '@/hooks/useMediaQuery'
import type {
  ColumnTone,
  SupportRequestResponse,
  SupportStatusCode,
  SupportResponseResponse,
} from '@/types'
import { fmtDotShort } from '@/utils/date'

import ComplaintFormModal from './components/ComplaintFormModal'
import useSupportRequests from './useSupportRequests'

import styles from './Complaints.module.scss'

const STATES: { code: SupportStatusCode; label: string; tone: ColumnTone }[] = [
  { code: 'in_progress', label: '처리중', tone: 'blue' },
  { code: 'completed', label: '처리완료', tone: 'green' },
]

const STATUS_LABEL: Record<SupportStatusCode, string> = {
  in_progress: '처리중',
  completed: '처리완료',
}

const COLUMNS = [
  { id: 'org', header: '회사', width: 150 },
  { id: 'owner', header: '담당자', width: 90 },
  { id: 'issue', header: '제목', width: 230 },
  { id: 'note', header: '내용', width: 560 },
  { id: 'state', header: '상태', width: 92 },
  { id: 'created', header: '등록날짜', width: 104 },
]

const dateOf = (value: string) => new Date(value)

const dateTime = new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

export default function Complaints() {
  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const status = params.get('status') ?? ''
  const deferredQuery = useDeferredValue(query)

  const [openId, setOpenId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const isDesktop = useMediaQuery(`(min-width: ${BP_DESKTOP}px)`)

  const {
    requests,
    contacts,
    loading,
    error,
    reload,
    detail,
    detailLoading,
    detailError,
    reloadDetail,
    pendingKey,
    mutationError,
    clearMutationError,
    createRequest,
    transition,
    addResponse,
  } = useSupportRequests(openId)

  const setParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params)
      if (value === '') next.delete(key)
      else next.set(key, value)
      setParams(next, { replace: true })
    },
    [params, setParams],
  )

  const beforeStatus = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase()
    if (needle === '') return requests
    return requests.filter((request) =>
      [
        request.title,
        request.body,
        request.customer_company_name,
        request.customer_contact_name,
        request.assignee_display_name,
      ]
        .join(' ')
        .toLowerCase()
        .includes(needle),
    )
  }, [requests, deferredQuery])

  const rows = useMemo(
    () =>
      status === ''
        ? beforeStatus
        : beforeStatus.filter((request) => request.status_code === status),
    [beforeStatus, status],
  )

  const statusTabs = useMemo<TabItem[]>(
    () => [
      { value: '', label: '전체', count: beforeStatus.length },
      ...STATES.map((state) => ({
        value: state.code,
        label: state.label,
        count: beforeStatus.filter((request) => request.status_code === state.code).length,
        tone: state.tone,
      })),
    ],
    [beforeStatus],
  )

  const summary = openId === null ? undefined : requests.find((request) => request.id === openId)
  const open = detail?.id === openId ? detail : summary
  const isFiltered = query.trim() !== '' || status !== ''

  const closeDrawer = useCallback(() => {
    setOpenId(null)
    clearMutationError()
  }, [clearMutationError])

  return (
    <section className={styles.page} aria-busy={loading}>
      <h1 className="sr-only">고객불만관리</h1>

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="제목·회사·담당자·내용 검색"
          label="고객불만 검색"
          onChange={(next) => setParam('q', next)}
        />

        <div className={styles.actions}>
          <Button disabled={loading} onClick={() => setAdding(true)}>
            <PlusIcon width={15} height={15} />
            불만 등록
          </Button>
        </div>
      </div>

      <Tabs
        items={statusTabs}
        value={status}
        label="처리 상태"
        onChange={(next) => setParam('status', next)}
      />

      {error ? (
        <div className={styles.loadState} role="alert">
          <p>{error}</p>
          <Button variant="outline" onClick={reload}>
            다시 시도
          </Button>
        </div>
      ) : loading && requests.length === 0 ? (
        <p className={styles.loadState} role="status">
          고객불만 목록을 불러오는 중입니다.
        </p>
      ) : rows.length === 0 ? (
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
        <div className={styles.card}>
          <div className={styles.scroller}>
            <table
              className={styles.table}
              style={{ width: COLUMNS.reduce((sum, column) => sum + column.width, 0) }}
            >
              <caption className="sr-only">고객불만 목록. 줄을 누르면 상세가 열립니다.</caption>
              <colgroup>
                {COLUMNS.map((column) => (
                  <col key={column.id} style={{ width: column.width }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  {COLUMNS.map((column) => (
                    <th key={column.id} scope="col">
                      {column.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((request) => (
                  <tr
                    key={request.id}
                    className={styles.clickable}
                    onClick={() => setOpenId(request.id)}
                  >
                    <td title={request.customer_company_name}>
                      <button
                        type="button"
                        className={styles.openButton}
                        onClick={(event) => {
                          event.stopPropagation()
                          setOpenId(request.id)
                        }}
                      >
                        {request.customer_company_name}
                      </button>
                    </td>
                    <td title={request.assignee_display_name}>{request.assignee_display_name}</td>
                    <td className={styles.issue} title={request.title}>
                      {request.title}
                    </td>
                    <td className={styles.note} title={request.body}>
                      {request.body}
                    </td>
                    <td>
                      <StateBadge state={request.status_code} />
                    </td>
                    <td className={`${styles.date} tnum`}>
                      {fmtDotShort(dateOf(request.registered_at))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <ul className={styles.cardList}>
          {rows.map((request) => (
            <li key={request.id} className={styles.miniCard} onClick={() => setOpenId(request.id)}>
              <div className={styles.miniHead}>
                <button
                  type="button"
                  className={styles.openButton}
                  onClick={() => setOpenId(request.id)}
                >
                  {request.customer_company_name}
                </button>
                <StateBadge state={request.status_code} />
              </div>
              <p className={styles.miniIssue}>{request.title}</p>
              <p className={styles.miniNote}>{request.body}</p>
              <div className={styles.miniMeta}>
                <span>{request.assignee_display_name}</span>
                <span className="tnum">{fmtDotShort(dateOf(request.registered_at))}</span>
              </div>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <Drawer
          title={open.title}
          sub={`${open.customer_company_name} · ${open.customer_contact_name}`}
          onClose={closeDrawer}
          meta={
            <>
              <StateBadge state={open.status_code} />
              {open.is_urgent && <i className={`${styles.badge} ${styles.risk}`}>긴급</i>}
            </>
          }
          footer={
            detail?.id === open.id ? (
              <Button
                variant={detail.status_code === 'in_progress' ? 'primary' : 'outline'}
                disabled={pendingKey !== null}
                onClick={() =>
                  void transition(
                    detail,
                    detail.status_code === 'in_progress' ? 'completed' : 'in_progress',
                  )
                }
              >
                {pendingKey === `transition:${open.id}`
                  ? '변경 중…'
                  : detail.status_code === 'in_progress'
                    ? '처리완료로 변경'
                    : '처리중으로 되돌리기'}
              </Button>
            ) : undefined
          }
        >
          {detailError ? (
            <div className={styles.loadState} role="alert">
              <p>{detailError}</p>
              <Button variant="outline" onClick={reloadDetail}>
                다시 시도
              </Button>
            </div>
          ) : detailLoading || detail?.id !== open.id ? (
            <p className={styles.loadState} role="status">
              상세 내용을 불러오는 중입니다.
            </p>
          ) : (
            <>
              <dl className={styles.rows}>
                <div>
                  <dt>회사</dt>
                  <dd>{detail.customer_company_name}</dd>
                </div>
                <div>
                  <dt>고객 담당자</dt>
                  <dd>{detail.customer_contact_name}</dd>
                </div>
                <div>
                  <dt>처리 담당자</dt>
                  <dd>{detail.assignee_display_name}</dd>
                </div>
                <div>
                  <dt>등록일시</dt>
                  <dd>{dateTime.format(dateOf(detail.registered_at))}</dd>
                </div>
                <div>
                  <dt>내용</dt>
                  <dd>{detail.body}</dd>
                </div>
              </dl>

              <ResponseHistory
                key={detail.id}
                request={detail}
                pending={pendingKey === `response:${detail.id}`}
                error={mutationError}
                onClearError={clearMutationError}
                onSubmit={(body) => addResponse(detail.id, body)}
              />
            </>
          )}
        </Drawer>
      )}

      {adding && (
        <ComplaintFormModal
          contacts={contacts}
          onClose={() => setAdding(false)}
          onSubmit={async (payload) => {
            const created = await createRequest(payload)
            setAdding(false)
            if (status !== '' && status !== created.status_code) {
              setParam('status', created.status_code)
            }
          }}
        />
      )}
    </section>
  )
}

function StateBadge({ state }: { state: SupportStatusCode }) {
  return (
    <i className={`${styles.badge} ${state === 'completed' ? styles.done : styles.working}`}>
      {STATUS_LABEL[state]}
    </i>
  )
}

interface ResponseHistoryProps {
  request: SupportRequestResponse
  pending: boolean
  error: string | null
  onClearError: () => void
  onSubmit: (body: string) => Promise<boolean>
}

function ResponseHistory({
  request,
  pending,
  error,
  onClearError,
  onSubmit,
}: ResponseHistoryProps) {
  const [body, setBody] = useState('')
  const [bodyError, setBodyError] = useState<string | null>(null)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    const value = body.trim()
    if (value === '') {
      setBodyError('답변 내용을 입력하세요.')
      return
    }

    if (await onSubmit(value)) setBody('')
  }

  return (
    <section className={styles.responses}>
      <h3>답변 이력</h3>
      {request.responses.length === 0 ? (
        <p className={styles.noResponses}>등록된 답변이 없습니다.</p>
      ) : (
        <ol>
          {request.responses.map((response: SupportResponseResponse) => (
            <li key={response.id}>
              <div>
                <strong>{response.responder_display_name}</strong>
                <time dateTime={response.responded_at}>
                  {dateTime.format(dateOf(response.responded_at))}
                </time>
              </div>
              <p>{response.body}</p>
            </li>
          ))}
        </ol>
      )}

      <form className={styles.responseForm} onSubmit={submit}>
        <label htmlFor={`response-${request.id}`}>답변 추가</label>
        <textarea
          id={`response-${request.id}`}
          rows={4}
          maxLength={5_000}
          value={body}
          disabled={pending}
          onChange={(event) => {
            setBody(event.target.value)
            setBodyError(null)
            onClearError()
          }}
        />
        {bodyError && (
          <p className={styles.error} role="alert">
            {bodyError}
          </p>
        )}
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <Button type="submit" disabled={pending}>
          {pending ? '등록 중…' : '답변 등록'}
        </Button>
      </form>
    </section>
  )
}

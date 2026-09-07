import { useState } from 'react'
import { useSearchParams } from 'react-router'

import Button from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import { BellIcon, PlusIcon, SearchIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import Pagination, { PAGE_SIZE } from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import { ListPageSkeleton, TableSkeleton } from '@/components/Skeleton'
import StatusBadge from '@/components/StatusBadge'
import Tabs from '@/components/Tabs'
import { progressLabel, rollupLabel } from '@/shared/noticeStatus'
import { showToast } from '@/shared/toast'
import type { NoticeManageListResponse, NoticeManageResponse, NoticeType } from '@/types'

import DirectiveStatusModal from './components/DirectiveStatusModal'
import NoticeFormModal from './components/NoticeFormModal'
import NoticeRowActions from './components/NoticeRowActions'
import {
  TYPE_TABS,
  columnsFor,
  periodLabel,
  stateOf,
  tableWidth,
  targetsLabel,
} from './noticeCatalog'
import useNotices from './useNotices'

import styles from './Notices.module.scss'

/** 열려 있는 폼. 등록은 initial 이 없고, 수정은 본문까지 받아 온 한 건을 답니다. */
type FormState = { mode: 'create' } | { mode: 'edit'; notice: NoticeManageResponse }

export default function Notices() {
  const [params, setParams] = useSearchParams()
  const type = (params.get('type') === 'DIRECTIVE' ? 'DIRECTIVE' : 'NOTICE') satisfies NoticeType
  const query = params.get('q') ?? ''
  const [page, setPage] = useState(1)
  const [form, setForm] = useState<FormState | null>(null)
  const [removing, setRemoving] = useState<NoticeManageListResponse | null>(null)
  const [progressOf, setProgressOf] = useState<NoticeManageListResponse | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  // 이행 현황 열은 지시사항 탭에만 섭니다. 공지 표는 지금 모양 그대로입니다.
  const columns = columnsFor(type)

  const {
    notices: rows,
    total,
    loading,
    error,
    reload,
    loadNotice,
    addNotice,
    editNotice,
    removeNotice,
    toggleHidden,
  } = useNotices({ type, q: query, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE })

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const patchParams = (change: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params)
    change(next)
    setParams(next, { replace: true })
    // 조건이 바뀌면 결과가 줄어 지금 쪽수가 범위를 넘을 수 있습니다. 첫 쪽으로 돌립니다.
    setPage(1)
  }

  const setType = (value: NoticeType) =>
    patchParams((next) => {
      if (value === 'NOTICE') next.delete('type')
      else next.set('type', value)
    })

  const setQuery = (value: string) =>
    patchParams((next) => {
      if (value === '') next.delete('q')
      else next.set('q', value)
    })

  // 목록에는 본문이 없습니다. 폼을 열 때 단건으로 받아 옵니다.
  const openEdit = async (row: NoticeManageListResponse) => {
    setBusyId(row.id)
    try {
      setForm({ mode: 'edit', notice: await loadNotice(row.id) })
    } catch {
      showToast('공지를 불러오지 못했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  const switchHidden = async (row: NoticeManageListResponse) => {
    setBusyId(row.id)
    try {
      await toggleHidden(row)
      showToast(row.is_hidden ? '다시 보이게 했습니다.' : '숨겼습니다.')
    } catch {
      showToast('상태를 바꾸지 못했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  const confirmRemove = async () => {
    if (removing === null) return
    setBusyId(removing.id)
    try {
      await removeNotice(removing.id)
      showToast('삭제했습니다.')
      setRemoving(null)
    } catch {
      showToast('삭제하지 못했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  // 첫 진입에서 툴바·표가 따로 들어오면 화면이 두 번 들썩입니다. 한 장을 통째로 둡니다.
  if (loading && rows.length === 0 && !error) {
    return (
      <section className={styles.page} aria-busy={loading}>
        <h1 className="sr-only">공지관리</h1>
        <ListPageSkeleton label="공지 목록을 불러오는 중입니다." />
      </section>
    )
  }

  return (
    <section className={styles.page} aria-busy={loading}>
      <h1 className="sr-only">공지관리</h1>

      <Tabs items={TYPE_TABS} value={type} label="공지 종류" onChange={setType} />

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="제목·본문·태그·작성자 검색"
          label="공지 검색"
          onSearch={setQuery}
        />
        <div className={styles.actions}>
          <Button disabled={loading} onClick={() => setForm({ mode: 'create' })}>
            <PlusIcon width={15} height={15} />
            {type === 'DIRECTIVE' ? '지시 등록' : '공지 등록'}
          </Button>
        </div>
      </div>

      <ErrorToast message={error} onRetry={reload} />

      {!error && loading ? (
        <TableSkeleton label="공지 목록을 새로고침하는 중입니다." rows={rows.length} />
      ) : rows.length === 0 ? (
        <div className={styles.card}>
          <div className={styles.empty}>
            {query.trim() !== '' ? (
              <>
                <SearchIcon width={34} height={34} strokeWidth={1.5} />
                <p>조건에 맞는 글이 없습니다.</p>
                <Button variant="outline" onClick={() => setQuery('')}>
                  검색 초기화
                </Button>
              </>
            ) : (
              <>
                <BellIcon width={34} height={34} strokeWidth={1.5} />
                <p>등록된 글이 없습니다.</p>
                <Button onClick={() => setForm({ mode: 'create' })}>
                  {type === 'DIRECTIVE' ? '지시 등록' : '공지 등록'}
                </Button>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className={styles.card}>
          {/* 좁은 화면에서는 표가 카드 안에서만 옆으로 흐릅니다. */}
          <div className={styles.scroller}>
            <table className={styles.table} style={{ width: tableWidth(columns) }}>
              <caption className="sr-only">등록된 공지·지시사항 목록</caption>
              <colgroup>
                {columns.map((column) => (
                  <col key={column.id} style={{ width: column.width }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={column.id} scope="col">
                      {column.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const state = stateOf(row)
                  return (
                    <tr key={row.id} className={row.is_hidden ? styles.isHidden : undefined}>
                      <td className="tnum">{row.sort_order}</td>
                      <td className={styles.title} title={row.title}>
                        {row.title}
                      </td>
                      <td>{row.tag === null ? '-' : <i className={styles.badge}>{row.tag}</i>}</td>
                      <td className={styles.targets} title={targetsLabel(row)}>
                        {targetsLabel(row)}
                      </td>
                      {/* 누가 했고 누가 못 했는지. 눌러서 사람별 상태와 사유를 봅니다. */}
                      {type === 'DIRECTIVE' && (
                        <td>
                          <button
                            type="button"
                            className={styles.progress}
                            onClick={() => setProgressOf(row)}
                            aria-label={`${row.title} 이행 현황 보기`}
                          >
                            <StatusBadge
                              label={rollupLabel(row.targets).label}
                              tone={rollupLabel(row.targets).tone}
                            />
                            <span className="tnum">{progressLabel(row.targets)}</span>
                          </button>
                        </td>
                      )}
                      <td className="tnum">{periodLabel(row)}</td>
                      <td>
                        <StatusBadge label={state.label} tone={state.tone} />
                      </td>
                      <td>{row.author_display_name}</td>
                      <td>
                        <NoticeRowActions
                          row={row}
                          busy={busyId === row.id}
                          onEdit={() => void openEdit(row)}
                          onToggleHidden={() => void switchHidden(row)}
                          onDelete={() => setRemoving(row)}
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <Pagination page={page} pageCount={pageCount} total={total} unit="건" onPage={setPage} />
        </div>
      )}

      {form !== null && (
        <NoticeFormModal
          initial={form.mode === 'edit' ? form.notice : undefined}
          defaultType={type}
          onClose={() => setForm(null)}
          onSubmit={async (payload) => {
            if (form.mode === 'edit') {
              await editNotice(form.notice.id, payload)
              showToast('수정했습니다.')
            } else {
              await addNotice(payload as Parameters<typeof addNotice>[0])
              showToast('등록했습니다.')
            }
            setForm(null)
          }}
        />
      )}

      {progressOf !== null && (
        <DirectiveStatusModal notice={progressOf} onClose={() => setProgressOf(null)} />
      )}

      {removing !== null && (
        <Modal
          title="공지를 삭제할까요?"
          description={`'${removing.title}' 이(가) 대시보드와 목록에서 사라집니다.`}
          onClose={() => setRemoving(null)}
          onSubmit={confirmRemove}
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                disabled={busyId !== null}
                onClick={() => setRemoving(null)}
              >
                취소
              </Button>
              <Button
                type="submit"
                variant="outline"
                className={styles.danger}
                disabled={busyId !== null}
              >
                삭제
              </Button>
            </>
          }
        >
          <p className={styles.hint}>지운 글은 목록에서 되살릴 수 없습니다.</p>
        </Modal>
      )}
    </section>
  )
}

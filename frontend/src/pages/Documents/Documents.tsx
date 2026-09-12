// 자료실. 영업이 돌려 보는 파일을 한 곳에 모읍니다. 화면 하나를 방 둘이 나눠 씁니다.
// 거래문서실은 딜에 딸린 견적·계약·발주를, 영업자료실은 상품설명서와 그 밖의 자료를 담습니다.
// 발주 목록과 같은 형태입니다: 검색·필터 → 분류 탭 → 표 → 상세 드로어.
//
// 조건은 주소에 둡니다(q·owner·range·category). 목록을 걸러 둔 채로 링크를 건네면
// 받는 쪽도 같은 화면을 봅니다. 정렬과 페이지는 보는 사람 사정이라 주소에 남기지 않습니다.
import { useCallback, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { errorMessage } from '@/api/errorMessage'
import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import FilterSelect from '@/components/FilterSelect'
import Modal from '@/components/Modal'
import { UploadIcon } from '@/components/icons'
import Pagination, { PAGE_SIZE } from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import { ListPageSkeleton, TableSkeleton } from '@/components/Skeleton'
import { useShowOwner } from '@/shared/scope'
import type { DocumentCategory } from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

import { fileOf, ROOMS, type RoomId } from './catalog'
import CategoryTabs from './components/CategoryTabs'
import DocumentDrawer from './components/DocumentDrawer'
import DocumentEditModal from './components/DocumentEditModal'
import DocumentTable from './components/DocumentTable'
import UploadModal, { type UploadResult } from './components/UploadModal'
import useDocuments, { type DocumentMeta } from './useDocuments'

import styles from './Documents.module.scss'

/** 기간 선택지. 값이 개월 수이고 0 이면 전체입니다. 발주 목록과 같은 어휘를 씁니다. */
const RANGES = [
  { value: '3', label: '최근 3개월' },
  { value: '6', label: '최근 6개월' },
  { value: '12', label: '최근 1년' },
  { value: '0', label: '전체' },
]

/** 기본 기간. 등록일 기준입니다. 자료는 오래 남으므로 발주보다 넉넉하게 잡습니다. */
const DEFAULT_RANGE = '12'

interface Props {
  /** 보고 있는 방. 담는 분류와 고를 수 있는 연결이 방마다 다릅니다. */
  room: RoomId
}

export default function Documents({ room }: Props) {
  const { label: roomLabel, categories } = ROOMS[room]

  // 자료는 팀원도 올립니다. 등록자 칸은 여러 사람이 섞여 보일 때만 세웁니다.
  // 등록자 필터는 보여 주는 것이 아니라 대상을 좁히는 조작이라 팀장에게 늘 둡니다.
  const { profile, memberId, isManager } = useCurrentUser()
  const showOwner = useShowOwner()

  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const owner = isManager ? (params.get('owner') ?? '') : ''
  const range = params.get('range') ?? DEFAULT_RANGE

  // 주소에 이 방이 담지 않는 분류가 적혀 있으면 전체로 봅니다. 없는 탭이 골라진 것처럼
  // 보이면서 목록만 비는 화면을 막습니다.
  const requested = params.get('category') ?? ''
  const category = (categories as readonly string[]).includes(requested) ? requested : ''

  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<string | null>(null)
  const [openFilter, setOpenFilter] = useState<'owner' | 'range' | null>(null)
  const [uploading, setUploading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  // 올리는 중에 몇 개째인지. 파일 하나가 요청 여러 번이라 개수가 보여야 합니다.
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null)
  // 방금 올려 서버가 접수한 파일들. 올린 직후의 행은 아직 접수 전 상태를 들고 있어서,
  // 이것이 없으면 드로어가 요약이 도는 중인 줄 모르고 "아직 요약이 없습니다"를 세웁니다.
  // 첫 자료만이 아니라 함께 올린 모두가 해당하므로 전부 들고 있습니다.
  const [queuedFileIds, setQueuedFileIds] = useState<string[]>([])

  // 기본값은 쿼리에서 지웁니다. 주소를 복사했을 때 조건이 그대로 살아나되 짧게 남습니다.
  // 조건이 바뀌면 첫 페이지로 돌아옵니다. 3페이지에 있다가 결과가 줄면 빈 화면을 봅니다.
  const setParam = useCallback(
    (key: string, value: string, fallback = '') => {
      const next = new URLSearchParams(params)
      if (value === fallback) next.delete(key)
      else next.set(key, value)
      setParams(next, { replace: true })
      setPage(1)
    },
    [params, setParams],
  )

  const fromISO = useMemo(() => {
    const months = Number(range)
    if (!months) return null
    return iso(addDays(TODAY, -Math.round(months * 30.4)))
  }, [range])

  const documentQuery = useMemo(
    () => ({
      q: query,
      room,
      category: category as DocumentCategory | '',
      uploaderMemberId: owner,
      fromISO,
      skip: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    }),
    [query, room, category, owner, fromISO, page],
  )

  const {
    documents: pageRows,
    total,
    counts,
    uploaders,
    findDocument,
    loading,
    error,
    pending,
    reload,
    addDocument,
    updateDocument,
    removeDocument,
    queueSummaries,
    summarizeFile,
    loadSummary,
    approveSummary,
  } = useDocuments(documentQuery)

  // 분류 탭 옆 건수는 서버가 셉니다. 고른 분류는 빼고 센 값입니다.
  const categoryCounts = useMemo(() => new Map(Object.entries(counts)), [counts])
  const categoryTotal = useMemo(
    () => [...categoryCounts.values()].reduce((sum, count) => sum + count, 0),
    [categoryCounts],
  )
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // 등록자 선택지. 받아 둔 목록에서 뽑으면 지금 쪽에 있는 사람만 나옵니다.
  const ownerOptions = useMemo(
    () => [
      { value: '', label: '등록자 전체' },
      ...uploaders.map((item) => ({ value: item.id, label: item.name })),
    ],
    [uploaders],
  )

  // 헤더 정렬을 끄므로 누를 일이 없습니다. 고객 목록과 같은 처리입니다.
  const ignoreSort = useCallback(() => undefined, [])

  const clearFilters = useCallback(() => {
    setParams(new URLSearchParams(), { replace: true })
    setPage(1)
  }, [setParams])

  const openDoc = openId ? findDocument(openId) : undefined

  // 올린 뒤에는 첫 자료의 드로어만 열어 줍니다. 요약이 끝났다고 다음 자료로 넘기지 않습니다.
  // 목록은 다시 받지 않습니다. 올린 자료는 훅이 이미 목록 앞에 세워 두었습니다.
  const onUpload = async (results: UploadResult[]) => {
    try {
      const queued: { documentId: string; fileId: string }[] = []
      setUploadProgress({ done: 0, total: results.length })
      for (const result of [...results].reverse()) {
        const uploaded = await addDocument({
          file: result.file,
          owner: profile.name,
          title: result.title,
          category: result.category,
          link: result.link,
          description: result.description,
        })
        queued.push({ documentId: uploaded.document.id, fileId: uploaded.fileId })
        setUploadProgress({ done: queued.length, total: results.length })
      }
      await queueSummaries(queued)
      setUploading(false)
      setQueuedFileIds(queued.map(({ fileId }) => fileId))
      // 거꾸로 돌며 담았으므로 마지막에 담긴 것이 고른 순서의 첫 자료입니다.
      const first = queued.at(-1)
      if (first) setOpenId(first.documentId)
    } catch {
      // 업로드 뒤 서버 배치 접수가 실패하면 훅의 오류 안내를 보여 줍니다.
      // 서버가 접수한 뒤의 처리는 화면 수명과 무관합니다.
    } finally {
      // 실패해도 진행 표시는 반드시 걷습니다. 모달이 로딩에 잠긴 채 남습니다.
      setUploadProgress(null)
    }
  }

  const summarizeOpenDocument = useCallback(
    (fileId: string) =>
      openDoc
        ? summarizeFile(openDoc.id, fileId)
        : Promise.reject(new Error('자료를 찾을 수 없습니다.')),
    [openDoc, summarizeFile],
  )
  const loadOpenDocumentSummary = useCallback(
    (fileId: string) =>
      openDoc
        ? loadSummary(openDoc.id, fileId)
        : Promise.reject(new Error('자료를 찾을 수 없습니다.')),
    [loadSummary, openDoc],
  )
  const approveOpenDocument = useCallback(
    async (fileId: string) => {
      if (!openDoc) throw new Error('자료를 찾을 수 없습니다.')
      // 승인 결과는 드로어 안에서만 반영합니다. 목록은 다시 들어올 때 갱신됩니다.
      return await approveSummary(openDoc.id, fileId)
    },
    [approveSummary, openDoc],
  )

  const saveDocument = useCallback(
    async (meta: Partial<DocumentMeta>) => {
      if (!openDoc) return
      try {
        await updateDocument(openDoc.id, meta)
        setEditing(false)
      } catch {
        // 훅이 세운 오류 안내를 위쪽 토스트가 이미 보여 줍니다. 모달은 열어 둡니다.
      }
    },
    [openDoc, updateDocument],
  )

  const confirmDelete = useCallback(async () => {
    if (!openDoc) return
    setDeleteError(null)
    try {
      await removeDocument(openDoc.id)
      setDeleting(false)
      setOpenId(null)
      // 목록에서는 빠졌지만 분류 탭 옆 건수는 서버가 셉니다. 다시 받아 맞춥니다.
      reload()
    } catch (reason: unknown) {
      setDeleteError(errorMessage(reason, '자료를 삭제하지 못했습니다.'))
    }
  }, [openDoc, reload, removeDocument])

  const isFiltered =
    query.trim() !== '' || owner !== '' || category !== '' || range !== DEFAULT_RANGE

  // 첫 진입입니다. 툴바·탭·표가 차례로 나타나면 화면이 두세 번 들썩이므로
  // 화면 한 장을 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (loading && pageRows.length === 0 && !error) {
    return (
      <section className={styles.page} aria-busy={loading || pending}>
        {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
        <h1 className="sr-only">{roomLabel}</h1>
        <ListPageSkeleton label="자료를 불러오는 중입니다." tabs />
      </section>
    )
  }

  return (
    <section className={styles.page} aria-busy={loading || pending}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">{roomLabel}</h1>

      <ErrorToast message={error} onRetry={reload} />

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="파일명·메모·연결 검색"
          label="자료 검색"
          onSearch={(next) => setParam('q', next)}
        />

        {isManager && (
          <FilterSelect
            label="등록자"
            value={owner}
            options={ownerOptions}
            open={openFilter === 'owner'}
            onOpenChange={(open) => setOpenFilter(open ? 'owner' : null)}
            onChange={(value) => setParam('owner', value)}
          />
        )}

        <FilterSelect
          label="기간"
          value={range}
          options={RANGES}
          open={openFilter === 'range'}
          onOpenChange={(open) => setOpenFilter(open ? 'range' : null)}
          onChange={(value) => setParam('range', value, DEFAULT_RANGE)}
        />

        <div className={styles.actions}>
          <Button disabled={pending} onClick={() => setUploading(true)}>
            <UploadIcon width={15} height={15} />
            파일 업로드
          </Button>
        </div>
      </div>

      <CategoryTabs
        value={category}
        categories={categories}
        countOf={(id) => categoryCounts.get(id) ?? 0}
        total={categoryTotal}
        onChange={(next) => setParam('category', next)}
      />

      {!error && loading ? (
        <TableSkeleton label="자료 목록을 새로고침하는 중입니다." rows={pageRows.length} />
      ) : (
        <DocumentTable
          rows={pageRows}
          sort={null}
          onSort={ignoreSort}
          onOpen={setOpenId}
          isFiltered={isFiltered}
          onClearFilters={clearFilters}
          showOwner={showOwner}
          onUpload={() => setUploading(true)}
        />
      )}

      {pageRows.length > 0 && (
        <Pagination page={page} pageCount={pageCount} total={total} unit="건" onPage={setPage} />
      )}

      {openDoc && (
        <DocumentDrawer
          key={openDoc.id}
          doc={openDoc}
          onClose={() => setOpenId(null)}
          onSummarize={summarizeOpenDocument}
          onLoadSummary={loadOpenDocumentSummary}
          watchFileId={queuedFileIds.find((id) => id === fileOf(openDoc).id)}
          onApproveSummary={approveOpenDocument}
          canManage={isManager || openDoc.createdByMemberId === memberId}
          onEdit={() => setEditing(true)}
          onDelete={() => {
            setDeleteError(null)
            setDeleting(true)
          }}
        />
      )}

      {editing && openDoc && (
        <DocumentEditModal
          // 드로어와 형제라 같은 키를 쓸 수 없습니다. 자료가 바뀌면 입력값을 새로 채웁니다.
          key={`edit-${openDoc.id}`}
          room={room}
          doc={openDoc}
          submitting={pending}
          onClose={() => setEditing(false)}
          onSubmit={(meta) => void saveDocument(meta)}
        />
      )}

      {deleting && openDoc && (
        <Modal
          title="자료를 삭제하시겠습니까?"
          description={openDoc.title}
          onClose={() => setDeleting(false)}
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                disabled={pending}
                onClick={() => setDeleting(false)}
              >
                취소
              </Button>
              <Button type="button" disabled={pending} onClick={() => void confirmDelete()}>
                {pending ? '삭제 중…' : '삭제'}
              </Button>
            </>
          }
        >
          <p className={styles.confirm}>삭제한 자료는 목록과 AI 검색에서 사라집니다.</p>
          {deleteError && (
            <p className={styles.confirmError} role="alert">
              {deleteError}
            </p>
          )}
        </Modal>
      )}

      {uploading && (
        <UploadModal
          room={room}
          progress={uploadProgress}
          onClose={() => setUploading(false)}
          onSubmit={onUpload}
        />
      )}
    </section>
  )
}

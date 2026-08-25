// 자료실. 계약서·발주서·상품설명서처럼 영업이 돌려 보는 파일을 한 곳에 모읍니다.
// 발주 목록과 같은 형태입니다: 검색·필터 → 분류 탭 → 표 → 상세 드로어.
//
// 조건은 주소에 둡니다(q·owner·range·category). 목록을 걸러 둔 채로 링크를 건네면
// 받는 쪽도 같은 화면을 봅니다. 정렬과 페이지는 보는 사람 사정이라 주소에 남기지 않습니다.
import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import FilterSelect from '@/components/FilterSelect'
import { UploadIcon } from '@/components/icons'
import Pagination from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import { InlineLoader, ListPageSkeleton } from '@/components/Skeleton'
import type { DocumentCategory } from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

import { latestOf } from './catalog'
import { compareBy, linkLabel, type SortState } from './columns'
import CategoryTabs from './components/CategoryTabs'
import DocumentDrawer from './components/DocumentDrawer'
import DocumentTable from './components/DocumentTable'
import UploadModal, { type UploadResult } from './components/UploadModal'
import useDocuments from './useDocuments'

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

export default function Documents() {
  const { documents, findDocument, loading, error, pending, reload, addDocument, addVersion } =
    useDocuments()
  // 자료를 올리는 것은 팀장 몫입니다. 팀원은 받아 보기만 합니다.
  const { profile, isManager } = useCurrentUser()
  const showOwner = isManager

  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const owner = showOwner ? (params.get('owner') ?? '') : ''
  const range = params.get('range') ?? DEFAULT_RANGE

  const ownerOptions = useMemo(() => {
    const names = [...new Set(documents.map((doc) => latestOf(doc).owner))].sort()
    return [
      { value: '', label: '등록자 전체' },
      ...names.map((name) => ({ value: name, label: name })),
    ]
  }, [documents])
  const category = params.get('category') ?? ''

  // 타이핑 중에도 입력이 밀리지 않도록 목록 계산만 한 박자 늦춥니다.
  const deferredQuery = useDeferredValue(query)

  const [sort, setSort] = useState<SortState>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(30)
  const [openId, setOpenId] = useState<string | null>(null)
  const [openFilter, setOpenFilter] = useState<'owner' | 'range' | null>(null)
  /** 업로드 모달. 'new' 는 새 문서, 문서 id 면 그 문서의 새 버전입니다. */
  const [uploading, setUploading] = useState<string | null>(null)

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

  // 분류를 뺀 나머지 조건까지만 거른 목록입니다. 탭의 건수를 여기서 셉니다.
  const beforeCategory = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase()
    return documents.filter((doc) => {
      const latest = latestOf(doc)
      if (owner !== '' && latest.owner !== owner) return false
      if (fromISO !== null && latest.uploaded < fromISO) return false
      if (needle === '') return true
      // 숨은 값(설명·태그·파일명)까지 봅니다. 표에 안 보여도 사람은 그 낱말로 찾습니다.
      return [doc.title, doc.description, latest.fileName, latest.owner, linkLabel(doc)]
        .concat(doc.tags)
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [documents, owner, fromISO, deferredQuery])

  const categoryCounts = useMemo(() => {
    const map = new Map<DocumentCategory, number>()
    for (const doc of beforeCategory) map.set(doc.category, (map.get(doc.category) ?? 0) + 1)
    return map
  }, [beforeCategory])

  const matched = useMemo(() => {
    const rows =
      category === '' ? beforeCategory : beforeCategory.filter((doc) => doc.category === category)
    if (!sort) return rows
    const sign = sort.dir === 'asc' ? 1 : -1
    const compare = compareBy(sort.id)
    return [...rows].sort((a, b) => sign * compare(a, b))
  }, [beforeCategory, category, sort])

  // 결과가 줄어들어 현재 페이지가 사라졌으면 마지막 페이지로 당겨 옵니다.
  const pageCount = Math.max(1, Math.ceil(matched.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const pageRows = useMemo(
    () => matched.slice((safePage - 1) * pageSize, safePage * pageSize),
    [matched, safePage, pageSize],
  )

  const onSort = useCallback((id: string) => {
    // 오름 → 내림 → 해제. 원래 순서로 되돌릴 방법이 있어야 합니다.
    setSort((prev) => {
      if (prev?.id !== id) return { id, dir: 'asc' }
      if (prev.dir === 'asc') return { id, dir: 'desc' }
      return null
    })
  }, [])

  const clearFilters = useCallback(() => {
    setParams(new URLSearchParams(), { replace: true })
    setPage(1)
  }, [setParams])

  const openDoc = openId ? findDocument(openId) : undefined
  const versionTarget = uploading && uploading !== 'new' ? findDocument(uploading) : undefined

  const onUpload = async (results: UploadResult[]) => {
    try {
      if (versionTarget) {
        const [result] = results
        await addVersion(versionTarget.id, result.file, profile.name, result.note)
      } else {
        for (const result of [...results].reverse()) {
          await addDocument({
            file: result.file,
            owner: profile.name,
            note: result.note,
            title: result.title,
            category: result.category,
            link: result.link,
            description: result.description,
            tags: result.tags,
          })
        }
      }
      setUploading(null)
    } catch {
      // 훅이 화면에 오류를 표시하며, 모달은 입력값 보존을 위해 그대로 둡니다.
    }
  }

  const isFiltered =
    query.trim() !== '' || owner !== '' || category !== '' || range !== DEFAULT_RANGE

  // 첫 진입입니다. 툴바·탭·표가 차례로 나타나면 화면이 두세 번 들썩이므로
  // 화면 한 장을 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (loading && documents.length === 0 && !error) {
    return (
      <section className={styles.page} aria-busy={loading || pending}>
        {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
        <h1 className="sr-only">자료실</h1>
        <ListPageSkeleton label="자료를 불러오는 중입니다." tabs />
      </section>
    )
  }

  return (
    <section className={styles.page} aria-busy={loading || pending}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">자료실</h1>

      <ErrorToast message={error} onRetry={reload} />

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="파일명·설명·태그 검색"
          label="자료 검색"
          onChange={(next) => setParam('q', next)}
        />

        {showOwner && (
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

        {isManager && (
          <div className={styles.actions}>
            <Button disabled={pending} onClick={() => setUploading('new')}>
              <UploadIcon width={15} height={15} />
              파일 업로드
            </Button>
          </div>
        )}
      </div>

      <CategoryTabs
        value={category}
        countOf={(id) => categoryCounts.get(id) ?? 0}
        total={beforeCategory.length}
        onChange={(next) => setParam('category', next)}
      />

      {!error && loading && documents.length > 0 && (
        <InlineLoader label="자료 목록을 새로고침하는 중입니다." />
      )}

      <DocumentTable
        rows={pageRows}
        sort={sort}
        onSort={onSort}
        onOpen={setOpenId}
        isFiltered={isFiltered}
        onClearFilters={clearFilters}
        canUpload={isManager}
        showOwner={showOwner}
        onUpload={() => setUploading('new')}
      />

      {matched.length > 0 && (
        <Pagination
          page={safePage}
          pageCount={pageCount}
          pageSize={pageSize}
          total={matched.length}
          unit="건"
          onPage={setPage}
          onPageSize={(size) => {
            setPageSize(size)
            setPage(1)
          }}
        />
      )}

      {openDoc && (
        <DocumentDrawer
          doc={openDoc}
          onClose={() => setOpenId(null)}
          canUpload={isManager}
          onNewVersion={() => setUploading(openDoc.id)}
        />
      )}

      {uploading && (
        <UploadModal
          target={versionTarget}
          submitting={pending}
          onClose={() => setUploading(null)}
          onSubmit={onUpload}
        />
      )}
    </section>
  )
}

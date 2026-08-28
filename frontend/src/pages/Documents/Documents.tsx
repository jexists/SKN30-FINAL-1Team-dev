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
import Pagination, { PAGE_SIZE } from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import { InlineLoader, ListPageSkeleton } from '@/components/Skeleton'
import type { DocumentCategory } from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

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
  // 자료는 팀원도 올립니다. 등록자 필터·열은 팀장에게만 보입니다.
  const { profile, isManager } = useCurrentUser()
  const showOwner = isManager

  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const owner = showOwner ? (params.get('owner') ?? '') : ''
  const range = params.get('range') ?? DEFAULT_RANGE

  const category = params.get('category') ?? ''

  // 타이핑 중에도 입력이 밀리지 않도록 목록 계산만 한 박자 늦춥니다.
  const deferredQuery = useDeferredValue(query)

  const [page, setPage] = useState(1)
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

  const documentQuery = useMemo(
    () => ({
      q: deferredQuery,
      category: category as DocumentCategory | '',
      uploaderMemberId: owner,
      fromISO,
      skip: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    }),
    [deferredQuery, category, owner, fromISO, page],
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
    addVersion,
    summarizeVersion,
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
  if (loading && pageRows.length === 0 && !error) {
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
        total={categoryTotal}
        onChange={(next) => setParam('category', next)}
      />

      {!error && loading && pageRows.length > 0 && (
        <InlineLoader label="자료 목록을 새로고침하는 중입니다." />
      )}

      <DocumentTable
        rows={pageRows}
        sort={null}
        onSort={ignoreSort}
        onOpen={setOpenId}
        isFiltered={isFiltered}
        onClearFilters={clearFilters}
        showOwner={showOwner}
        canUpload={isManager}
        onUpload={() => setUploading('new')}
      />

      {pageRows.length > 0 && (
        <Pagination page={page} pageCount={pageCount} total={total} unit="건" onPage={setPage} />
      )}

      {openDoc && (
        <DocumentDrawer
          doc={openDoc}
          onClose={() => setOpenId(null)}
          canUpload={isManager}
          onNewVersion={() => setUploading(openDoc.id)}
          onSummarize={(fileId) => summarizeVersion(openDoc.id, fileId)}
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

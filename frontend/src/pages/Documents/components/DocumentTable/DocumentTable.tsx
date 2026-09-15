// 자료실 목록 표입니다. 줄 하나가 문서 한 건이고, 누르면 오른쪽 드로어가 섭니다.
//
// 발주 목록 표와 같은 구조입니다. 다른 점은 파일명 칸으로, 무슨 파일인지가 제목만큼
// 중요해서 종류 배지를 제목 앞에 붙입니다.
import { useEffect, useMemo, useRef } from 'react'

import Button from '@/components/Button'
import { ArrowUpIcon, DocumentsIcon, DownloadIcon, SearchIcon, SortIcon } from '@/components/icons'
import OwnerName from '@/components/OwnerName'
import { BP_DESKTOP } from '@/constants/breakpoints'
import type { SalesDocument } from '@/types'
import useMediaQuery from '@/hooks/useMediaQuery'
import { sizeLabel } from '@/utils/attachment'
import { fmtDotShort, parseISO } from '@/utils/date'

import { KIND_LABEL, OWNER_ONLY_DELETE, fileOf, TONE_OF } from '../../catalog'
import { DOCUMENT_COLUMNS, linkLabel, type SortState } from '../../columns'
import { downloadFile } from '../../download'

import styles from './DocumentTable.module.scss'

/** 체크박스 열의 폭. 고객 목록과 같은 값이라 두 표가 같은 자리에서 시작합니다. */
const CHECK_W = 44

interface Props {
  rows: SalesDocument[]
  sort: SortState
  onSort: (id: string) => void
  onOpen: (id: string) => void
  isFiltered: boolean
  onClearFilters: () => void
  showOwner: boolean
  onUpload: () => void
  selected: ReadonlySet<string>
  onToggleRow: (id: string) => void
  onTogglePage: () => void
  /** 지울 수 있는 자료인지. 아니면 체크박스를 잠그고 사유를 답니다. */
  canDelete: (doc: SalesDocument) => boolean
}

export default function DocumentTable({
  rows,
  sort,
  onSort,
  onOpen,
  isFiltered,
  onClearFilters,
  showOwner,
  onUpload,
  selected,
  onToggleRow,
  onTogglePage,
  canDelete,
}: Props) {
  const columns = useMemo(
    () => DOCUMENT_COLUMNS.filter((col) => col.id !== 'owner' || showOwner),
    [showOwner],
  )

  // 표와 카드는 마크업 자체가 다릅니다. CSS 로는 한쪽을 숨기는 것밖에 못 해
  // 폰에서도 일곱 열짜리 DOM 을 그대로 들고 있게 됩니다.
  const isDesktop = useMediaQuery(`(min-width: ${BP_DESKTOP}px)`)

  // 전체선택의 모수는 보이는 줄이 아니라 지울 수 있는 줄입니다. 남이 올린 자료가
  // 한 건이라도 섞이면 "전체"가 영영 켜지지 않습니다.
  const deletable = useMemo(() => rows.filter(canDelete), [rows, canDelete])
  const headCheck = useRef<HTMLInputElement>(null)
  const allChecked = deletable.length > 0 && deletable.every((doc) => selected.has(doc.id))
  const someChecked = deletable.some((doc) => selected.has(doc.id))

  useEffect(() => {
    // indeterminate 는 속성이 아니라 DOM 프로퍼티라 JSX 로 못 넘깁니다.
    if (headCheck.current) headCheck.current.indeterminate = someChecked && !allChecked
  }, [someChecked, allChecked])

  if (rows.length === 0) {
    return (
      <div className={styles.card}>
        <div className={styles.empty}>
          {isFiltered ? (
            <>
              <SearchIcon width={34} height={34} strokeWidth={1.5} />
              <p>조건에 맞는 자료가 없습니다.</p>
              <Button variant="outline" onClick={onClearFilters}>
                검색·필터 초기화
              </Button>
            </>
          ) : (
            <>
              <DocumentsIcon width={34} height={34} strokeWidth={1.5} />
              <p>아직 올린 자료가 없습니다.</p>
              <Button onClick={onUpload}>파일 업로드</Button>
            </>
          )}
        </div>
      </div>
    )
  }

  if (!isDesktop) {
    return (
      <ul className={styles.cardList}>
        {rows.map((doc) => {
          const file = fileOf(doc)
          const mine = canDelete(doc)
          return (
            <li
              key={doc.id}
              className={[styles.miniCard, selected.has(doc.id) ? styles.isSelected : '']
                .filter(Boolean)
                .join(' ')}
              onClick={() => onOpen(doc.id)}
            >
              <div className={styles.miniHead}>
                {/* 카드 어디를 눌러도 상세가 열립니다. 체크박스는 할 일이 따로 있어 막습니다. */}
                <label className={styles.miniCheck} onClick={(event) => event.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected.has(doc.id)}
                    disabled={!mine}
                    title={mine ? undefined : OWNER_ONLY_DELETE}
                    onChange={() => onToggleRow(doc.id)}
                  />
                  <span className="sr-only">
                    {mine ? `${doc.title} 선택` : `${doc.title} — ${OWNER_ONLY_DELETE}`}
                  </span>
                </label>
                <button type="button" className={styles.openButton} onClick={() => onOpen(doc.id)}>
                  {doc.title}
                </button>
                <span className={[styles.badge, styles[TONE_OF[doc.category]]].join(' ')}>
                  {doc.category}
                </span>
              </div>
              <p className={styles.miniLink}>{linkLabel(doc) || KIND_LABEL[doc.kind]}</p>
              <div className={styles.miniMeta}>
                <span className="tnum">{sizeLabel(file.bytes)}</span>
                {showOwner && <OwnerName name={doc.owner} memberId={doc.ownerMemberId} />}
                <span className="tnum">{fmtDotShort(parseISO(file.uploaded))}</span>
                <button
                  type="button"
                  className={styles.miniDownload}
                  onClick={(event) => {
                    event.stopPropagation()
                    downloadFile(file)
                  }}
                >
                  <DownloadIcon width={13} height={13} />
                  받기
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <div className={styles.card}>
      <div className={styles.scroller}>
        <table
          className={styles.table}
          style={{ width: CHECK_W + columns.reduce((sum, col) => sum + col.width, 0) }}
        >
          <caption className="sr-only">자료 목록. 헤더를 눌러 정렬할 수 있습니다.</caption>

          <colgroup>
            <col style={{ width: CHECK_W }} />
            {columns.map((col) => (
              <col key={col.id} style={{ width: col.width }} />
            ))}
          </colgroup>

          <thead>
            <tr>
              <th scope="col" className={styles.checkCell}>
                <input
                  ref={headCheck}
                  type="checkbox"
                  checked={allChecked}
                  disabled={deletable.length === 0}
                  onChange={onTogglePage}
                  title={deletable.length === 0 ? OWNER_ONLY_DELETE : undefined}
                  aria-label="지울 수 있는 자료 전체 선택"
                />
              </th>

              {columns.map((col) => {
                const active = sort?.id === col.id
                return (
                  <th
                    key={col.id}
                    scope="col"
                    className={col.align === 'right' ? styles.right : undefined}
                    aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  >
                    {col.sortable ? (
                      <button
                        type="button"
                        className={[styles.sortButton, active ? styles.isSorted : '']
                          .filter(Boolean)
                          .join(' ')}
                        onClick={() => onSort(col.id)}
                      >
                        {col.header}
                        {active ? (
                          <ArrowUpIcon
                            width={13}
                            height={13}
                            className={sort.dir === 'desc' ? styles.flip : undefined}
                          />
                        ) : (
                          <SortIcon width={13} height={13} className={styles.sortHint} />
                        )}
                      </button>
                    ) : (
                      <span className={styles.headLabel}>{col.header}</span>
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>

          <tbody>
            {rows.map((doc) => {
              const mine = canDelete(doc)
              return (
                <tr
                  key={doc.id}
                  className={[styles.clickable, selected.has(doc.id) ? styles.isSelected : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => onOpen(doc.id)}
                >
                  <td className={styles.checkCell} onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected.has(doc.id)}
                      disabled={!mine}
                      title={mine ? undefined : OWNER_ONLY_DELETE}
                      onChange={() => onToggleRow(doc.id)}
                      aria-label={
                        mine ? `${doc.title} 선택` : `${doc.title} — ${OWNER_ONLY_DELETE}`
                      }
                    />
                  </td>

                  {columns.map((col) => (
                    <td
                      key={col.id}
                      className={[
                        col.align === 'right' ? styles.right : '',
                        col.numeric ? 'tnum' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      title={col.id === 'title' ? fileOf(doc).fileName : col.text(doc)}
                    >
                      {/* 줄 전체를 누르지만 tr 은 키보드로 못 잡습니다. 파일명 칸이
                        그 손잡이이고, 하는 일은 줄을 누른 것과 같습니다. */}
                      {col.id === 'title' ? (
                        <span className={styles.titleCell}>
                          <i className={styles.kind}>{KIND_LABEL[doc.kind]}</i>
                          <button
                            type="button"
                            className={styles.openButton}
                            onClick={(event) => {
                              event.stopPropagation()
                              onOpen(doc.id)
                            }}
                          >
                            {doc.title}
                          </button>
                        </span>
                      ) : col.id === 'category' ? (
                        <span className={[styles.badge, styles[TONE_OF[doc.category]]].join(' ')}>
                          {doc.category}
                        </span>
                      ) : col.id === 'link' && doc.link.kind === 'none' ? (
                        <span className={styles.none}>—</span>
                      ) : col.id === 'owner' ? (
                        <OwnerName name={doc.owner} memberId={doc.ownerMemberId} />
                      ) : col.id === 'download' ? (
                        // 상세를 열지 않고 파일을 바로 받습니다. 줄 클릭과 겹치므로 멈춰 세웁니다.
                        <button
                          type="button"
                          className={styles.download}
                          aria-label={`${fileOf(doc).fileName} 내려받기`}
                          onClick={(event) => {
                            event.stopPropagation()
                            downloadFile(fileOf(doc))
                          }}
                        >
                          <DownloadIcon width={15} height={15} />
                        </button>
                      ) : (
                        col.text(doc)
                      )}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

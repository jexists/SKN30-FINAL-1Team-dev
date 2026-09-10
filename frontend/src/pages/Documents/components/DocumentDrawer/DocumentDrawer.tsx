import { useCallback, useEffect, useRef, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import ErrorToast from '@/components/ErrorToast'
import Popover from '@/components/Popover'
import ReportBody from '@/components/ReportBody'
import { SkeletonBlocks } from '@/components/Skeleton'
import {
  ChevronDownIcon,
  DownloadIcon,
  EditIcon,
  EyeIcon,
  MoreIcon,
  TrashIcon,
} from '@/components/icons'
import { BP_DESKTOP } from '@/constants/breakpoints'
import useMediaQuery from '@/hooks/useMediaQuery'
import SourceDocumentViewer from '@/pages/Customers/components/SourceDocumentViewer'
import type { SalesDocument } from '@/types'
import type { DocumentSummaryResponse } from '@/types'
import { sizeLabel } from '@/utils/attachment'
import { fmtDay, parseISO } from '@/utils/date'

import { KIND_LABEL, fileOf, sourceMode } from '../../catalog'
import { linkLabel } from '../../columns'
import {
  downloadArtifact,
  downloadFile,
  fetchSourceFile,
  type DocumentArtifact,
} from '../../download'
import { pollSummary } from '@/api/polling'

import styles from './DocumentDrawer.module.scss'

interface Props {
  doc: SalesDocument
  /** 지우는 것은 팀장만 합니다. 수정은 팀원도 합니다. */
  canDelete: boolean
  onClose: () => void
  onEdit: () => void
  onDelete: () => void
  /** 다시 실행(재요약) 경로. 지금은 화면에서 감췄지만 API·연결은 그대로 둡니다. */
  onSummarize: (fileId: string) => Promise<DocumentSummaryResponse>
  onLoadSummary: (fileId: string) => Promise<DocumentSummaryResponse>
  /** 배치 접수 뒤에는 처리 시작 POST 없이 상태·결과만 조회합니다. */
  autoLoadSummaryFileId?: string
  onSummaryCompleted?: (fileId: string, failureMessage?: string) => void
  onApproveSummary: (fileId: string) => Promise<DocumentSummaryResponse>
}

/**
 * 내려받기 목록에 세울 처리 결과. 무엇을 받는지로 부르고 형식은 뒤에 작게 붙인다.
 *
 * API 의 'text' 는 'txt' 와 같은 값(extracted_text)을 확장자만 바꿔 내려준다.
 * 같은 것을 두 번 세워 둘 이유가 없어 화면에서는 'txt' 만 쓴다.
 */
const ARTIFACTS: { key: DocumentArtifact; label: string; ext: string }[] = [
  { key: 'txt', label: '추출 텍스트', ext: '.txt' },
  { key: 'md', label: '추출 마크다운', ext: '.md' },
  { key: 'json', label: '인식 데이터', ext: '.json' },
  { key: 'summary', label: 'AI 요약', ext: '.md' },
]

/**
 * 새 요약은 서버에서 추출 필드·출처를 본문에 넣지 않는다. 이미 저장된 구버전 요약도
 * 드로어에서는 같은 기준으로 보여야 하므로, 해당 섹션을 렌더링 직전에 제외한다.
 */
function summaryWithoutHiddenSections(markdown: string): string {
  const lines = markdown.split('\n')
  const hiddenHeadings = new Set(['## 추출 필드', '## 출처'])
  const hiddenTitles = new Set(['# 문서 요약', '# 문서요약'])
  // 'AI 문서 요약' 바로 아래에 '핵심 요약'이 또 서면 라벨만 두 줄이 된다. 본문은
  // 남기고 소제목만 걷어, 첫 문단이 요약의 도입부가 되게 한다.
  const unlabeledHeadings = new Set(['## 핵심 요약', '## 요약'])
  const visibleLines: string[] = []
  let hiding = false

  for (const line of lines) {
    // 새 요약은 제목을 만들지 않지만, 구버전의 제목도 화면에서는 표시하지 않는다.
    if (hiddenTitles.has(line.trim())) continue
    if (/^#{1,2}\s+/.test(line)) {
      hiding = hiddenHeadings.has(line.trim())
      if (unlabeledHeadings.has(line.trim())) continue
    }
    if (!hiding) visibleLines.push(line)
  }
  return visibleLines.join('\n')
}

export default function DocumentDrawer({
  doc,
  canDelete,
  onClose,
  onEdit,
  onDelete,
  // 다시 실행 버튼을 감추면서 함께 쉬는 자리입니다. prop 과 API 는 남겨 둡니다.
  // onSummarize,
  onLoadSummary,
  autoLoadSummaryFileId,
  onSummaryCompleted,
  onApproveSummary,
}: Props) {
  const [summary, setSummary] = useState<DocumentSummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  // 저장된 요약을 받아 오는 동안입니다. 첫 렌더부터 켜 두어야 "아직 요약이
  // 없습니다"가 잠깐 스쳤다가 요약으로 바뀌는 깜빡임이 생기지 않습니다.
  const [summaryFetching, setSummaryFetching] = useState(true)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [summaryLoadError, setSummaryLoadError] = useState<string | null>(null)
  const [summaryLoadRetry, setSummaryLoadRetry] = useState(0)
  const [artifactLoading, setArtifactLoading] = useState<DocumentArtifact | null>(null)
  const [approvalLoading, setApprovalLoading] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [downloadOpen, setDownloadOpen] = useState(false)
  // 오른쪽 패널을 펼쳐 두었는지. 무엇을 세우는지는 아래 mode 가 가릅니다.
  const [sourceOpen, setSourceOpen] = useState(false)
  // 그림으로 그릴 원본. 통째로 받아 둔 파일이라 서명 주소 만료와 상관없습니다.
  const [source, setSource] = useState<File | null>(null)
  // 원본이 곧 글인 형식(txt·md)을 받아서 읽어 둔 것입니다.
  const [sourceText, setSourceText] = useState<string | null>(null)
  const [sourceLoading, setSourceLoading] = useState(false)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const file = fileOf(doc)
  // 이 폭 아래에서는 드로어가 본문을 감추고 원본만 남깁니다(Drawer.module.scss 의
  // .hasSide). 접기가 아니라 닫기로 읽히는 자리라 버튼 모양도 그에 맞춥니다.
  const sourceFullScreen = useMediaQuery(`(max-width: ${BP_DESKTOP - 1}px)`)
  // 원본을 그대로 그릴 수 있는지, 글로 대신 보여 줄지 가릅니다.
  const mode = sourceMode({ name: file.fileName })
  // 브라우저가 그리지 못하는 형식은 처리 과정에서 뽑아 둔 글로 대신합니다. 요약을
  // 불러올 때 같은 응답으로 이미 받아 둔 값이라 따로 조회하지 않습니다.
  const extractedBody = summary?.extracted_markdown ?? summary?.extracted_text ?? ''
  // 추출한 글이 아직 없으면 보여 줄 것이 없습니다. 처리가 끝나면 버튼이 섭니다.
  const canOpenSource = mode !== 'extracted' || extractedBody !== ''
  // 그림으로 그리는 형식에는 넘길 글이 없습니다. 그때는 뷰어가 파일을 직접 그립니다.
  const textSource =
    mode === 'render'
      ? undefined
      : mode === 'plain'
        ? {
            body: sourceText ?? '',
            markdown: /\.(md|markdown)$/i.test(file.fileName),
            extracted: false,
          }
        : { body: extractedBody, markdown: Boolean(summary?.extracted_markdown), extracted: true }
  // 문서에 대한 것과 파일에 대한 것을 갈라 둡니다. 파일 쪽은 아래 카드가 맡습니다.
  const rows: [string, string][] = [
    ['메모', doc.description || '—'],
    ['연결', linkLabel(doc) || '연결된 곳 없음'],
  ]
  const fileMeta = [sizeLabel(file.bytes), file.owner, fmtDay(parseISO(file.uploaded))].join(' · ')
  // 자동 폴링을 시작한 경우와, 드로어를 다시 열어 파일 상태만 가진 경우를 모두 잡는다.
  // 처리 중인데 "아직 요약이 없습니다"라고 보이면 사용자는 업로드가 실패한 것으로 오해한다.
  const summaryProcessing =
    summaryLoading ||
    summary?.processing_status === 'processing' ||
    file.processingStatus === 'processing'

  // 목록을 다시 받으면 부모의 콜백 정체성이 바뀝니다. 그때마다 아래 효과가
  // 다시 돌면 같은 요약을 여러 번 조회하게 되므로 최신 함수만 ref 로 들고 갑니다.
  const loadSummaryRef = useRef(onLoadSummary)
  useEffect(() => {
    loadSummaryRef.current = onLoadSummary
  }, [onLoadSummary])

  // 응답이 늦게 도착하는 사이 다른 파일로 넘어갔다면 그 결과는 버립니다.
  const shownFileRef = useRef(file.id)
  shownFileRef.current = file.id

  const loadSavedSummary = useCallback((fileId: string) => {
    setSummaryLoadError(null)
    setSummaryFetching(true)
    void loadSummaryRef
      .current(fileId)
      .then((result) => {
        if (shownFileRef.current !== fileId) return
        // 아직 처리 전인 정상 응답은 오류가 아니다. 저장된 결과가 있을 때만 표시한다.
        if (result.summary_markdown) setSummary(result)
        else setSummary(null)
      })
      .catch((reason: unknown) => {
        if (shownFileRef.current !== fileId) return
        setSummaryLoadError(
          errorMessage(reason, '저장된 요약을 불러오지 못했습니다. 다시 불러와 주세요.'),
        )
      })
      // 실패해도 로딩 표시는 반드시 걷습니다.
      .finally(() => {
        if (shownFileRef.current === fileId) setSummaryFetching(false)
      })
  }, [])

  useEffect(() => {
    if (!file.id) return
    // 같은 드로어 컴포넌트가 다른 문서로 재사용될 수 있습니다. 새 파일의
    // 결과를 받기 전에 이전 파일의 요약이 잠깐 보이지 않도록 먼저 비웁니다.
    setSummary(null)
    setSummaryError(null)
    setSummaryLoading(false)
    setApprovalLoading(false)
    // 앞 문서의 원본이 오른쪽에 남아 있으면 다른 문서를 보고 있는 것처럼 읽힙니다.
    setSourceOpen(false)
    setSource(null)
    setSourceText(null)
    setSourceError(null)
    setDownloadOpen(false)
    // 배치 접수 직후에는 아래 폴링이 같은 GET 을 돌리므로 단발 조회를 건너뜁니다.
    if (autoLoadSummaryFileId === file.id) return
    loadSavedSummary(file.id)
  }, [autoLoadSummaryFileId, file.id, loadSavedSummary])

  // 다시 실행(재요약)은 당분간 화면에서 감춰 둡니다. 되살릴 때를 위해
  // 처리 흐름은 지우지 않고 그대로 남겨 둡니다. (POST /files/{id}/process)
  // const requestSummary = useCallback(
  //   (fileId: string) => {
  //     setSummaryLoading(true)
  //     setSummaryError(null)
  //     setSummaryLoadError(null)
  //     void onSummarize(fileId)
  //       .then((result) => {
  //         setSummary(result)
  //         if (result.processing_status === 'completed') {
  //           onSummaryCompleted?.(result.file_id)
  //         } else if (result.processing_status === 'failed') {
  //           const message = '문서 요약에 실패했습니다. 잠시 후 다시 시도해 주세요.'
  //           setSummaryError(message)
  //           onSummaryCompleted?.(result.file_id, message)
  //         }
  //       })
  //       .catch((reason: unknown) => {
  //         const message =
  //           reason instanceof Error && reason.message === 'document_summary_timeout'
  //             ? '문서 요약 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.'
  //             : errorMessage(reason, '문서 요약에 실패했습니다. 잠시 후 다시 시도해 주세요.')
  //         setSummaryError(message)
  //         onSummaryCompleted?.(fileId, message)
  //       })
  //       .finally(() => setSummaryLoading(false))
  //   },
  //   [onSummarize, onSummaryCompleted],
  // )

  const monitorQueuedSummary = useCallback(
    (fileId: string) => {
      setSummaryLoading(true)
      setSummaryError(null)
      setSummaryLoadError(null)
      void pollSummary({
        // 배치 API가 이미 처리 요청을 접수했으므로 자동 흐름에서는 GET만 수행합니다.
        start: async () => undefined,
        read: () => onLoadSummary(fileId),
      })
        .then((result) => {
          setSummary(result)
          if (result.processing_status === 'completed') {
            onSummaryCompleted?.(result.file_id)
          } else if (result.processing_status === 'failed') {
            const message = '문서 요약에 실패했습니다. 잠시 후 다시 시도해 주세요.'
            setSummaryError(message)
            onSummaryCompleted?.(result.file_id, message)
          }
        })
        .catch((reason: unknown) => {
          const message =
            reason instanceof Error && reason.message === 'document_summary_timeout'
              ? '문서 요약 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.'
              : errorMessage(
                  reason,
                  '문서 요약 결과를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.',
                )
          setSummaryError(message)
          onSummaryCompleted?.(fileId, message)
        })
        .finally(() => setSummaryLoading(false))
    },
    [onLoadSummary, onSummaryCompleted],
  )

  useEffect(() => {
    if (autoLoadSummaryFileId) monitorQueuedSummary(autoLoadSummaryFileId)
  }, [autoLoadSummaryFileId, monitorQueuedSummary])

  async function handleArtifact(artifact: DocumentArtifact) {
    if (!file.id) return
    setArtifactLoading(artifact)
    try {
      await downloadArtifact(doc.id, file.id, artifact)
    } finally {
      setArtifactLoading(null)
      setDownloadOpen(false)
    }
  }

  function closeSource() {
    setSourceOpen(false)
    setSource(null)
    setSourceText(null)
  }

  async function openSource() {
    if (!file.id) return
    // 드로어가 pointerdown 을 막고 있어 팝오버의 바깥 클릭 닫기가 여기까지 오지
    // 않습니다. 원본을 여는 김에 열려 있던 목록도 함께 걷습니다.
    setDownloadOpen(false)
    setSourceError(null)
    // 추출한 글은 이미 손에 있습니다. 받아 올 것이 없어 바로 펼칩니다.
    if (mode === 'extracted') {
      setSourceOpen(true)
      return
    }
    setSourceLoading(true)
    try {
      const opened = await fetchSourceFile(file)
      // 원본이 곧 글인 형식은 글만 남기면 됩니다. 파일은 들고 있지 않습니다.
      if (mode === 'plain') setSourceText(await opened.text())
      else setSource(opened)
      setSourceOpen(true)
    } catch (reason: unknown) {
      setSourceError(errorMessage(reason, '원본을 열지 못했습니다. 내려받아서 확인해 주세요.'))
    } finally {
      setSourceLoading(false)
    }
  }

  return (
    <Drawer
      title={doc.title}
      sub={doc.documentNo ?? doc.id}
      onClose={onClose}
      actions={
        <Popover
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
          align="end"
          compact
          label="자료 메뉴"
          trigger={
            <button
              type="button"
              className={styles.menuBtn}
              aria-label="자료 메뉴"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((value) => !value)}
            >
              <MoreIcon width={18} height={18} />
            </button>
          }
        >
          <div className={styles.menu}>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false)
                onEdit()
              }}
            >
              <EditIcon width={15} height={15} />
              수정
            </button>
            {canDelete && (
              <button
                type="button"
                className={styles.danger}
                onClick={() => {
                  setMenuOpen(false)
                  onDelete()
                }}
              >
                <TrashIcon width={15} height={15} />
                삭제
              </button>
            )}
          </div>
        </Popover>
      }
      meta={
        <>
          <i className={styles.pill}>{doc.category}</i>
          <i className={styles.pill}>{KIND_LABEL[doc.kind]}</i>
        </>
      }
      side={
        sourceOpen && (
          <SourceDocumentViewer
            file={source ?? { name: file.fileName }}
            text={textSource}
            fullScreen={sourceFullScreen}
            onCollapse={closeSource}
          />
        )
      }
    >
      <ErrorToast
        key={`${file.id ?? 'empty'}-${summaryLoadRetry}`}
        message={summaryLoadError}
        onRetry={() => {
          if (!file.id) return
          setSummaryLoadRetry((value) => value + 1)
          loadSavedSummary(file.id)
        }}
      />
      {/* 원본을 열지 못한 것은 요약과 다른 문제라 따로 알립니다. */}
      <ErrorToast
        key={`source-${file.id ?? 'empty'}`}
        message={sourceError}
        onRetry={() => void openSource()}
      />
      <dl className={styles.rows}>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      {file.id && (
        <section className={styles.summary}>
          <div className={styles.summaryHead}>
            <h3 className={styles.sectionTitle}>AI 문서 요약</h3>
            {/* 다시 실행은 당분간 쓰지 않습니다. 되살릴 때 이 자리에 그대로 둡니다.
            <button
              type="button"
              className={styles.summarize}
              disabled={summaryLoading}
              onClick={() => requestSummary(file.id!)}
            >
              {summaryLoading ? '요약 중…' : '다시 실행'}
            </button>
            */}
          </div>
          {(summaryError ?? summaryLoadError) ? (
            <p className={styles.summaryError}>{summaryError ?? summaryLoadError}</p>
          ) : summaryProcessing && !summary?.summary_markdown ? (
            <div className={styles.summaryLoading} role="status" aria-live="polite">
              <span className={styles.summarySpinner} aria-hidden="true" />
              <div>
                <strong>AI 문서 요약 중…</strong>
                <p>문서 내용을 읽고 핵심 정보를 정리하고 있습니다.</p>
              </div>
            </div>
          ) : summaryFetching && !summary?.summary_markdown ? (
            <div className={styles.summarySkeleton}>
              <SkeletonBlocks
                label="AI 요약을 불러오는 중입니다."
                count={4}
                height={12}
                gap={10}
                radius="var(--r-sm)"
              />
            </div>
          ) : !summary?.summary_markdown ? (
            <p className={styles.summaryPending}>아직 요약이 없습니다.</p>
          ) : (
            <>
              {summary?.processing_status === 'review_required' && (
                <p className={styles.reviewNotice}>
                  OCR·요약 결과를 확인한 뒤 승인해야 최종 DB와 RAG에 저장됩니다.
                </p>
              )}
              {/* 저장된 요약은 마크다운입니다. 보고서 본문과 같은 렌더러로 그립니다. */}
              <ReportBody
                body={summaryWithoutHiddenSections(summary.summary_markdown)}
                className={styles.summaryBody}
              />
              {summary?.processing_status === 'review_required' && (
                <div className={styles.approveRow}>
                  <button
                    type="button"
                    className={styles.approve}
                    disabled={approvalLoading}
                    onClick={() => {
                      setApprovalLoading(true)
                      void onApproveSummary(summary.file_id)
                        .then(setSummary)
                        .catch(() => setSummaryError('요약을 승인하고 저장하지 못했습니다.'))
                        .finally(() => setApprovalLoading(false))
                    }}
                  >
                    {approvalLoading ? '저장 중…' : '확인하고 최종 저장'}
                  </button>
                </div>
              )}
            </>
          )}
        </section>
      )}

      <section className={styles.source}>
        <h3 className={styles.sectionTitle}>원본 파일</h3>
        {file.id ? (
          <div className={styles.fileCard}>
            <div className={styles.fileName}>{file.fileName}</div>
            <p className={styles.fileMeta}>{fileMeta}</p>
            <div className={styles.fileActions}>
              {canOpenSource &&
                (sourceOpen ? (
                  <Button variant="outline" size="sm" onClick={closeSource}>
                    <EyeIcon width={14} height={14} />
                    원본 닫기
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={sourceLoading}
                    onClick={() => void openSource()}
                  >
                    <EyeIcon width={14} height={14} />
                    {sourceLoading ? '원본 여는 중…' : '원본 보기'}
                  </Button>
                ))}

              {/* 받을 것이 여럿이라 버튼을 늘어놓는 대신 한 곳에 모읍니다.
                  머리말의 '…' 메뉴와 같은 팝오버입니다. */}
              <Popover
                open={downloadOpen}
                onClose={() => setDownloadOpen(false)}
                align="end"
                compact
                up
                label="내려받기"
                trigger={
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-expanded={downloadOpen}
                    onClick={() => setDownloadOpen((value) => !value)}
                  >
                    <DownloadIcon width={14} height={14} />
                    내려받기
                    <ChevronDownIcon width={14} height={14} />
                  </Button>
                }
              >
                <div className={styles.downloadMenu}>
                  <p className={styles.menuGroup}>원본</p>
                  <button
                    type="button"
                    onClick={() => {
                      setDownloadOpen(false)
                      void downloadFile(file)
                    }}
                  >
                    <span>{file.fileName}</span>
                    <i>{sizeLabel(file.bytes)}</i>
                  </button>

                  {summary?.processing_status === 'completed' && (
                    <>
                      <p className={`${styles.menuGroup} ${styles.menuDivider}`}>처리 결과</p>
                      {ARTIFACTS.map(({ key, label, ext }) => (
                        <button
                          key={key}
                          type="button"
                          disabled={artifactLoading !== null}
                          onClick={() => void handleArtifact(key)}
                        >
                          <span>{label}</span>
                          <i>{artifactLoading === key ? '준비 중…' : ext}</i>
                        </button>
                      ))}
                    </>
                  )}
                </div>
              </Popover>
            </div>
          </div>
        ) : (
          <p className={styles.fileEmpty}>파일 없음</p>
        )}
        {file.note && <p className={styles.note}>{file.note}</p>}
      </section>
    </Drawer>
  )
}

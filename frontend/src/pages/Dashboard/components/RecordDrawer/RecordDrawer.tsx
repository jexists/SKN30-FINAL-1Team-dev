import { useRef, useState } from 'react'
import { Link } from 'react-router'

import { errorMessage } from '@/api/errorMessage'
import Button, { buttonClass } from '@/components/Button'
import Drawer from '@/components/Drawer'
import Popover from '@/components/Popover'
import Skeleton, { InlineLoader } from '@/components/Skeleton'
import { EditIcon, MoreIcon, RefreshIcon, TrashIcon } from '@/components/icons'
import { orderPath } from '@/constants/routes'
import SourceDocumentViewer from '@/pages/Customers/components/SourceDocumentViewer'
import { sourceMode } from '@/pages/Documents/catalog'
import { fetchDocumentSummary, fetchSourceFile } from '@/pages/Documents/download'
import { statusScope } from '@/shared/agenda'
import { useAgendaReportLink } from '@/shared/agendaReport'
import { RISK_LABEL } from '@/shared/riskLabels'
import { useShowOwner } from '@/shared/scope'
import type { AgendaItem, ContractBriefingOutput, ContractRisk, SourceRef } from '@/types'
import type { BriefingDocument } from '@/types/agenda'
import { fmtDay, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import { useRelatedDeal } from '../../useDashboard'
import BriefingMaterials from './BriefingMaterials'
import BriefingProgress from './BriefingProgress'
import BriefingSourceSummary from './BriefingSourceSummary'
import BriefingStream, { type BriefingReference } from './BriefingStream'
import InfoHint from './InfoHint'
import useAiBriefing from '../../useAiBriefing'

import styles from './RecordDrawer.module.scss'

const BRIEFING_SCOPE_TEXT =
  '최근 보고서 3건, 과거 보고서 RAG 검색, 고객사의 전체 딜을 참고해 만듭니다.'

/** 요약 탭에 세울 것이 있는 자료인지. 없으면 탭 없이 원본만 폅니다. */
function hasSummaryView(document: BriefingDocument) {
  return !!document.summary_markdown
}

interface BriefingViewHighlight {
  title: string
  body: string
  suggestedActions: string[]
  sourceRefs: SourceRef[]
}

interface BriefingView {
  highlights: BriefingViewHighlight[]
  missingInformation: string[]
  risks: ContractRisk[]
}

/** 본문 인용에서 원문을 열 때 바로 펼 자리. 있으면 요약 대신 원본부터 폅니다. */
interface DocumentCitation {
  pageStart: number | null
}

/** 새 highlights 형식과 DB에 남은 구 contract_summary 형식을 한 화면 모델로 맞춥니다. */
function briefingView(content: ContractBriefingOutput | null | undefined): BriefingView | null {
  if (!content || typeof content !== 'object') return null
  if ('highlights' in content) {
    const highlights = Array.isArray(content.highlights) ? content.highlights : []
    return {
      highlights: highlights
        .filter((highlight) => highlight && typeof highlight === 'object')
        .map((highlight) => ({
          title: typeof highlight.title === 'string' ? highlight.title : '',
          body: typeof highlight.body === 'string' ? highlight.body : '',
          suggestedActions: Array.isArray(highlight.suggested_actions)
            ? highlight.suggested_actions.filter(
                (value): value is string => typeof value === 'string',
              )
            : [],
          sourceRefs: Array.isArray(highlight.source_refs) ? highlight.source_refs : [],
        }))
        .filter((highlight) => highlight.title || highlight.body),
      missingInformation: Array.isArray(content.missing_information)
        ? content.missing_information.filter((value): value is string => typeof value === 'string')
        : [],
      risks: [],
    }
  }
  return {
    highlights:
      typeof content.contract_summary === 'string' && content.contract_summary
        ? [
            {
              title: '',
              body: content.contract_summary,
              suggestedActions: Array.isArray(content.recommended_actions)
                ? content.recommended_actions
                : [],
              sourceRefs: Array.isArray(content.source_refs) ? content.source_refs : [],
            },
          ]
        : [],
    missingInformation: Array.isArray(content.missing_information)
      ? content.missing_information
      : [],
    risks: Array.isArray(content.risks) ? content.risks : [],
  }
}

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
  const {
    briefing,
    loading: briefingLoading,
    error: briefingError,
    regenerate: regenerateBriefing,
    regenerating: briefingRegenerating,
    regenerateError: briefingRegenerateError,
    stalled: briefingStalled,
  } = useAiBriefing({ activityId: item.id, eligible: !!item.customerCompanyId })
  // 내가 누른 재생성과 서버가 이미 돌리고 있는 갱신을 화면에서는 같게 다룹니다.
  const briefingBusy = briefingRegenerating || !!briefing?.refreshing
  const briefingContent = briefingView(briefing?.content)
  // 실행이 돌고 있거나 아직 보여줄 본문이 없으면 진행 줄을 세웁니다. 갱신을 다 기다리지
  // 못하고 폴링을 접었으면(stalled) 걷습니다 — 더 올 것이 없는데 초만 셀 이유가 없습니다.
  const briefingPending =
    !!briefing &&
    !briefingStalled &&
    briefing.status !== 'failed' &&
    (briefingBusy || briefing.status !== 'completed')
  // 새 실행이 시작될 때마다 초를 처음부터 셉니다.
  const briefingRunKey = `${briefing?.run_id ?? 'pending'}:${briefingBusy ? 'busy' : 'wait'}`
  // 기다리는 것을 본 적이 있으면, 도착한 본문을 타자 치듯 폅니다. 이미 있던 브리핑을
  // 그냥 열었을 때는 흐르지 않습니다 — 읽으려고 연 글이 다시 써지면 자리를 잃습니다.
  const waitedForBriefing = useRef(false)
  if (briefingPending) waitedForBriefing.current = true
  // 인용 여부는 목록을 거르는 조건이 아니라 세우는 순서입니다. 브리핑이 인용을 빠뜨려도
  // 자료 자체는 보여야 하고, 브리핑이 실패해도 목록은 남아야 합니다. 어느 문단이 무엇을
  // 썼는지는 문단 앞 링크가 말하므로 끝의 목록에는 따로 표시를 달지 않습니다.
  const citedDocumentIds = new Set(
    (briefingContent?.highlights.flatMap((highlight) => highlight.sourceRefs) ?? [])
      .filter((ref) => ref.type === 'document')
      .map((ref) => ref.id),
  )
  const [menuOpen, setMenuOpen] = useState(false)
  // 옆에 펴 둔 자료. 요약은 브리핑에 실려 와 바로 서고, 원본은 그 탭을 눌러야 받아 옵니다.
  // 그릴 수 있는 형식은 file 로, 글로 대신하는 형식은 text 로 채워집니다.
  const [source, setSource] = useState<{
    document: BriefingDocument
    tab: 'summary' | 'source'
    file: File | null
    text: { body: string; markdown: boolean; extracted: boolean } | null
    citation: DocumentCitation | null
    loading: boolean
    error: string | null
  } | null>(null)
  // 받아 오는 중인 자료. 누른 줄의 버튼만 멈춥니다.
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [sourceError, setSourceError] = useState<{
    documentId: string
    message: string
  } | null>(null)
  const showOwner = useShowOwner()
  // 드로어는 눌러야 열리므로 여기서 물어보는 것이 곧 온디맨드입니다.
  const reportState = useAgendaReportLink(item)
  function closeSource() {
    setSource(null)
  }

  /**
   * 자료실과 같은 방식으로 원본을 받아 옵니다. 서명 주소는 60초만 살아 그대로
   * 넘기지 않고 파일째 받아 둡니다(pages/Documents/download.ts 주석).
   */
  async function loadSource(doc: BriefingDocument) {
    const mode = sourceMode({ name: doc.file_name })
    // 브라우저가 그리지 못하는 형식은 처리 과정에서 뽑아 둔 글로 대신합니다.
    if (mode === 'extracted') {
      const summary = await fetchDocumentSummary(doc.document_id, doc.file_id)
      const body = summary.extracted_markdown ?? summary.extracted_text ?? ''
      if (!body) throw new Error('document_source_not_extracted')
      return {
        file: null,
        text: { body, markdown: !!summary.extracted_markdown, extracted: true },
      }
    }
    const opened = await fetchSourceFile({
      id: doc.file_id,
      documentId: doc.document_id,
      fileName: doc.file_name,
      bytes: 0,
      owner: '',
      uploaded: '',
      note: '',
    })
    // 원본이 곧 글인 형식은 글만 남기면 됩니다. 파일은 들고 있지 않습니다.
    return mode === 'plain'
      ? {
          file: null,
          text: {
            body: await opened.text(),
            markdown: /\.(md|markdown)$/i.test(doc.file_name),
            extracted: false,
          },
        }
      : { file: opened, text: null }
  }

  function sourceFailure(reason: unknown) {
    return reason instanceof Error && reason.message === 'document_source_not_extracted'
      ? '아직 내용을 불러올 수 없습니다. 자료실에서 처리가 끝난 뒤 다시 열어 주세요.'
      : errorMessage(reason, '내용을 열지 못했습니다.')
  }

  /**
   * 자료를 옆에 폅니다. 요약은 브리핑에 이미 실려 와 기다릴 것이 없어 바로 펴고,
   * 원본은 그 탭을 눌렀을 때 받아 옵니다.
   */
  async function openSource(doc: BriefingDocument, citation: DocumentCitation | null = null) {
    setSourceError(null)
    if (hasSummaryView(doc) && !citation) {
      setSource({
        document: doc,
        tab: 'summary',
        file: null,
        text: null,
        citation,
        loading: false,
        error: null,
      })
      return
    }
    // 세울 탭이 없는 자료는 예전처럼 원본을 받아 온 뒤에 폅니다. 열지 못하면 빈 패널을
    // 세우는 대신 누른 줄에 사유를 답니다.
    setOpeningId(doc.document_id)
    try {
      const loaded = await loadSource(doc)
      setSource({
        document: doc,
        tab: 'source',
        ...loaded,
        citation,
        loading: false,
        error: null,
      })
    } catch (reason: unknown) {
      setSourceError({ documentId: doc.document_id, message: sourceFailure(reason) })
    } finally {
      setOpeningId(null)
    }
  }

  /** 탭을 옮깁니다. 원본은 처음 펼 때 한 번만 받아 오고 그 뒤로는 들고 있던 것을 씁니다. */
  async function changeTab(tab: 'summary' | 'source') {
    const current = source
    if (current === null || current.tab === tab) return
    const doc = current.document
    const loaded = current.file !== null || current.text !== null
    setSource({ ...current, tab, loading: tab === 'source' && !loaded, error: null })
    if (tab !== 'source' || loaded || current.loading) return
    // 받아 오는 동안 다른 자료로 갈아탔을 수 있어, 돌아와서 같은 자료인지 확인합니다.
    const settle = (
      patch: Partial<{ file: File | null; text: typeof current.text; error: string | null }>,
    ) =>
      setSource((previous) =>
        previous && previous.document.document_id === doc.document_id
          ? { ...previous, ...patch, loading: false }
          : previous,
      )
    try {
      settle(await loadSource(doc))
    } catch (reason: unknown) {
      settle({ error: sourceFailure(reason) })
    }
  }

  /**
   * 문단이 근거로 쓴 자료. 그 자료에서 온 문장을 찾으면 문장 끝에, 못 찾으면 문단 끝에
   * 원문 링크가 섭니다(BriefingStream).
   *
   * 자료 하나에 하나입니다. 같은 파일을 두 청크로 인용해도 같은 파일 이름이 두 번 서면
   * 무엇이 다른지 읽히지 않습니다. 형광펜을 그을 원문 구절은 인용된 만큼 모아 넘깁니다 —
   * 링크는 하나여도 짚어 볼 구절은 여럿입니다.
   */
  function documentReferences(refs: SourceRef[]): BriefingReference[] {
    // 제품 자료도 인용될 수 있습니다. 어느 묶음에서 왔든 링크는 달려야 합니다.
    const documents = [
      ...(briefing?.documents?.related ?? []),
      ...(briefing?.documents?.product ?? []),
    ]
    const byDocument = new Map<string, BriefingReference>()
    refs.forEach((ref) => {
      if (ref.type !== 'document') return
      const document = documents.find((item) => item.document_id === ref.id)
      if (!document) return
      const matched = ref.chunk_id
        ? document.excerpts?.find((item) => item.chunk_id === ref.chunk_id)
        : undefined
      // 청크를 짚지 않은 인용(예전 형식의 브리핑)은 그 자료에서 뽑아 둔 구절을 모두
      // 후보로 넘깁니다. 어느 문장이 그 자료에서 왔는지는 형광펜이 본문과 맞춰 봅니다.
      const candidates = matched ? [matched] : (document.excerpts ?? [])
      const quotes = [...new Set([ref.excerpt, ...candidates.map((item) => item.content)])].filter(
        (value): value is string => !!value,
      )
      const found = byDocument.get(document.document_id)
      if (found) {
        found.excerpts.push(...quotes)
        return
      }
      // 원문을 펼 자리는 짚은 청크, 없으면 그 자료의 첫 구절입니다.
      const anchor = candidates[0]
      const quote = ref.excerpt ?? anchor?.content ?? null
      const pageStart = anchor?.page_start ?? null
      const pageEnd = anchor?.page_end ?? null
      const page = pageStart
        ? pageEnd && pageEnd !== pageStart
          ? `${pageStart}-${pageEnd}페이지`
          : `${pageStart}페이지`
        : null
      byDocument.set(document.document_id, {
        key: document.document_id,
        // 아이콘 하나만 보이므로 파일 이름을 안내에 함께 답니다. 이름을 본문에 글자로
        // 세우면 브리핑 끝의 출처 목록과 같은 이름이 두 번 섭니다.
        hint: page ? `${document.file_name} · ${page} 열기` : `${document.file_name} 원문 열기`,
        excerpts: quotes,
        // 어느 대목을 보고 쓴 글인지 알 때는 원문의 그 자리를 바로 폅니다.
        onOpen: () => void openSource(document, quote ? { pageStart } : null),
      })
    })
    return [...byDocument.values()]
  }

  const at = item.contact.lastIndexOf(' ')
  const facts: [string, string][] = (
    [
      // 여러 사람의 일정이 섞여 보일 때만, 이것이 누구 일정인지 먼저 말합니다.
      ...(showOwner ? ([['담당 영업', item.owner]] as [string, string][]) : []),
      ['부서', item.dept],
      ['고객 담당자', at < 0 ? item.contact : item.contact.slice(0, at)],
      ['직책', item.contact && at >= 0 ? item.contact.slice(at + 1) : ''],
      ['제품', item.product],
      ['장소', item.place],
    ] as [string, string][]
  ).filter(([, value]) => value !== '')
  return (
    <Drawer
      wide
      // 자료는 미팅 내용을 보면서 확인하는 것입니다. 옆에 펴도 본문을 남깁니다.
      keepMain
      title={item.hospital || item.title}
      sub={
        <>
          {item.title}
          <span className={styles.when}>
            · {fmtDay(parseISO(item.date))} {item.time}
          </span>
        </>
      }
      onClose={onClose}
      // 자료는 보다가 본문으로 돌아가면 볼 일이 끝납니다. 본문을 누르면 그대로 닫습니다.
      onSideDismiss={closeSource}
      side={
        source && (
          <SourceDocumentViewer
            file={source.file ?? { name: source.document.file_name }}
            text={source.text ?? undefined}
            summary={
              hasSummaryView(source.document) && (
                <BriefingSourceSummary document={source.document} />
              )
            }
            tab={source.tab}
            onTabChange={(tab) => void changeTab(tab)}
            sourceStatus={
              source.loading
                ? 'loading'
                : source.error
                  ? 'error'
                  : source.file || source.text
                    ? 'ready'
                    : 'idle'
            }
            sourceError={source.error}
            initialPage={source.citation?.pageStart}
            // 여닫는 자리가 '자료 보기' 한 곳이라 접기가 아니라 닫기로 읽힙니다.
            dismiss="close"
            onCollapse={closeSource}
          />
        )
      }
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
      // 남이 한 일이고 아직 보고서도 없으면(blocked) 갈 곳이 없어 아무것도 세우지 않습니다.
      footer={
        reportState.error ? (
          <Button variant="outline" onClick={reportState.reload}>
            보고서 다시 조회
          </Button>
        ) : !reportState.link ? (
          <InlineLoader label="보고서 연결을 확인하는 중입니다." />
        ) : reportState.link.blocked ? null : (
          <Link className={buttonClass()} to={reportState.link.to}>
            {reportState.link.label}
          </Link>
        )
      }
    >
      <div className={`${styles.grid} ${source ? styles.gridNarrow : ''}`}>
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

        <section className={`${styles.block} ${styles.full}`}>
          <h3 className={styles.briefingHead}>
            AI 브리핑
            {item.customerCompanyId && <InfoHint text={BRIEFING_SCOPE_TEXT} />}
            {/* 갱신 중이라는 표시는 제목 옆에만 둡니다. 본문은 그대로 두고 읽게 합니다. */}
            {briefing?.refreshing && <span className={styles.refreshTag}>최신 자료 반영 중</span>}
            {/* 브리핑은 새로고침을 눌러야만 바뀝니다. 그 사이 입력이 바뀌었으면 버튼 옆에서 알립니다. */}
            {briefing?.outdated && !briefingBusy && (
              <span className={styles.outdatedTag}>반영되지 않은 내용이 있습니다</span>
            )}
            {item.customerCompanyId && (
              <Button
                className={styles.refreshButton}
                variant="ghost"
                size="sm"
                title="최신 내용으로 재생성"
                disabled={briefingLoading || briefingBusy}
                onClick={regenerateBriefing}
              >
                <RefreshIcon
                  className={briefingBusy ? styles.spin : undefined}
                  width={14}
                  height={14}
                  aria-hidden="true"
                />
                {briefingBusy ? '새로고침 중' : '새로고침'}
              </Button>
            )}
          </h3>
          {!item.customerCompanyId ? (
            <p className={styles.note}>고객사가 연결되지 않아 AI 브리핑을 만들 수 없습니다.</p>
          ) : briefingError ? (
            <p className={styles.note} role="alert">
              {briefingError}
            </p>
          ) : briefingLoading ? (
            <Skeleton height={72} radius="var(--r-md)" />
          ) : briefing === null ? (
            // 이 일정에는 아직 브리핑 실행이 없습니다. 자동으로 생기지 않으니 새로고침으로 만들게 안내합니다.
            <p className={styles.note}>아직 만든 AI 브리핑이 없습니다. 새로고침을 눌러 만들어 주세요.</p>
          ) : briefing.status === 'failed' && !briefingContent ? (
            // 보여줄 이전 결과가 없을 때만 실패를 크게 알립니다.
            <p className={styles.note} role="alert">
              {`브리핑 생성에 실패했습니다${briefing.error ? `: ${briefing.error}` : ''}`}
            </p>
          ) : (
            <>
              {/* 도는 중이면 무엇을 하고 있는지 한 줄로 세웁니다. 보고서 진행 화면과 같은 줄입니다. */}
              {briefingPending && <BriefingProgress key={briefingRunKey} runKey={briefingRunKey} />}
              {/* 마지막 성공 브리핑은 그대로 두고, 실패는 작게만 알립니다. */}
              {briefing.refresh_error && (
                <p className={styles.refreshError} role="status">
                  최신 자료로 다시 만들지 못했습니다. 이전 브리핑을 보여드립니다.
                </p>
              )}
              {briefingRegenerateError && (
                <p className={styles.refreshError} role="alert">
                  {briefingRegenerateError}
                </p>
              )}
              {!briefingContent ? (
                // 도는 중이면 진행 줄이 이미 서 있습니다. 여기서 또 말하지 않습니다.
                !briefingPending && <p className={styles.note}>표시할 브리핑 내용이 없습니다.</p>
              ) : (
                <div className={briefingPending ? styles.staleBody : undefined}>
                  {briefingContent.highlights.length > 0 ? (
                    <BriefingStream
                      stream={waitedForBriefing.current}
                      blocks={briefingContent.highlights.map((highlight, index) => ({
                        key: `${highlight.title}-${index}`,
                        title: highlight.title,
                        body: highlight.body,
                        actions: highlight.suggestedActions,
                        references: documentReferences(highlight.sourceRefs),
                      }))}
                      risks={briefingContent.risks.map((risk) => RISK_LABEL[risk.code])}
                      missingInformation={briefingContent.missingInformation}
                    />
                  ) : (
                    <p className={styles.note}>표시할 브리핑 내용이 없습니다.</p>
                  )}
                </div>
              )}
            </>
          )}
          {!briefingLoading && briefing && (
            <BriefingMaterials
              documents={briefing.documents}
              citedDocumentIds={citedDocumentIds}
              onOpenSource={openSource}
              openingDocumentId={openingId}
              sourceError={sourceError}
            />
          )}
        </section>

        {item.brief && (
          <section className={`${styles.block} ${styles.full}`}>
            <h3>미팅 메모</h3>
            <p className={styles.note}>{item.brief}</p>
          </section>
        )}
      </div>
    </Drawer>
  )
}

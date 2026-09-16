// 기간 보고서 작성. 생성 당시 하위 보고서 참조를 최종 제출까지 보존합니다.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import Button, { buttonClass } from '@/components/Button'
import AttachmentPanel from '@/components/AttachmentPanel'
import ColumnHead from '@/components/ColumnHead'
import DayHeader from '@/components/DayHeader'
import ErrorToast from '@/components/ErrorToast'
import FormField from '@/components/FormField'
import {
  ArrowDownIcon,
  CalendarIcon,
  // ChevronLeftIcon, // 접기 손잡이와 함께 내려둠
  ChevronRightIcon,
  DocumentsIcon,
  DownloadIcon,
  InfoIcon,
  RefreshIcon,
  SheetIcon,
  StopIcon,
  TeamIcon,
} from '@/components/icons'
import Modal from '@/components/Modal'
import ReportBanner from '@/components/ReportBanner'
import ReportDocHeader from '@/components/ReportDocHeader'
import ReportReviewWarning from '@/components/ReportReviewWarning'
import Skeleton from '@/components/Skeleton'
import Tabs from '@/components/Tabs'
import { dailyComposePath, dailyReportPath } from '@/constants/routes'
import useTeamMembers from '@/hooks/useTeamMembers'
import { reportTextLength } from '@/shared/reports'
import type { ReportKind } from '@/types'
import { fmtDay, fmtDot, parseISO, TODAY_ISO } from '@/utils/date'

import ActivityList from './components/ActivityList'
import DailyListLink from './components/DailyListLink'
import ReportStatusBadge from './components/ReportStatusBadge'
import { kindToPeriod, PERIOD_KIND, periodLabelFor, periodStart, toPeriod } from './periods'
import useDailyDraft from './useDailyDraft'
import useDailyReports from './useDailyReports'
import EditableReport from '../Meetings/components/EditableReport'
import GenerationProgress from '../Meetings/components/GenerationProgress'
import useStickToBottom from '../Meetings/components/GenerationProgress/useStickToBottom'

import styles from './Compose.module.scss'

/** 자료를 기다리는 동안 잡아 두는 목록 높이. 서너 줄쯤 들어가는 자리입니다. */
const SOURCE_LIST_H = 240

/**
 * 확인이 필요한 여섯 갈래. 앞의 셋은 "쓰던 걸 버려도 되나", 'unwritten' 은 "빠뜨려도 되나",
 * 뒤의 둘은 수정을 끝내는 두 길입니다.
 */
type Confirm =
  | { kind: 'regenerate' }
  | { kind: 'date'; next: string }
  | { kind: 'submit' }
  | { kind: 'unwritten' }
  | { kind: 'cancelEdit' }
  | { kind: 'finishEdit' }
  | null

const DATE_LABEL: Record<ReportKind, string> = {
  일일: '보고 일자를',
  주간: '기준 주를',
  월간: '기준 월을',
}

export default function Compose() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  // ?kind= 는 기간 탭(?tab=)과 같은 어휘를 씁니다. 없으면 일일보고입니다.
  const kind = PERIOD_KIND[toPeriod(params.get('kind'))] ?? '일일'
  // 주·월은 아무 날짜로 들어와도 그 기간의 첫날 하나로 봅니다. 같은 주에 보고서가
  // 둘 생기지 않는 것도, 이어서 쓰는 것도 이 값이 같은지로 갈립니다.
  const dateISO = periodStart(kind, params.get('date') ?? TODAY_ISO)

  const draft = useDailyDraft(dateISO, kind)
  // 보고서 머리표가 쓰는 값입니다. 부서·회사는 팀의 값이라 구성원마다 같습니다.
  const { profile } = useCurrentUser()
  // 보고 대상 이름은 사람이 머리표에서 적습니다. 다만 검토 요청은 팀장에게 가므로
  // 가리키는 사람은 팀장으로 고정합니다 — 팀장은 팀당 한 명입니다.
  const { members } = useTeamMembers()
  const manager = members.find((member) => member.role_code === 'manager')
  const { submitReport, pending, error } = useDailyReports()
  const loadError = draft.error ?? error

  const [confirm, setConfirm] = useState<Confirm>(null)
  // 본문을 고치는 중인지. 조작부는 아래 떠 있는 바 하나뿐이라 상태도 여기서 쥡니다.
  const [editing, setEditing] = useState(false)
  // 수정에 들어간 순간의 본문과 보고 대상. [취소] 는 이 값으로 되돌립니다.
  const bodySnapshot = useRef('')
  const approverSnapshot = useRef('')
  // 미팅 작성 화면과 같은 손잡이입니다. 보고서만 넓게 볼 때 자료 열을 접습니다.
  // 자료 열 접기 기능은 잠시 내려둡니다. 손잡이가 없으니 늘 펼친 채로 둡니다.
  // const [sideCollapsed, setSideCollapsed] = useState(false)
  const sideCollapsed = false
  // 오른쪽 보고서 열 자체입니다. 다 쓰인 뒤 [↓] 가 이 열의 아래끝으로 창을 내립니다.
  const work = useRef<HTMLDivElement>(null)
  // 그 아래끝에 박는 표식. 이것이 보이면 이미 다 내려온 것이라 [↓] 가 할 일이 없습니다.
  const workEnd = useRef<HTMLDivElement>(null)
  const [atEnd, setAtEnd] = useState(false)
  // 관련 보고서 목록에서 지금 보고 있는 묶음. 생성에 쓰이는 쪽을 먼저 세웁니다.
  const [refTab, setRefTab] = useState<'written' | 'unwritten'>('written')

  const sourceKind = kind === '일일' ? '미팅' : kind === '주간' ? '일일' : '주간'
  const periodLabel = periodLabelFor(kind, dateISO)
  const existing = draft.existing
  const locked = existing?.status === '확정'
  // 아직 오지 않은 기간은 쓸 것이 없습니다. 주소를 직접 쳐도 막습니다.
  const isFuture = dateISO > TODAY_ISO

  const hasWork = draft.phase !== 'idle' || draft.dirtyIds.size > 0 || draft.transcript.length > 0
  // 생성 버튼이 머리말에 서므로 '지금 만들 수 있는가'와 '이미 만든 것이 있는가'를 한 곳에서 봅니다.
  const generating = draft.phase === 'generating'
  // 글이 자라는 동안 스크롤 상자가 바닥을 따라갑니다. 표식은 .reports 의 마지막 자식입니다.
  const streamEnd = useStickToBottom(generating)
  // 검토·수정이 남긴 말만 검토 메모로 갑니다. 나머지는 진행 상황입니다.
  const reviewNotes = (draft.generationProgress?.stage_results ?? [])
    .filter((item) => item.stage === 'review_initial' || item.stage === 'repair')
    .map((item) => item.body)
  // 고쳐 쓴 본문이 실제로 흐르기 시작하면 메모는 읽고 난 것입니다. 그때 위로 올립니다.
  // 검토가 끝난 시점은 아직 이릅니다 — 올려 두고 한참 기다리게 됩니다. 판(draft_version) 2 는
  // 수정 단계 본문에만 붙고, 병합이 되돌리지 않으므로 한 번 참이면 끝까지 참입니다.
  const revising = (draft.generationProgress?.previews ?? []).some(
    (item) => (item.draft_version ?? 1) >= 2,
  )
  const liveMemo = generating ? (
    <ReportReviewWarning evidence={draft.generationEvidence} generating notes={reviewNotes} />
  ) : null
  const busy = locked || pending || draft.recovering || generating
  // 멈출 수 있는 순간. 도는 run 이 있어야 하므로 activeRunId 까지 봅니다.
  const showStop = (generating || draft.recovering) && Boolean(draft.activeRunId)
  // AI 가 쓴 본문이 이미 이 화면에 있는가. 태그와 이어쓰기 안내가 같은 값을 봅니다.
  const aiWritten = draft.aiFilledIds.has('body')
  const hasDraftContent = draft.phase === 'ready'
  /*
   * 이 열에 AI 가 쓴 보고서가 놓여 있는가 — [↓] 가 설 조건입니다. 이번에 막 쓴 것
   * (aiFilledIds)뿐 아니라, 검토 대기인 보고서를 이어 쓰는 경우도 같은 자리를 얻습니다.
   * 이어 쓰기는 reset 에서 aiFilledIds 를 비우지만 저장된 aiEvidence 는 그대로 살립니다 —
   * 그래서 AI 가 쓴 긴 글이 놓여 있는데도 내려가는 손잡이만 없는 상태가 됐습니다.
   * 손으로만 쓴 보고서는 둘 다 비어 있으므로 여전히 서지 않습니다.
   */
  const aiReport = hasDraftContent && (aiWritten || draft.generationEvidence !== null)
  // 양식지의 첫 줄. 주간·월간은 덮는 기간을, 일일은 그날을 세웁니다.
  const docTitle = `${periodLabel ?? fmtDay(parseISO(dateISO))} ${kind} 업무 보고서`
  // 등록 단계에서는 아직 만든 것이 없습니다. 결과 자리를 비워 두지 않고 한 열만 씁니다.
  const showWork = !draft.hasAiFields || draft.phase !== 'idle'

  /*
   * 아래끝 표식이 창에 들어왔는가만 봅니다. 구르는 것은 창이므로 root 는 기본값(창)입니다.
   * [↓] 를 세울지 말지는 여전히 생성 상태가 정하고, 이 값은 이미 바닥인 동안만 잠시 감춥니다.
   */
  useEffect(() => {
    const mark = workEnd.current
    if (!mark) return
    const watch = new IntersectionObserver(([entry]) => setAtEnd(entry.isIntersecting))
    watch.observe(mark)
    return () => watch.disconnect()
  }, [showWork])

  const payload = {
    reportId: existing?.id,
    version: existing?.version,
    statusCode: existing?.apiStatus,
    date: dateISO,
    kind,
    approver: draft.approver,
    // 문서에 적힌 이름과 별개로, 제출하면 검토 요청은 팀장에게 갑니다.
    approverId: manager?.id ?? null,
    values: draft.values,
    activities: draft.activities,
    attachments: draft.attachments,
    transcript: draft.transcript,
  }

  // 기간만 바꿉니다. 종류(?kind=)는 그대로 두어야 양식이 바뀌지 않습니다.
  const changeDate = useCallback(
    (next: string) => {
      const query = new URLSearchParams(params)
      // 미리 골라 둔 자료는 그 날짜의 것이라 함께 버립니다.
      query.delete('pick')
      if (next === TODAY_ISO) query.delete('date')
      else query.set('date', next)
      setParams(query, { replace: true })
    },
    [params, setParams],
  )

  const onDateInput = (next: string) => {
    if (next === '' || periodStart(kind, next) === dateISO) return
    // 쓰던 내용은 기간이 바뀌면 사라집니다. 먼저 물어봅니다.
    if (hasWork) {
      setConfirm({ kind: 'date', next })
      return
    }
    changeDate(next)
  }

  // 생성에 쓰이는 줄(제출을 마친 것)과 그렇지 않은 줄을 나눠 세웁니다. 작성중은 뒤쪽입니다.
  const written = draft.activities.filter((item) => item.included)
  const unwritten = draft.activities.filter((item) => !item.included)
  const refList = refTab === 'written' ? written : unwritten
  const renderAside = (item: (typeof draft.activities)[number]) => {
    const meta = draft.meta.get(item.id)
    if (!meta) return null
    return (
      <>
        {/* 탭이 이미 말하는 상태는 줄에서 뺍니다. 검토 대기·반려처럼 탭과 다른 것만 답니다. */}
        {meta.tracked &&
          meta.status != null &&
          meta.status !== '확정' &&
          meta.status !== '작성완료' && <ReportStatusBadge status={meta.status} />}
        {/*
          쓰던 보고서를 두고 떠나지 않도록 원본은 새 창에서 엽니다.
          그래서 <Link> 가 아니라 버튼 모양의 <a target="_blank"> 입니다.
        */}
        {meta.to && (
          <a
            className={buttonClass({ variant: 'outline', size: 'sm' })}
            href={meta.to}
            target="_blank"
            rel="noopener noreferrer"
          >
            {meta.status == null ? '보고서 작성' : '보고서 확인'}
          </a>
        )}
      </>
    )
  }

  const runGenerate = async () => {
    try {
      await draft.generate()
    } catch {
      // 생성 훅이 오류를 표시합니다.
    }
  }

  const askRegenerate = () => {
    // 사람이 손댄 항목이 있으면 덮어써도 되는지 먼저 묻습니다.
    if (draft.phase === 'ready' && (existing || draft.dirtyIds.size > 0)) {
      setConfirm({ kind: 'regenerate' })
      return
    }
    void runGenerate()
  }

  const onGenerate = () => {
    // 생성에 쓰이는 것은 제출을 마친 줄뿐입니다. 남은 줄이 있으면 그 사실부터 알립니다.
    if (unwritten.length > 0) {
      setConfirm({ kind: 'unwritten' })
      return
    }
    askRegenerate()
  }

  const onSubmit = async () => {
    if (
      draft.attachmentsPending ||
      draft.recovering ||
      draft.loading ||
      draft.error ||
      draft.missing.length > 0 ||
      draft.phase !== 'ready' ||
      locked ||
      pending
    )
      return
    try {
      const report = await submitReport(payload, draft.generationRunId)
      setConfirm(null)
      navigate(dailyReportPath(report.id))
    } catch {
      // 훅이 같은 화면에 오류를 표시합니다.
    }
  }

  if (isFuture) {
    return (
      <section>
        <h1 className="sr-only">{kind}업무보고 작성</h1>
        <div className={styles.head}>
          <DailyListLink back tab={kindToPeriod(kind)} className={styles.back} />
        </div>
        <div className={styles.blank}>
          <p>아직 오지 않은 기간입니다. 지난 기간의 보고서만 쓸 수 있습니다.</p>
          <Link
            className={buttonClass({ variant: 'outline' }, styles.blankCta)}
            to={dailyComposePath(TODAY_ISO, kind)}
          >
            이번 {kind}보고서로 이동
            <ChevronRightIcon />
          </Link>
        </div>
      </section>
    )
  }

  return (
    <section className={styles.page}>
      <h1 className="sr-only">{kind}업무보고 작성</h1>

      {/*
        머리 띠. 상세 화면과 같은 것을 씁니다 — 어느 기간의 무슨 보고서인지, 지금 어디까지
        왔는지, 그리고 이 문서로 할 수 있는 일. 오른쪽 끝은 AI 에게 맡기는 길과 종이로
        뽑는 길입니다.
      */}
      <ReportBanner
        crumb={<DailyListLink crumb tab={kindToPeriod(kind)} />}
        title={periodLabel ?? fmtDot(parseISO(dateISO))}
        kind={`${kind}업무보고`}
        /* 이어 쓰는 보고서에만 상태가 있습니다. 새 보고서는 제목만 섭니다. */
        badge={existing && <ReportStatusBadge status={existing.status} />}
        meta={[
          <>
            <CalendarIcon width={14} height={14} />
            {fmtDot(parseISO(dateISO))}
          </>,
          <>
            <TeamIcon width={14} height={14} />
            작성자 {profile.name}
          </>,
          <>
            <SheetIcon width={14} height={14} />
            보고 대상 {draft.approver || '미지정'}
          </>,
        ]}
      >
        {/* 작성 시작 지점입니다. 이미 본문이 있으면 같은 버튼이 다시 작성으로 바뀝니다.
            쓰는 동안에는 진행을 오른쪽 열이 말하므로 이 자리에는 멈추는 길만 남깁니다. */}
        {draft.hasAiFields && !generating && (
          <Button
            type="button"
            variant={hasDraftContent ? 'outline' : 'primary'}
            aria-busy={draft.recovering}
            disabled={busy || !draft.canGenerate}
            onClick={onGenerate}
          >
            {hasDraftContent ? (
              <>
                <RefreshIcon width={16} height={16} />
                AI 보고서 다시 작성
              </>
            ) : (
              'AI 보고서 작성'
            )}
          </Button>
        )}

        {/*
          멈추는 길은 시작한 자리 바로 옆입니다 — 미팅 작성 화면과 같습니다.
          도는 run 은 activeRunId 입니다. generationRunId 는 끝난 뒤에야 서므로
          그것으로 게이팅하면 첫 생성에서 이 버튼이 나오지 않습니다.
        */}
        {draft.hasAiFields && showStop && (
          <Button
            type="button"
            variant="outline"
            disabled={draft.cancelling}
            onClick={() => void draft.cancelGeneration()}
          >
            <StopIcon />
            {draft.cancelling ? '중단 중…' : '생성 중단'}
          </Button>
        )}
      </ReportBanner>

      {/* 만들지 못했거나 멈춘 이야기. 이어 쓰기·반려 안내와 같은 자리에 섭니다. */}
      {draft.generationError && !generating && (
        <p className={styles.headNote} role="alert">
          {draft.generationError}
        </p>
      )}
      {draft.cancelError && (
        <p className={styles.headNote} role="alert">
          {draft.cancelError}
        </p>
      )}
      {draft.cancelled && (
        <p className={styles.headNote} role="status">
          생성이 중단되었습니다.
        </p>
      )}

      <ErrorToast message={loadError} onRetry={draft.reload} />

      {/* 이미 있는 보고서는 덮어쓰지 않고 이어서 씁니다. 승인 뒤에만 잠급니다.
          다시 작성을 누른 뒤로는 이어 쓰는 상황이 아니므로 이 안내는 물러납니다. */}
      {existing && !locked && !generating && !aiWritten && (
        <p className={styles.saved}>
          이 기간에 {existing.status}인 보고서가 있어 이어서 씁니다. 새 보고서를 만들지 않습니다.
        </p>
      )}

      {existing?.reviewNote && (
        <div className={styles.review} role="note">
          <strong>반려 사유</strong>
          <p>{existing.reviewNote}</p>
        </div>
      )}
      {locked && existing && (
        <p className={styles.locked}>
          {periodLabel ?? fmtDot(parseISO(dateISO))} 보고서는 이미 제출했습니다 · {existing.status}.{' '}
          <Link to={dailyReportPath(existing.id)}>제출한 보고서 열기</Link>
        </p>
      )}

      <div
        className={
          showWork
            ? sideCollapsed
              ? `${styles.layout} ${styles.sideCollapsed}`
              : styles.layout
            : `${styles.layout} ${styles.solo}`
        }
      >
        <div className={styles.side}>
          {/* 왼쪽 열 전체의 머리. 접기 손잡이는 아래 판들이 아니라 이 열을 여닫습니다.
              접으면 제목은 물러나고 손잡이만 레일로 남습니다. */}
          <ColumnHead title={!sideCollapsed && '보고서 자료'} bare={sideCollapsed}>
            {/* 접기 손잡이는 잠시 내려둡니다.
            {showWork && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                iconOnly
                className={styles.sideToggle}
                aria-expanded={!sideCollapsed}
                aria-controls="period-compose-side"
                aria-label={sideCollapsed ? '보고서 작성 자료 펼치기' : '보고서 작성 자료 접기'}
                onClick={() => setSideCollapsed((collapsed) => !collapsed)}
              >
                {sideCollapsed ? (
                  <ChevronRightIcon width={15} height={15} />
                ) : (
                  <ChevronLeftIcon width={15} height={15} />
                )}
              </Button>
            )}
            */}
          </ColumnHead>
          <div
            id="period-compose-side"
            className={
              sideCollapsed ? `${styles.sideContent} ${styles.collapsed}` : styles.sideContent
            }
          >
            <article className={styles.reference}>
              <h2 className={styles.inputTitle}>
                관련 보고서
                {/* 생성에 무엇이 쓰이는지는 목록 위가 아니라 카드 이름 옆에서 미리 알립니다. */}
                <span className={styles.refNote}>
                  <InfoIcon width={14} height={14} aria-hidden="true" />
                  작성 완료된 {sourceKind} 보고서만 반영됩니다.
                </span>
              </h2>
              {/*
              날짜가 이 카드의 머리말입니다. 덮는 기간이 하루든 한 주든 한 달이든 한 점을
              고르는 일이라 — 주는 어느 날을 찍든 그 주로 접힙니다 — 머리말 하나로 세웁니다.
            */}
              <DayHeader
                dateISO={dateISO}
                label={periodLabel}
                pickerType={kind === '월간' ? 'month' : 'date'}
                maxISO={TODAY_ISO}
                onDateChange={onDateInput}
              />

              {draft.relatedLoading ? (
                <div role="status">
                  <span className="sr-only">관련 보고서를 불러오는 중입니다.</span>
                  <Skeleton height={SOURCE_LIST_H} radius="var(--r-md)" />
                </div>
              ) : draft.relatedError ? (
                <div className={styles.blank}>
                  <p role="alert">{draft.relatedError}</p>
                  <Button variant="outline" onClick={draft.reloadRelated}>
                    다시 시도
                  </Button>
                </div>
              ) : (
                /* 탭과 목록은 한 덩이입니다 — 사이가 벌어지면 어느 묶음을 보는 중인지 흐려집니다. */
                <div>
                  <Tabs
                    items={[
                      { value: 'written', label: '작성완료', count: written.length },
                      { value: 'unwritten', label: '미작성', count: unwritten.length },
                    ]}
                    value={refTab}
                    onChange={setRefTab}
                    label="관련 보고서 작성 상태"
                    size="sm"
                    className={styles.refTabs}
                  />
                  <ActivityList
                    activities={refList}
                    renderAside={renderAside}
                    flush
                    empty={
                      refTab === 'written'
                        ? undefined
                        : `아직 ${sourceKind} 보고서가 없는 일정이 없습니다.`
                    }
                  />
                </div>
              )}
            </article>

            {draft.hasAiFields && (
              <div className={styles.input}>
                <AttachmentPanel
                  attachments={draft.attachments}
                  reportId={existing?.id}
                  gallery
                  title="보고서 참고자료"
                  icon={<DocumentsIcon width={18} height={18} />}
                  acceptedKinds={['image']}
                  description="선택 입력입니다. 배경자료로만 씁니다."
                  hint="JPG, PNG 등"
                  onAttach={(files, kinds) => void draft.addAttachments(files, kinds)}
                  onRemove={draft.removeAttachment}
                  note={`AI는 제출된 ${sourceKind} 보고서, 첨부 참고자료, 추가 결정사항 및 메모, 현재 작성한 본문을 바탕으로 작성합니다.`}
                  readOnly={locked || pending || draft.recovering || draft.phase === 'generating'}
                />
                <FormField label="추가 결정사항 및 메모" error={draft.guidanceError ?? undefined}>
                  <textarea
                    id="period-report-guidance"
                    rows={4}
                    value={draft.transcript}
                    readOnly={locked || pending || draft.recovering || draft.phase === 'generating'}
                    placeholder="보고서에 추가할 결정사항, 후속 조치, 참고할 상황을 입력하세요."
                    onChange={(event) => draft.setTranscript(event.target.value)}
                  />
                  <span className={styles.guidanceMeta}>
                    {reportTextLength(draft.transcript).toLocaleString()} / 2,000자 · 메모를 바꾼 뒤
                    AI 보고서 작성 버튼을 다시 눌러야 반영됩니다.
                  </span>
                </FormField>
              </div>
            )}
          </div>
        </div>

        {/* 화면에서 유일하게 떠 있는 면. 그것만으로 "내는 것은 여기" 가 전달됩니다. */}
        {showWork && (
          <div className={styles.work} ref={work}>
            {/* 왼쪽 열 머리와 같은 줄에 섭니다. 오른쪽 끝은 이 문서를 종이로 내보내는 자리입니다. */}
            <ColumnHead
              title={
                <>
                  보고서 작성
                  {/* 어디까지가 AI 가 쓴 것인지. 문서 안이 아니라 이 열의 머리에서 말합니다.
                      쓰는 동안에는 같은 자리에서 진행 중임을 말합니다. */}
                  {(generating || aiWritten) && (
                    <span className={styles.aiBadge}>{generating ? 'AI 작성중' : 'AI 작성'}</span>
                  )}
                </>
              }
            >
              {/* 이 문서를 종이로 내보내는 자리. 인쇄가 곧 PDF 입니다. */}
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={draft.phase === 'idle' || draft.phase === 'generating'}
                onClick={() => window.print()}
              >
                <DownloadIcon width={15} height={15} />
                PDF 다운로드
              </Button>
            </ColumnHead>
            {/* 끝난 뒤에 남는 한 줄. 생성 중에는 흐름 맨 아래에서 쌓입니다. */}
            {!generating && <ReportReviewWarning evidence={draft.generationEvidence} />}
            {revising && liveMemo}
            <div
              className={
                generating ? `${styles.reports} ${styles.reportsGenerating}` : styles.reports
              }
            >
              {draft.phase === 'generating' ? (
                <GenerationProgress
                  feed="steps"
                  progress={draft.generationProgress}
                  previews={draft.generationProgress?.previews}
                  preview={draft.generationProgress?.previews.find(
                    (item) => item.section === 'body',
                  )}
                  reportKind="period"
                />
              ) : (
                <>
                  {/* 다 쓰인 뒤에는 양식지가 됩니다. 이 머리표가 그대로 PDF 의 머리글입니다. */}
                  {draft.phase !== 'idle' && (
                    <ReportDocHeader
                      title={docTitle}
                      author={profile.name}
                      jobTitle={profile.title}
                      department={profile.department}
                      company={profile.company}
                      writtenOn={fmtDot(parseISO(TODAY_ISO))}
                      approver={draft.approver}
                      /* 본문과 같은 규칙입니다 — 아래 [수정] 을 눌러야 이 칸이 열립니다. */
                      onApproverChange={editing && !locked ? draft.setApprover : undefined}
                    />
                  )}
                  {/* 평소에는 문서로 읽고, 아래 [수정] 을 눌러야 고칩니다 — 미팅 보고서와 같습니다. */}
                  <EditableReport
                    body={draft.values.body ?? ''}
                    docKey={draft.docKey}
                    disabled={locked || draft.recovering}
                    editing={editing}
                    onChange={(body) => draft.setValue('body', body)}
                    placeholder={draft.template.fields[0]?.placeholder}
                  />
                  {/* 제출을 막는 이유만 답니다. 낼 수 있을 때는 버튼이 스스로 말합니다. */}
                  {draft.missing.length > 0 && (
                    <p className={styles.missing}>제출 전 확인: {draft.missing.join(', ')}</p>
                  )}
                </>
              )}
              {/* 검토는 초안 다음에 일어납니다. 수정이 시작되면 이 상자는 위로 올라갑니다. */}
              {!revising && liveMemo}
              {/* 지금 하는 일은 늘 마지막 글입니다. 바닥까지 내려 읽어도 이 줄이 보입니다. */}
              {generating && (
                <GenerationProgress
                  feed="live"
                  progress={draft.generationProgress}
                  reportKind="period"
                />
              )}
              {generating && (
                <div ref={streamEnd} className={styles.streamEnd} aria-hidden="true" />
              )}
            </div>

            {/*
              쓰는 중인지 다 썼는지를 한 자리에서 말합니다. 쓰는 동안에는 점 세 개로
              "아직 쓰는 중"만 알리고 — 누를 것이 아니므로 버튼이 아닙니다 — 다 쓰이면
              같은 자리가 보고서 아래끝으로 내려가는 손잡이가 됩니다. 둘은 겹치지 않습니다.
            */}
            {generating ? (
              <div className={styles.dots} role="status" aria-label="AI가 보고서를 작성 중입니다">
                <span />
                <span />
                <span />
              </div>
            ) : (
              aiReport && (
                <Button
                  type="button"
                  variant="outline"
                  iconOnly
                  // 이미 바닥이면 자리까지 비웁니다 — 마지막 글과 조작부 사이가 벌어집니다.
                  className={atEnd ? `${styles.jump} ${styles.atEnd}` : styles.jump}
                  aria-label="보고서 맨 아래로 이동"
                  onClick={() => work.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })}
                >
                  <ArrowDownIcon width={18} height={18} />
                </Button>
              )
            )}

            {/*
              이 화면의 조작부입니다. 보고서 맨 아래, 마지막 글 다음에 놓입니다 — 다 읽고
              내려온 자리에서 고치거나 냅니다. 종이로 뽑는 길은 이 열의 머리에 있습니다.
              쓰는 동안에는 누를 것이 하나도 없으므로 바 자체를 내립니다.
            */}
            {!generating && (
              <div className={styles.saveBar}>
                {editing ? (
                  <>
                    <Button
                      variant="outline"
                      type="button"
                      onClick={() => setConfirm({ kind: 'cancelEdit' })}
                    >
                      취소
                    </Button>
                    <Button type="button" onClick={() => setConfirm({ kind: 'finishEdit' })}>
                      수정 완료
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      variant="outline"
                      type="button"
                      disabled={
                        locked ||
                        draft.recovering ||
                        draft.phase === 'idle' ||
                        draft.phase === 'generating'
                      }
                      onClick={() => {
                        bodySnapshot.current = draft.values.body ?? ''
                        approverSnapshot.current = draft.approver
                        setEditing(true)
                      }}
                    >
                      수정
                    </Button>
                    <Button
                      type="button"
                      disabled={
                        draft.missing.length > 0 ||
                        locked ||
                        pending ||
                        draft.phase === 'idle' ||
                        draft.phase === 'generating' ||
                        draft.recovering ||
                        draft.attachmentsPending ||
                        draft.loading ||
                        Boolean(draft.error)
                      }
                      onClick={() => setConfirm({ kind: 'submit' })}
                    >
                      보고서 제출
                    </Button>
                  </>
                )}
              </div>
            )}

            {/* 이 열의 아래끝. 1px 만 차지하고, 보이는지 여부가 [↓] 를 감출지 정합니다. */}
            <div ref={workEnd} className={styles.workEnd} aria-hidden="true" />
          </div>
        )}
      </div>

      {confirm?.kind === 'unwritten' && (
        <Modal
          title={`미작성 보고서가 ${unwritten.length}건 있습니다`}
          description={`작성을 마친 ${written.length}건만으로 ${kind}보고서를 작성합니다.`}
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setConfirm(null)
                  askRegenerate()
                }}
              >
                이대로 작성
              </Button>
            </>
          }
        >
          <p>
            미작성 일정은 이번 작성에 반영되지 않습니다. 먼저 쓰려면 목록에서 보고서 작성을
            누르세요.
          </p>
        </Modal>
      )}

      {confirm?.kind === 'regenerate' && (
        <Modal
          title="직접 고친 내용을 덮어쓸까요?"
          description="AI가 채우는 항목은 새 결과로 바뀝니다. 직접 입력 전용 항목은 유지됩니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setConfirm(null)
                  void runGenerate()
                }}
              >
                다시 작성
              </Button>
            </>
          }
        >
          <p>
            {existing
              ? '저장된 보고서의 AI 작성 항목이 새 후보로 바뀝니다.'
              : `지금까지 ${draft.dirtyIds.size}개 항목을 직접 고쳤습니다. AI 작성 항목의 수정 내용이 새 후보로 바뀝니다.`}
          </p>
        </Modal>
      )}

      {confirm?.kind === 'date' && (
        <Modal
          title={`${DATE_LABEL[kind]} 바꿀까요?`}
          description="다른 기간으로 옮기면 작성 중인 내용은 사라집니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  changeDate(confirm.next)
                  setConfirm(null)
                }}
              >
                기간 바꾸기
              </Button>
            </>
          }
        >
          <p>
            {periodLabelFor(kind, confirm.next) ?? fmtDot(parseISO(confirm.next))} 보고서로
            옮깁니다.
          </p>
        </Modal>
      )}

      {confirm?.kind === 'submit' && (
        <Modal
          title="보고서를 제출하시겠어요?"
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button
                type="button"
                disabled={
                  pending ||
                  draft.attachmentsPending ||
                  draft.recovering ||
                  draft.missing.length > 0
                }
                onClick={onSubmit}
              >
                {pending ? '제출 중…' : '제출'}
              </Button>
            </>
          }
        >
          <p>
            {periodLabel ?? fmtDot(parseISO(dateISO))} {kind} 보고서를 제출합니다.
          </p>
        </Modal>
      )}

      {/* 수정에서 나가는 두 길. 고친 것이 사라지는 쪽은 한 번 더 묻습니다. */}
      {confirm?.kind === 'cancelEdit' && (
        <Modal
          title="수정을 취소하시겠어요?"
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                돌아가기
              </Button>
              <Button
                type="button"
                onClick={() => {
                  draft.setValue('body', bodySnapshot.current)
                  draft.setApprover(approverSnapshot.current)
                  setEditing(false)
                  setConfirm(null)
                }}
              >
                수정 취소
              </Button>
            </>
          }
        >
          <p>수정한 내용이 사라지고 수정 전 내용으로 되돌아갑니다.</p>
        </Modal>
      )}

      {confirm?.kind === 'finishEdit' && (
        <Modal
          title="수정을 완료하시겠어요?"
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                계속 수정
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setEditing(false)
                  setConfirm(null)
                }}
              >
                수정 완료
              </Button>
            </>
          }
        >
          <p>현재 내용으로 수정 완료합니다.</p>
        </Modal>
      )}
    </section>
  )
}

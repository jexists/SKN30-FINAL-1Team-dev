// 업무 보고서 작성 화면.
//
// 왼쪽은 미팅 공통 정보·원문이고, 오른쪽은 선택한 딜마다 하나씩 생기는 보고서입니다.
// 카드 한 장이 report 한 행이자 sales_deal 한 건이라 저장·Agent·ML 상태가 섞이지 않습니다.
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import { errorMessage } from '@/api/errorMessage'
import { applyMeetingProcessing, processMeeting, saveMeetingNotes } from '@/api/reportAgent'
import Button, { buttonClass } from '@/components/Button'
import { ChevronLeftIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { SkeletonDetail } from '@/components/Skeleton'
import { meetingPickPath, meetingReportPath, ROUTES } from '@/constants/routes'
import { isOwnAgendaItem, useAgendaItem } from '@/shared/agenda'
import { showToast } from '@/shared/toast'
import type { MeetingAssignmentOverride, MeetingDealRef } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'

import DealReportCard from './components/DealReportCard'
import MeetingInfoPanel from './components/MeetingInfoPanel'
import MeetingInputPanel from './components/MeetingInputPanel'
import MeetingSharedPanel from './components/MeetingSharedPanel'
import { canReassignEvidence, runDealGeneration } from './generatedDraft'
import useCompanyDeals from './useCompanyDeals'
import useMeetingDraft from './useMeetingDraft'
import useMeetingReports, {
  type MeetingDraftPayload,
  toMeetingReport,
  useMeetingReportsOfAgenda,
} from './useMeetingReports'

import styles from './Compose.module.scss'

type Confirm = { kind: 'apply'; dealId: string } | null

export default function Compose() {
  const [params] = useSearchParams()
  const { memberId, isManager } = useCurrentUser()
  const activeGenerations = useRef(new Set<string>())
  const processingAbort = useRef<AbortController | null>(null)
  const [generating, setGenerating] = useState(false)
  const [savingNotes, setSavingNotes] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [runErrors, setRunErrors] = useState<Record<string, string>>({})
  const [notesDirty, setNotesDirty] = useState(false)
  const agendaId = params.get('agenda') ?? ''
  useEffect(() => {
    setGenerating(false)
    setSavingNotes(false)
    setNotesDirty(false)
    setRunError(null)
    setRunErrors({})
    return () => {
      processingAbort.current?.abort()
      processingAbort.current = null
    }
  }, [agendaId])
  const {
    item,
    loading: agendaLoading,
    error: agendaError,
    reload: reloadAgenda,
  } = useAgendaItem(agendaId)
  const {
    reports: savedReports,
    loading,
    error: loadError,
    reload,
  } = useMeetingReportsOfAgenda(agendaId)
  const { saveDraft, error: saveError, pending } = useMeetingReports()
  const draft = useMeetingDraft(
    item,
    savedReports,
    !agendaLoading && !loading && !agendaError && !loadError && item?.id === agendaId,
  )
  const deals = useCompanyDeals(item?.customerCompanyId)
  const [confirm, setConfirm] = useState<Confirm>(null)

  if (agendaLoading || loading) {
    return (
      <section>
        <SkeletonDetail label="업무 보고서를 불러오는 중입니다." title height={520} />
      </section>
    )
  }

  if (agendaError || loadError) {
    return (
      <section>
        <p className={styles.notFound} role="alert">
          {agendaError ?? loadError}
        </p>
        <Button
          variant="outline"
          onClick={() => {
            reloadAgenda()
            reload()
          }}
        >
          다시 시도
        </Button>
      </section>
    )
  }

  if (!item) {
    return (
      <section>
        <h1 className="sr-only">업무 보고서 작성</h1>
        <p className={styles.notFound}>
          기록할 일정을 찾을 수 없습니다.{' '}
          <Link to={ROUTES.DASHBOARD}>대시보드에서 일정을 고르세요.</Link>
        </p>
      </section>
    )
  }

  const savedByDeal = new Map(
    savedReports.flatMap((report) => (report.salesDealId ? [[report.salesDealId, report]] : [])),
  )
  const unassignedReports = savedReports.filter((report) => !report.salesDealId)
  const canWrite = isOwnAgendaItem(item, memberId, isManager)
  const canEditDeal = (dealId: string) =>
    canWrite && (!savedByDeal.has(dealId) || savedByDeal.get(dealId)?.ownerMemberId === memberId)
  const lockedDealIds = savedReports.flatMap((report) =>
    report.review === 'approved' && report.salesDealId ? [report.salesDealId] : [],
  )
  const fixedDealIds = draft.salesDealIds.filter(
    (dealId) => draft.draftsByDeal[dealId]?.reportId !== undefined,
  )
  const busy = pending || generating || savingNotes
  const when = `${fmtDot(parseISO(item.date))} ${item.time}`

  const dealRef = (dealId: string): MeetingDealRef => {
    const deal = deals.deals.find((one) => one.id === dealId)
    if (deal) return { id: dealId, label: deal.no, note: deal.title.trim() || deal.product }
    return savedByDeal.get(dealId)?.salesDeal ?? { id: dealId, label: dealId }
  }

  const payloadFor = (dealId: string): MeetingDraftPayload => {
    const state = draft.draftsByDeal[dealId]
    if (!state) throw new Error('deal_draft_not_found')
    const deal = deals.deals.find((one) => one.id === dealId)
    return {
      reportId: state.reportId,
      statusCode: state.statusCode,
      agendaId: item.id,
      salesDealId: dealId,
      salesDeal: dealRef(dealId),
      template: state.template,
      date: item.date,
      time: item.time,
      hospital: item.hospital,
      dept: item.dept,
      contact: item.contact,
      product: deal?.product ?? item.product,
      place: item.place,
      title: state.title,
      transcript: draft.transcript,
      values: state.values,
      attachments: draft.attachments,
      evidence: state.evidence,
      aiValues: state.aiValues,
      aiEvidence: state.aiEvidence,
      aiGeneratedAt: state.aiGeneratedAt,
    }
  }

  const generatable =
    draft.salesDealIds.length > 0 &&
    draft.salesDealIds.every(
      (id) => canEditDeal(id) && draft.draftsByDeal[id]?.statusCode === 'draft',
    )
  const result = draft.meetingResult
  const canReassign =
    generatable &&
    !!result?.evidence &&
    canReassignEvidence(
      result.evidence.transcript_sha256,
      draft.transcriptSha256,
      result.evidence.selected_deal_ids,
      draft.salesDealIds,
    )
  const canEditNotes =
    canWrite &&
    !!result &&
    !!result.shared?.revision &&
    draft.salesDealIds.every(
      (id) =>
        canEditDeal(id) &&
        ['draft', 'changes_requested'].includes(draft.draftsByDeal[id]?.statusCode),
    )

  // 잠금 키는 딜이 아니라 미팅입니다. 사전저장부터 서버 apply까지 한 번만 실행합니다.
  const generateAll = async (overrides: MeetingAssignmentOverride[] = []) => {
    if (busy || activeGenerations.current.has(agendaId) || !generatable || !draft.canGenerate)
      return false
    if (notesDirty) {
      setRunError('수정한 공통·미지정 메모를 먼저 저장한 뒤 다시 생성하세요.')
      return false
    }
    if (overrides.length && !canReassign) return false
    const targets = [...draft.salesDealIds]
    const controller = new AbortController()
    processingAbort.current = controller
    return runDealGeneration(
      activeGenerations.current,
      agendaId,
      () => {
        if (!controller.signal.aborted) setGenerating(activeGenerations.current.has(agendaId))
      },
      async () => {
        setRunError(null)
        setRunErrors({})
        draft.beginGeneration(targets)
        try {
          const reports = await Promise.all(
            targets.map(async (id) => {
              const report = await saveDraft(payloadFor(id))
              if (!controller.signal.aborted) draft.bindReport(id, report)
              return report
            }),
          )
          if (controller.signal.aborted) return false
          const run = await processMeeting(
            reports.map((report) => report.id),
            overrides.length
              ? {
                  parent_run_id: result!.runId,
                  assignment_overrides: overrides,
                }
              : undefined,
            (progress) => {
              if (controller.signal.aborted || processingAbort.current !== controller) return
              draft.receiveProgress({
                ...progress,
                previews: progress.previews.filter(
                  (preview) =>
                    preview.section !== 'deal' || targets.includes(preview.sales_deal_id!),
                ),
              })
            },
            controller.signal,
          )
          if (controller.signal.aborted) return false
          const persisted = await applyMeetingProcessing(run.id)
          if (controller.signal.aborted) return false
          draft.acceptGenerated(
            persisted.map(toMeetingReport),
            run.output_snapshot.reports === null,
          )
          setRunErrors(run.output_snapshot.errors)
          showToast(
            Object.keys(run.output_snapshot.errors).length
              ? '미팅 처리가 일부 완료됐습니다. 실패한 항목을 확인하세요.'
              : `${targets.length}개 딜의 보고서와 분석 결과를 저장했습니다.`,
          )
          return true
        } catch (reason: unknown) {
          if (controller.signal.aborted) return false
          draft.generationFailed(targets, reason)
          setRunError(errorMessage(reason, '미팅 처리를 완료하지 못했습니다.'))
          return false
        }
      },
    )
  }

  const saveShared = async (common: string | null, unassigned: string | null) => {
    if (busy || !canEditNotes || !result) return
    const controller = new AbortController()
    processingAbort.current = controller
    setSavingNotes(true)
    setRunError(null)
    try {
      const reports = await saveMeetingNotes(
        result.runId,
        result.shared!.revision,
        common,
        unassigned,
      )
      if (controller.signal.aborted) return
      draft.acceptShared(reports.map(toMeetingReport))
      showToast('미팅 공통·미지정 메모를 저장했습니다.')
    } catch (reason: unknown) {
      if (controller.signal.aborted) return
      setRunError(errorMessage(reason, '미팅 메모를 저장하지 못했습니다.'))
    } finally {
      if (!controller.signal.aborted) setSavingNotes(false)
    }
  }

  const saveOne = async (dealId: string) => {
    if (activeGenerations.current.has(agendaId) || !canEditDeal(dealId) || busy) return
    try {
      const report = await saveDraft(payloadFor(dealId))
      draft.bindReport(dealId, report)
      showToast(`${dealRef(dealId).label} 보고서를 저장했습니다.`)
    } catch {
      // 저장 훅이 카드 목록 위에 오류를 표시합니다.
    }
  }

  const printable = draft.salesDealIds.some(
    (dealId) => draft.draftsByDeal[dealId]?.phase === 'ready',
  )

  return (
    <section className={styles.page}>
      <h1 className="sr-only">
        {item.hospital} {item.title} 업무 보고서 작성
      </h1>

      <div className={styles.head}>
        <Link
          className={buttonClass({ variant: 'outline' }, styles.back)}
          to={meetingPickPath(item.date)}
        >
          <ChevronLeftIcon width={15} height={15} />
          일정 고르기
        </Link>

        <Button
          variant="outline"
          type="button"
          disabled={!printable}
          onClick={() => window.print()}
        >
          PDF 다운로드
        </Button>
      </div>

      {lockedDealIds.length > 0 && (
        <p className={styles.locked}>
          팀장 확인이 끝난 딜 보고서 {lockedDealIds.length}건은 수정할 수 없습니다.{' '}
          <Link to={meetingReportPath(savedByDeal.get(lockedDealIds[0])?.id ?? '')}>
            확인 완료 보고서 열기
          </Link>
        </p>
      )}

      {(saveError || runError) && (
        <p className={styles.mutationError} role="alert">
          {saveError || runError}
        </p>
      )}
      {Object.keys(runErrors).length > 0 && (
        <div className={styles.mutationError} role="alert">
          <p>일부 처리가 완료되지 않았습니다. 저장된 보고서와 기존 작성 내용은 유지됩니다.</p>
          <ul>
            {Object.entries(runErrors).map(([step, message]) => (
              <li key={step}>{message}</li>
            ))}
          </ul>
        </div>
      )}

      {unassignedReports.map((report) => (
        <p className={styles.locked} key={report.id}>
          딜이 지정되지 않은 기존 보고서는 원본 그대로 보관했습니다.{' '}
          <Link to={meetingReportPath(report.id)}>{report.title || '기존 보고서'} 열기</Link>
        </p>
      ))}

      <div className={styles.layout}>
        <div className={styles.side}>
          <aside className={styles.reference}>
            <div className={styles.refHead}>
              <h2 className={styles.refTitle}>미팅 정보</h2>
              {item.stage && <span className={styles.pill}>{item.stage}</span>}
            </div>

            <MeetingInfoPanel
              item={item}
              deals={deals.deals}
              dealsLoading={deals.loading}
              dealsError={deals.error}
              onReloadDeals={deals.reload}
              selectedDealIds={draft.salesDealIds}
              fixedDealIds={fixedDealIds}
              onToggleDeal={draft.toggleSalesDeal}
              disabled={busy || !canWrite}
            />
          </aside>

          <div className={styles.input}>
            <MeetingInputPanel
              attachments={draft.attachments}
              onAttach={(files) => void draft.addAttachments(files)}
              onRemoveAttachment={draft.removeAttachment}
              attachmentError={draft.attachmentError}
              transcript={draft.transcript}
              onTranscriptChange={draft.setTranscript}
              canGenerate={draft.canGenerate && generatable && !notesDirty}
              generating={generating}
              contentLabel="미팅 내용"
              generateLabel="미팅 전체 분석·보고서 작성"
              disabled={busy || !canWrite}
              onGenerate={() => void generateAll()}
            />
            {draft.salesDealIds.length > 0 && !generatable && (
              <p className={styles.generationNote}>
                선택한 딜 중 읽기 전용 또는 작성중이 아닌 보고서가 있어 미팅 전체를 다시 생성할 수
                없습니다.
              </p>
            )}
            {notesDirty && (
              <p className={styles.generationNote}>
                수정한 공통·미지정 메모를 먼저 저장하면 다시 생성할 수 있습니다.
              </p>
            )}
            <p className={styles.generationNote}>
              한 번 실행하면 선택한 모든 딜을 함께 처리합니다. 새 AI 원본은 직접 작성한 본문을
              덮어쓰지 않습니다.
            </p>
          </div>
        </div>

        <section className={styles.work} aria-label="딜별 미팅보고서">
          {(result || draft.processingProgress) && (
            <MeetingSharedPanel
              shared={result?.shared ?? null}
              evidence={result?.evidence}
              progress={draft.processingProgress}
              deals={draft.salesDealIds.map(dealRef)}
              disabled={busy}
              canReassign={canReassign}
              onSave={canEditNotes ? saveShared : undefined}
              onDirtyChange={setNotesDirty}
              onAssign={canWrite ? (assignments) => void generateAll(assignments) : undefined}
            />
          )}
          {draft.salesDealIds.length === 0 ? (
            <div className={styles.noDeals}>
              <h2>보고서를 작성할 딜을 선택하세요</h2>
              <p>왼쪽 영업 현황에서 하나 이상 선택하면 딜별 보고서 카드가 만들어집니다.</p>
            </div>
          ) : (
            draft.salesDealIds.map((dealId) => {
              const state = draft.draftsByDeal[dealId]
              if (!state) return null
              const deal = deals.deals.find((one) => one.id === dealId)

              return (
                <DealReportCard
                  key={dealId}
                  dealId={dealId}
                  deal={deal}
                  savedDeal={savedByDeal.get(dealId)?.salesDeal}
                  draft={state}
                  progress={draft.processingProgress}
                  template={state.template}
                  when={when}
                  saving={pending}
                  generating={generating}
                  canGenerate={draft.canGenerate && generatable && !notesDirty}
                  readOnly={!canEditDeal(dealId) || savingNotes}
                  onTitleChange={(value) => draft.setTitle(dealId, value)}
                  onChange={(values, missing) => draft.applyDocument(dealId, values, missing)}
                  onRestoreSections={() => draft.restoreSections(dealId)}
                  onStartManual={() => draft.startManual(dealId)}
                  onApplyAi={() => setConfirm({ kind: 'apply', dealId })}
                  onGenerate={() => void generateAll()}
                  onSave={() => void saveOne(dealId)}
                />
              )
            })
          )}
        </section>
      </div>

      {confirm?.kind === 'apply' && (
        <Modal
          title="새 AI 원본을 최종 보고서에 적용할까요?"
          description="직접 고친 내용도 이 딜의 새 AI 원본으로 바뀝니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  draft.applyAi(confirm.dealId)
                  showToast(`${dealRef(confirm.dealId).label}의 새 AI 원본을 적용했습니다.`)
                  setConfirm(null)
                }}
              >
                적용
              </Button>
            </>
          }
        >
          <p>적용하지 않고 AI 원본을 참고하면서 보고서를 직접 고쳐도 됩니다.</p>
        </Modal>
      )}
    </section>
  )
}

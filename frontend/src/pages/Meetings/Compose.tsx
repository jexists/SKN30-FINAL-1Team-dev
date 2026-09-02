// 업무 보고서 작성 화면.
//
// 왼쪽은 미팅 공통 정보·원문이고, 오른쪽은 선택한 딜마다 하나씩 생기는 보고서입니다.
// 저장할 때는 공통 기록과 모든 딜 카드를 미팅 보고서 한 건으로 묶습니다.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { isAxiosError } from 'axios'

import { useCurrentUser } from '@/auth/sessionContext'
import { errorMessage } from '@/api/errorMessage'
import {
  createReportGeneration,
  finishIdempotencyAttempt,
  idempotencyAttemptFor,
  isAgentRunTerminalError,
  latestMeetingProcessing,
  requiresRecoveryConfirmation,
  waitForMeetingProcessing,
} from '@/api/reportAgent'
import Button, { buttonClass } from '@/components/Button'
import { ChevronLeftIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { SkeletonDetail } from '@/components/Skeleton'
import { meetingPickPath, meetingReportPath, ROUTES } from '@/constants/routes'
import { isOwnAgendaItem, useAgendaItem } from '@/shared/agenda'
import { showToast } from '@/shared/toast'
import type { IdempotencyAttempt } from '@/api/reportAgent'
import type {
  AgentRunResponse,
  MeetingDealRef,
  MeetingProcessingOutput,
  ReportGenerationInput,
} from '@/types'
import { fmtDot, parseISO } from '@/utils/date'

import DealReportCard from './components/DealReportCard'
import MeetingInfoPanel from './components/MeetingInfoPanel'
import MeetingInputPanel from './components/MeetingInputPanel'
import MeetingSharedPanel from './components/MeetingSharedPanel'
import useCompanyDeals from './useCompanyDeals'
import useMeetingDraft, { hasMeetingDraftContent } from './useMeetingDraft'
import useMeetingReports, {
  type MeetingDealDraftPayload,
  type MeetingDraftPayload,
  meetingGenerationRequestOf,
  useMeetingReportOfAgenda,
} from './useMeetingReports'

import styles from './Compose.module.scss'

type Confirm = { kind: 'regenerate' } | null

function meetingInputOf(
  run: AgentRunResponse<MeetingProcessingOutput>,
  agendaId: string,
): ReportGenerationInput {
  const input = run.generation_input
  if (
    !input ||
    input.report_kind !== 'meeting' ||
    input.source_activity_id !== agendaId ||
    !input.transcript ||
    input.sales_deal_ids.length === 0
  ) {
    throw new Error('report_generation_input_missing')
  }
  return input
}

export default function Compose() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { memberId, isManager } = useCurrentUser()
  const generationAbort = useRef<AbortController | null>(null)
  const generationAttempt = useRef<IdempotencyAttempt | undefined>(undefined)
  const recoveryAbort = useRef<AbortController | null>(null)
  const submitAbort = useRef<AbortController | null>(null)
  const recoveredAgendaId = useRef('')
  const [generating, setGenerating] = useState(false)
  const [recovering, setRecovering] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [runErrors, setRunErrors] = useState<Record<string, string>>({})
  const [pendingRecovery, setPendingRecovery] =
    useState<AgentRunResponse<MeetingProcessingOutput> | null>(null)
  const agendaId = params.get('agenda') ?? ''
  useEffect(() => {
    setGenerating(false)
    setRecovering(true)
    setSubmitting(false)
    setRunError(null)
    setRunErrors({})
    setPendingRecovery(null)
    recoveredAgendaId.current = ''
    generationAttempt.current = undefined
    return () => {
      generationAbort.current?.abort()
      generationAbort.current = null
      recoveryAbort.current?.abort()
      recoveryAbort.current = null
      submitAbort.current?.abort()
      submitAbort.current = null
    }
  }, [agendaId])
  const {
    item,
    loading: agendaLoading,
    error: agendaError,
    reload: reloadAgenda,
  } = useAgendaItem(agendaId)
  const {
    report: savedReport,
    loading,
    error: loadError,
    reload,
  } = useMeetingReportOfAgenda(agendaId)
  const { finalizeReport, error: saveError, pending } = useMeetingReports()
  const draftReady =
    !agendaLoading && !loading && !agendaError && !loadError && item?.id === agendaId
  const draft = useMeetingDraft(item, savedReport, draftReady)
  const {
    beginGeneration,
    receiveProgress,
    acceptGenerated,
    generationFailed,
    restoreGenerationInput,
  } = draft

  const resumeGeneration = useCallback(
    async (run: AgentRunResponse<MeetingProcessingOutput>, controller: AbortController) => {
      let dealIds: string[] = []
      try {
        const input = meetingInputOf(run, agendaId)
        dealIds = input.sales_deal_ids
        restoreGenerationInput(input)
        beginGeneration(dealIds)
        if (run.status_code === 'failed' || run.status_code === 'cancelled') {
          throw new Error(run.error_code ?? run.error_message ?? 'agent_run_failed')
        }
        const completed = ['queued', 'running'].includes(run.status_code)
          ? await waitForMeetingProcessing(run, receiveProgress, controller.signal)
          : run
        if (!completed.output_snapshot) throw new Error('agent_run_failed')
        if (controller.signal.aborted) return
        acceptGenerated(completed.id, completed.output_snapshot)
        setRunErrors(completed.output_snapshot.errors)
      } catch (reason: unknown) {
        if (!controller.signal.aborted) {
          if (dealIds.length) generationFailed(dealIds, reason)
          setRunError(errorMessage(reason, '진행 중인 보고서를 복구하지 못했습니다.'))
        }
      } finally {
        if (recoveryAbort.current === controller) {
          recoveryAbort.current = null
          setRecovering(false)
        }
      }
    },
    [
      agendaId,
      restoreGenerationInput,
      beginGeneration,
      receiveProgress,
      acceptGenerated,
      generationFailed,
    ],
  )

  useEffect(() => {
    if (!draftReady || recoveredAgendaId.current === agendaId) return
    if (
      savedReport &&
      (savedReport.ownerMemberId !== memberId ||
        !['draft', 'changes_requested'].includes(savedReport.apiStatus ?? ''))
    ) {
      recoveredAgendaId.current = agendaId
      setRecovering(false)
      return
    }
    recoveredAgendaId.current = agendaId
    const controller = new AbortController()
    recoveryAbort.current = controller
    setRecovering(true)
    void latestMeetingProcessing(agendaId, controller.signal)
      .then((run) => {
        if (controller.signal.aborted || generationAbort.current) return
        meetingInputOf(run, agendaId)
        if (requiresRecoveryConfirmation(savedReport?.id)) {
          setPendingRecovery(run)
          if (recoveryAbort.current === controller) {
            recoveryAbort.current = null
            setRecovering(false)
          }
          return
        }
        return resumeGeneration(run, controller)
      })
      .catch((reason: unknown) => {
        if (
          !controller.signal.aborted &&
          (!isAxiosError(reason) || reason.response?.status !== 404)
        ) {
          setRunError(errorMessage(reason, '진행 중인 보고서 상태를 확인하지 못했습니다.'))
        }
        if (recoveryAbort.current === controller) {
          recoveryAbort.current = null
          setRecovering(false)
        }
      })
    return () => controller.abort()
  }, [agendaId, draftReady, memberId, savedReport, resumeGeneration])
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
    savedReport?.dealSections.map((section) => [section.salesDealId, section]) ?? [],
  )
  const canWrite = isOwnAgendaItem(item, memberId, isManager)
  const canEdit =
    canWrite &&
    (!savedReport ||
      (savedReport.ownerMemberId === memberId &&
        (savedReport.apiStatus === 'draft' || savedReport.apiStatus === 'changes_requested')))
  const canEditDeal = (_dealId: string) => canEdit
  const lockedDealIds = savedReport?.review === 'approved' ? [...draft.salesDealIds] : []
  const fixedDealIds = draft.salesDealIds.filter(
    (dealId) => draft.draftsByDeal[dealId]?.reportId !== undefined,
  )
  const busy = pending || generating || recovering || submitting
  const when = `${fmtDot(parseISO(item.date))} ${item.time}`

  const dealRef = (dealId: string): MeetingDealRef => {
    const deal = deals.deals.find((one) => one.id === dealId)
    const saved = savedByDeal.get(dealId)?.salesDeal
    const label = (deal?.no ?? saved?.label ?? dealId).trim().slice(0, 254) || dealId
    const note = (deal ? deal.title.trim() || deal.product : saved?.note)?.trim().slice(0, 5_000)
    return { id: dealId, label, ...(note ? { note } : {}) }
  }

  const sectionPayloadFor = (dealId: string): MeetingDealDraftPayload => {
    const state = draft.draftsByDeal[dealId]
    if (!state) throw new Error('deal_draft_not_found')
    const deal = deals.deals.find((one) => one.id === dealId)
    return {
      salesDealId: dealId,
      salesDeal: dealRef(dealId),
      product: deal?.product ?? savedByDeal.get(dealId)?.product ?? item.product,
      title: state.title,
      values: state.values,
      evidence: state.evidence,
    }
  }

  const payloadForMeeting = (): MeetingDraftPayload => {
    const first = draft.draftsByDeal[draft.salesDealIds[0]]
    if (!first) throw new Error('meeting_draft_not_found')
    return {
      reportId: savedReport?.id ?? first.reportId,
      version: first.reportVersion ?? savedReport?.version,
      statusCode: savedReport?.apiStatus ?? first.statusCode,
      agendaId: item.id,
      template: savedReport?.template ?? first.template,
      date: item.date,
      time: item.time,
      hospital: item.hospital,
      dept: item.dept,
      contact: item.contact,
      place: item.place,
      title: item.title,
      transcript: draft.transcript,
      attachments: draft.attachments,
      dealSections: draft.salesDealIds.map(sectionPayloadFor),
      commonBody: draft.meetingResult?.shared?.common_report?.body,
      unassignedBody: draft.meetingResult?.shared?.unassigned_report?.body,
    }
  }

  const generatable =
    draft.salesDealIds.length > 0 &&
    draft.salesDealIds.every(
      (id) =>
        canEditDeal(id) &&
        ['draft', 'changes_requested'].includes(draft.draftsByDeal[id]?.statusCode),
    )
  const result = draft.meetingResult
  const editableDealIds = draft.salesDealIds.filter(
    (id) =>
      canEditDeal(id) &&
      ['draft', 'changes_requested'].includes(draft.draftsByDeal[id]?.statusCode),
  )
  const emptyDealIds = editableDealIds.filter((id) => draft.draftsByDeal[id]?.phase === 'idle')
  const brokenDealIds = editableDealIds.filter(
    (id) => (draft.draftsByDeal[id]?.sectionIssues.length ?? 0) > 0,
  )
  const hasDraftContent = hasMeetingDraftContent(
    draft.salesDealIds,
    draft.draftsByDeal,
    result?.shared,
  )

  const generateAll = async () => {
    if (busy || generationAbort.current || !generatable || !draft.canGenerate) return
    recoveryAbort.current?.abort()
    const targets = [...draft.salesDealIds]
    const payload = payloadForMeeting()
    const attempt = idempotencyAttemptFor(generationAttempt.current, payload)
    generationAttempt.current = attempt
    const controller = new AbortController()
    generationAbort.current = controller
    setGenerating(true)
    beginGeneration(targets)
    setRunError(null)
    setRunErrors({})
    try {
      const created = await createReportGeneration<MeetingProcessingOutput>(
        meetingGenerationRequestOf(payload, attempt.key),
      )
      const run = await waitForMeetingProcessing(
        created,
        (progress) => {
          receiveProgress({
            ...progress,
            previews: progress.previews.filter(
              (preview) => preview.section !== 'deal' || targets.includes(preview.sales_deal_id!),
            ),
          })
        },
        controller.signal,
      )
      if (controller.signal.aborted) return
      acceptGenerated(run.id, run.output_snapshot)
      generationAttempt.current = finishIdempotencyAttempt(generationAttempt.current, attempt.key)
      setRunErrors(run.output_snapshot.errors)
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        if (isAgentRunTerminalError(reason)) {
          generationAttempt.current = finishIdempotencyAttempt(
            generationAttempt.current,
            attempt.key,
          )
        }
        generationFailed(targets, reason)
        setRunError(errorMessage(reason, '미팅 처리를 완료하지 못했습니다.'))
      }
    } finally {
      if (generationAbort.current === controller) {
        generationAbort.current = null
        setGenerating(false)
      }
    }
  }

  const requestGeneration = () => {
    if (hasDraftContent) setConfirm({ kind: 'regenerate' })
    else void generateAll()
  }

  const submitAll = async () => {
    if (
      busy ||
      submitAbort.current ||
      editableDealIds.length !== draft.salesDealIds.length ||
      emptyDealIds.length > 0 ||
      brokenDealIds.length > 0
    )
      return

    const controller = new AbortController()
    submitAbort.current = controller
    setSubmitting(true)
    setRunError(null)

    try {
      const report = await finalizeReport(payloadForMeeting(), result?.runId, controller.signal)
      if (controller.signal.aborted || submitAbort.current !== controller) return
      showToast('업무보고를 확정했습니다.')
      navigate(meetingReportPath(report.id), { replace: true })
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        setRunError(errorMessage(reason, '업무보고를 확정하지 못했습니다.'))
      }
    } finally {
      if (submitAbort.current === controller) {
        submitAbort.current = null
        setSubmitting(false)
      }
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
          <Link to={meetingReportPath(savedReport?.id ?? '')}>확인 완료 보고서 열기</Link>
        </p>
      )}

      {(runError || saveError) && (
        <p className={styles.mutationError} role="alert">
          {runError ?? saveError}
        </p>
      )}
      {Object.keys(runErrors).length > 0 && (
        <div className={styles.mutationError} role="alert">
          <p>일부 처리가 완료되지 않았습니다. 기존 작성 내용은 유지됩니다.</p>
          <ul>
            {Object.entries(runErrors).map(([step, message]) => (
              <li key={step}>{message}</li>
            ))}
          </ul>
        </div>
      )}

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
              disabled={busy || !canEdit}
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
              canGenerate={draft.canGenerate && generatable}
              generating={generating}
              contentLabel="미팅 내용"
              generateLabel="미팅 전체 분석·보고서 작성"
              disabled={busy || !canEdit}
              onGenerate={requestGeneration}
            />
            {draft.salesDealIds.length > 0 && !generatable && (
              <p className={styles.generationNote}>
                선택한 딜 중 읽기 전용 또는 수정중 상태가 아닌 보고서가 있어 미팅 전체를 다시 생성할
                수 없습니다.
              </p>
            )}
            <p className={styles.generationNote}>
              한 번 실행하면 선택한 모든 딜을 함께 처리합니다. 작성한 내용이 있으면 새 후보로 바꾸기
              전에 확인합니다.
            </p>
          </div>
        </div>

        <section className={styles.work} aria-label="딜별 미팅보고서">
          {draft.salesDealIds.length > 0 && (
            <div className={styles.saveBar} aria-busy={submitting}>
              <div className={styles.saveCopy}>
                <strong>미팅 보고서</strong>
                <p>공통 기록과 딜 {draft.salesDealIds.length}건을 한 문서로 저장합니다.</p>
              </div>
              <Button
                type="button"
                className={styles.saveAllButton}
                aria-label="업무보고 확정"
                disabled={
                  busy ||
                  editableDealIds.length !== draft.salesDealIds.length ||
                  emptyDealIds.length > 0 ||
                  brokenDealIds.length > 0
                }
                onClick={() => void submitAll()}
              >
                {submitting ? '확정 중…' : '업무보고 확정'}
              </Button>
            </div>
          )}
          {(result || draft.processingProgress) && (
            <MeetingSharedPanel
              shared={result?.shared ?? null}
              progress={draft.processingProgress}
              disabled={busy}
              onChange={canEdit ? draft.setShared : undefined}
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
                  generating={generating || recovering}
                  canGenerate={draft.canGenerate && generatable}
                  readOnly={!canEditDeal(dealId)}
                  onTitleChange={(value) => draft.setTitle(dealId, value)}
                  onChange={(values, missing) => draft.applyDocument(dealId, values, missing)}
                  onRestoreSections={() => draft.restoreSections(dealId)}
                  onStartManual={() => draft.startManual(dealId)}
                  onGenerate={requestGeneration}
                />
              )
            })
          )}
        </section>
      </div>

      {pendingRecovery && (
        <Modal
          title="이전에 생성하던 후보를 복구할까요?"
          description="복구하면 당시 원문·첨부·선택 딜과 생성 결과가 현재 편집 내용 위에 올라옵니다."
          onClose={() => setPendingRecovery(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setPendingRecovery(null)}>
                현재 내용 유지
              </Button>
              <Button
                type="button"
                onClick={() => {
                  const run = pendingRecovery
                  setPendingRecovery(null)
                  const controller = new AbortController()
                  recoveryAbort.current = controller
                  setRecovering(true)
                  void resumeGeneration(run, controller)
                }}
              >
                후보 복구
              </Button>
            </>
          }
        >
          <p>현재 보고서 내용은 사용자가 복구를 선택하기 전까지 바뀌지 않습니다.</p>
        </Modal>
      )}

      {confirm?.kind === 'regenerate' && (
        <Modal
          title="미팅 보고서를 다시 생성할까요?"
          description="계속하면 공통 내용과 모든 딜 본문·제목이 새 후보로 바뀝니다."
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
                  void generateAll()
                }}
              >
                다시 생성
              </Button>
            </>
          }
        >
          <p>현재 편집 중인 내용은 아직 업무보고서로 저장되지 않았습니다.</p>
        </Modal>
      )}
    </section>
  )
}

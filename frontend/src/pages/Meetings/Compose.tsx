// 업무 보고서 작성 화면.
//
// 왼쪽은 미팅 공통 정보·원문이고, 오른쪽은 공통 기록과 선택한 딜의 보고서입니다.
// 저장할 때는 공통 기록과 선택된 딜 카드를 미팅 보고서 한 건으로 묶습니다.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { isAxiosError } from 'axios'

import { useCurrentUser } from '@/auth/sessionContext'
import { errorMessage, reportGenerationMessage } from '@/api/errorMessage'
import {
  createReportGeneration,
  finishIdempotencyAttempt,
  idempotencyAttemptFor,
  isAgentRunTerminalError,
  latestMeetingProcessing,
  waitForMeetingProcessing,
} from '@/api/reportAgent'
import Button, { buttonClass } from '@/components/Button'
import { ChevronLeftIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { SkeletonDetail } from '@/components/Skeleton'
import { meetingPickPath, meetingReportPath, ROUTES } from '@/constants/routes'
import { isOwnAgendaItem, useAgendaItem } from '@/shared/agenda'
import { isAuthorEditableReportStatus } from '@/shared/reports'
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
import useMeetingDraft, { hasMeetingDraftContent, isMeetingBodyBlank } from './useMeetingDraft'
import useMeetingReports, {
  type MeetingDealDraftPayload,
  type MeetingDraftPayload,
  canRecoverMeetingGeneration,
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
    !input.transcript
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
  const agendaId = params.get('agenda') ?? ''
  useEffect(() => {
    setGenerating(false)
    setRecovering(true)
    setSubmitting(false)
    setRunError(null)
    setRunErrors({})
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
          generationFailed(dealIds, reason)
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
    recoveredAgendaId.current = agendaId
    const controller = new AbortController()
    recoveryAbort.current = controller
    setRecovering(true)
    void latestMeetingProcessing(agendaId, controller.signal)
      .then((run) => {
        if (controller.signal.aborted || generationAbort.current) return
        meetingInputOf(run, agendaId)
        if (!canRecoverMeetingGeneration(run, savedReport, memberId)) return
        return resumeGeneration(run, controller)
      })
      .catch((reason: unknown) => {
        const missingInput =
          reason instanceof Error && reason.message === 'report_generation_input_missing'
        if (
          !controller.signal.aborted &&
          !missingInput &&
          (!isAxiosError(reason) || reason.response?.status !== 404)
        ) {
          setRunError(errorMessage(reason, '진행 중인 보고서 상태를 확인하지 못했습니다.'))
        }
      })
      .finally(() => {
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
        isAuthorEditableReportStatus(savedReport.apiStatus)))
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
    return {
      reportId: savedReport?.id,
      version: savedReport?.version,
      statusCode: savedReport?.apiStatus,
      agendaId: item.id,
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
    canEdit &&
    draft.salesDealIds.every(
      (id) => canEditDeal(id) && isAuthorEditableReportStatus(draft.draftsByDeal[id]?.statusCode),
    )
  const result = draft.meetingResult
  const editableDealIds = draft.salesDealIds.filter(
    (id) => canEditDeal(id) && isAuthorEditableReportStatus(draft.draftsByDeal[id]?.statusCode),
  )
  const emptyDealIds = editableDealIds.filter((id) =>
    isMeetingBodyBlank(draft.draftsByDeal[id]?.values ?? {}),
  )
  const hasSharedBody = Boolean(
    result?.shared?.common_report?.body.trim() || result?.shared?.unassigned_report?.body.trim(),
  )
  const missingBody = emptyDealIds.length > 0 || (draft.salesDealIds.length === 0 && !hasSharedBody)
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
      !canEdit ||
      editableDealIds.length !== draft.salesDealIds.length ||
      missingBody
    )
      return

    const controller = new AbortController()
    submitAbort.current = controller
    setSubmitting(true)
    setRunError(null)

    try {
      const report = await finalizeReport(payloadForMeeting(), result?.runId, controller.signal)
      if (controller.signal.aborted || submitAbort.current !== controller) return
      showToast('업무보고 작성을 완료했습니다.')
      navigate(meetingReportPath(report.id), { replace: true })
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        setRunError(errorMessage(reason, '업무보고 작성을 완료하지 못했습니다.'))
      }
    } finally {
      if (submitAbort.current === controller) {
        submitAbort.current = null
        setSubmitting(false)
      }
    }
  }

  const printable =
    hasSharedBody ||
    draft.salesDealIds.some((dealId) => draft.draftsByDeal[dealId]?.phase === 'ready')

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
              <li key={step}>{reportGenerationMessage(message)}</li>
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
              generating={generating || recovering}
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
              미팅 공통 기록을 만들며, 관련 딜을 선택하면 딜별 보고서도 함께 처리합니다. 작성한
              내용이 있으면 새 후보로 바꾸기 전에 확인합니다.
            </p>
          </div>
        </div>

        <section className={styles.work} aria-label="미팅 보고서">
          <div className={styles.saveBar} aria-busy={submitting}>
            <div className={styles.saveCopy}>
              <strong>미팅 보고서</strong>
              <p>
                {draft.salesDealIds.length > 0
                  ? `공통 기록과 딜 ${draft.salesDealIds.length}건을 한 문서로 저장합니다.`
                  : '딜 미지정 미팅 기록을 한 문서로 저장합니다.'}
              </p>
            </div>
            <Button
              type="button"
              className={styles.saveAllButton}
              aria-label="업무보고 작성 완료"
              disabled={
                busy ||
                !canEdit ||
                editableDealIds.length !== draft.salesDealIds.length ||
                missingBody
              }
              onClick={() => void submitAll()}
            >
              {submitting ? '완료 중…' : '업무보고 작성 완료'}
            </Button>
          </div>
          {(draft.salesDealIds.length === 0 ||
            result ||
            draft.processingProgress ||
            generating) && (
            <MeetingSharedPanel
              shared={result?.shared ?? null}
              progress={draft.processingProgress}
              generating={generating || recovering}
              disabled={busy}
              showCommon={draft.salesDealIds.length === 0}
              onChange={canEdit ? draft.setShared : undefined}
            />
          )}
          {draft.salesDealIds.length > 0 &&
            draft.salesDealIds.map((dealId) => {
              const state = draft.draftsByDeal[dealId]
              if (!state) return null
              const deal = deals.deals.find((one) => one.id === dealId)
              const savedSection = savedByDeal.get(dealId)
              const product = deal?.product ?? savedSection?.product

              return (
                <DealReportCard
                  key={dealId}
                  dealId={dealId}
                  deal={deal}
                  savedDeal={savedSection?.salesDeal}
                  draft={state}
                  progress={draft.processingProgress}
                  when={`${when}${product ? ` · ${product}` : ''}`}
                  saving={pending}
                  generating={generating || recovering}
                  canGenerate={draft.canGenerate && generatable}
                  readOnly={!canEditDeal(dealId)}
                  onTitleChange={(value) => draft.setTitle(dealId, value)}
                  onChange={(body) => draft.applyDocument(dealId, body)}
                  onStartManual={() => draft.startManual(dealId)}
                  onGenerate={requestGeneration}
                />
              )
            })}
        </section>
      </div>

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

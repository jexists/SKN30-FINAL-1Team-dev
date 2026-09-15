// 미팅 보고서 작성 화면.
//
// 왼쪽은 미팅 공통 정보·원문이고, 오른쪽은 공통 기록과 선택한 딜의 보고서입니다.
// 저장할 때는 공통 기록과 선택된 딜 카드를 미팅 보고서 한 건으로 묶습니다.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { isAxiosError, isCancel } from 'axios'

import { useCurrentUser } from '@/auth/sessionContext'
import useCompanyDeals from '@/hooks/useCompanyDeals'
import { errorMessage, meetingRunErrorMessage, reportGenerationMessage } from '@/api/errorMessage'
import {
  createReportGeneration,
  finishIdempotencyAttempt,
  idempotencyAttemptFor,
  isAgentRunTerminalError,
  latestMeetingProcessing,
  retryMeetingReport,
  sameReportGenerationInput,
  waitForMeetingAnalysis,
  waitForMeetingProcessing,
} from '@/api/reportAgent'
import Button from '@/components/Button'
import ColumnHead from '@/components/ColumnHead'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  RefreshIcon,
  StopIcon,
} from '@/components/icons'
import Modal from '@/components/Modal'
import RecordDrawer from '@/pages/Dashboard/components/RecordDrawer'
import ReportReviewWarning from '@/components/ReportReviewWarning'
import { SkeletonDetail } from '@/components/Skeleton'
import { meetingPickPath, meetingReportPath, ROUTES } from '@/constants/routes'
import { isOwnAgendaItem, useAgendaItem } from '@/shared/agenda'
import { isAuthorEditableReportStatus, reportInputError } from '@/shared/reports'
import { showToast } from '@/shared/toast'
import useAgentRunCancellation from '@/shared/useAgentRunCancellation'
import type { IdempotencyAttempt } from '@/api/reportAgent'
import type {
  AgentRunResponse,
  MeetingDealRef,
  MeetingProcessingOutput,
  ReportGenerationInput,
} from '@/types'
import { attachmentPayloadsOf, meetingAttachmentPurposeOf } from '@/utils/attachment'
import { fmtDot, parseISO } from '@/utils/date'

import DealReportCard from './components/DealReportCard'
import MeetingInfoPanel from './components/MeetingInfoPanel'
import MeetingDealForm from './components/MeetingDealForm'
import MeetingInputPanel from './components/MeetingInputPanel'
import MeetingSharedPanel from './components/MeetingSharedPanel'
import GenerationProgress from './components/GenerationProgress'
import useStickToBottom from './components/GenerationProgress/useStickToBottom'
import useMeetingDraft, { hasMeetingDraftContent, isMeetingBodyBlank } from './useMeetingDraft'
import useMeetingReports, {
  type MeetingDealDraftPayload,
  type MeetingDraftPayload,
  canRecoverMeetingGeneration,
  meetingGenerationRequestOf,
  meetingRequestOf,
  useMeetingReportOfAgenda,
} from './useMeetingReports'

import styles from './Compose.module.scss'

type Confirm = { kind: 'regenerate' } | { kind: 'deselect'; dealId: string } | null

function meetingInputOf(
  run: AgentRunResponse<MeetingProcessingOutput>,
  agendaId: string,
): ReportGenerationInput {
  const input = run.generation_input
  const hasSource = input?.attachments.some(
    (attachment) =>
      meetingAttachmentPurposeOf(attachment) === 'meeting_source' && attachment.extract.trim(),
  )
  if (
    !input ||
    input.report_kind !== 'meeting' ||
    input.source_activity_id !== agendaId ||
    (!input.transcript?.trim() && !hasSource)
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
  const analysisAbort = useRef<AbortController | null>(null)
  const submitAbort = useRef<AbortController | null>(null)
  const recoveredAgendaId = useRef('')
  const [generating, setGenerating] = useState(false)
  const [recovering, setRecovering] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [runErrors, setRunErrors] = useState<Record<string, string>>({})
  // 저장 전에 페이지를 다시 연 경우. 마지막 실행 결과를 되살렸다는 안내입니다.
  const [restored, setRestored] = useState(false)
  // 등록 단계에서는 왼쪽 한 열만 씁니다. 작성을 시작해야 보고서 열이 열립니다.
  const [opened, setOpened] = useState(false)
  const [generationEvidence, setGenerationEvidence] = useState<Record<string, unknown> | null>(null)
  const [activeRunId, setActiveRunId] = useState<string>()
  const [cancelledNotice, setCancelledNotice] = useState(false)
  const agendaId = params.get('agenda') ?? ''
  useEffect(() => {
    setGenerating(false)
    setRecovering(true)
    setSubmitting(false)
    setRunError(null)
    setRunErrors({})
    setRestored(false)
    setOpened(false)
    setGenerationEvidence(null)
    setActiveRunId(undefined)
    setCancelledNotice(false)
    recoveredAgendaId.current = ''
    generationAttempt.current = undefined
    return () => {
      generationAbort.current?.abort()
      generationAbort.current = null
      recoveryAbort.current?.abort()
      recoveryAbort.current = null
      analysisAbort.current?.abort()
      analysisAbort.current = null
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
  const stopAnalysisWatch = useCallback(() => {
    analysisAbort.current?.abort()
    analysisAbort.current = null
  }, [])
  const draft = useMeetingDraft(item, savedReport, draftReady, stopAnalysisWatch)
  const {
    beginGeneration,
    receiveProgress,
    acceptGenerated,
    acceptAnalysis,
    generationFailed,
    restoreConfirmed,
    restoreGenerationInput,
  } = draft
  const onGenerationCancelled = useCallback(() => {
    stopAnalysisWatch()
    generationAbort.current?.abort()
    recoveryAbort.current?.abort()
    recoveryAbort.current = null
    setRecovering(false)
    generationAbort.current = null
    setActiveRunId(undefined)
    setGenerating(false)
    setCancelledNotice(true)
    restoreConfirmed(draft.salesDealIds)
  }, [draft.salesDealIds, restoreConfirmed, stopAnalysisWatch])
  const cancellation = useAgentRunCancellation(
    activeRunId,
    () => {
      generationAbort.current?.abort()
      recoveryAbort.current?.abort()
    },
    onGenerationCancelled,
  )
  useEffect(() => {
    setGenerationEvidence(savedReport?.aiEvidence ?? null)
  }, [savedReport])
  const startAnalysisWatchForParent = useCallback(
    (parentRunId: string) => {
      stopAnalysisWatch()
      const controller = new AbortController()
      analysisAbort.current = controller
      void waitForMeetingAnalysis(parentRunId, acceptAnalysis, controller.signal)
        .catch(() => undefined)
        .finally(() => {
          if (analysisAbort.current === controller) analysisAbort.current = null
        })
    },
    [acceptAnalysis, stopAnalysisWatch],
  )
  const startAnalysisWatch = useCallback(
    (run: AgentRunResponse<MeetingProcessingOutput>) => {
      if (!run.child_runs?.some((child) => child.agent_code === 'meeting_analysis')) return
      const parentRunId =
        typeof run.source_refs.parent_run_id === 'string'
          ? run.source_refs.parent_run_id
          : run.agent_code === 'meeting_processing'
            ? run.id
            : undefined
      if (parentRunId) startAnalysisWatchForParent(parentRunId)
    },
    [startAnalysisWatchForParent],
  )

  const resumeGeneration = useCallback(
    async (run: AgentRunResponse<MeetingProcessingOutput>, controller: AbortController) => {
      let dealIds: string[] = []
      try {
        const input = meetingInputOf(run, agendaId)
        dealIds = input.sales_deal_ids
        restoreGenerationInput(input)
        beginGeneration(dealIds)
        if (run.status_code === 'queued' || run.status_code === 'running') {
          setActiveRunId(
            typeof run.source_refs.parent_run_id === 'string'
              ? run.source_refs.parent_run_id
              : run.id,
          )
        }
        setOpened(true)
        if (run.status_code === 'failed' || run.status_code === 'cancelled') {
          throw new Error(run.error_code ?? run.error_message ?? 'agent_run_failed')
        }
        const completed = await waitForMeetingProcessing(
          run,
          (progress) => {
            if (!controller.signal.aborted && recoveryAbort.current === controller) {
              receiveProgress({
                ...progress,
                previews: progress.previews.filter(
                  (preview) =>
                    preview.section !== 'deal' || dealIds.includes(preview.sales_deal_id!),
                ),
                confirmed_previews: progress.confirmed_previews?.filter(
                  (preview) =>
                    preview.section !== 'deal' || dealIds.includes(preview.sales_deal_id!),
                ),
              })
            }
          },
          controller.signal,
        )
        if (!completed.output_snapshot) throw new Error('agent_run_failed')
        if (controller.signal.aborted || recoveryAbort.current !== controller) return
        acceptGenerated(completed.id, completed.output_snapshot)
        setGenerationEvidence(completed.evidence)
        startAnalysisWatch(completed)
        // 지난 실행의 실패는 딜 카드가 따로 알립니다. 여기서는 되살렸다는 사실만 알립니다.
        setRestored(Boolean(completed.output_snapshot.reports))
      } catch (reason: unknown) {
        if (!controller.signal.aborted && recoveryAbort.current === controller) {
          const parentRunId =
            typeof run.source_refs.parent_run_id === 'string'
              ? run.source_refs.parent_run_id
              : run.agent_code === 'meeting_processing'
                ? run.id
                : undefined
          if (parentRunId) startAnalysisWatchForParent(parentRunId)
          generationFailed(dealIds, reason)
          setRunError(
            errorMessage(reason, 'AI 보고서 작성을 완료하지 못했습니다. 다시 시도해 주세요.'),
          )
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
      startAnalysisWatch,
      startAnalysisWatchForParent,
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
          setRunError(
            errorMessage(reason, 'AI 보고서 작성을 완료하지 못했습니다. 다시 시도해 주세요.'),
          )
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
  const [createDealOpen, setCreateDealOpen] = useState(false)
  const createDealKey = useRef('')
  const [confirm, setConfirm] = useState<Confirm>(null)
  // 일정 상세는 대시보드·캘린더가 쓰는 드로어를 그대로 엽니다. AI 브리핑까지 그 안에 있습니다.
  const [detailOpen, setDetailOpen] = useState(false)
  // 보고서를 읽을 때는 왼쪽 입력부를 통째로 접어 본문에 폭을 넘깁니다. 기억하지는 않습니다.
  const [sideCollapsed, setSideCollapsed] = useState(false)
  useEffect(() => {
    setCreateDealOpen(false)
    createDealKey.current = ''
    setDetailOpen(false)
    setConfirm(null)
  }, [agendaId, item?.customerCompanyId])

  const streaming = generating || recovering
  // 글이 자라는 동안 스크롤 상자가 바닥을 따라갑니다. 표식은 .reports 의 마지막 자식입니다.
  // 아래 이른 반환보다 앞에 서야 합니다 — 훅은 렌더마다 같은 순서로 불려야 합니다.
  const streamEnd = useStickToBottom(streaming)

  if (agendaLoading || loading) {
    return (
      <section>
        <SkeletonDetail label="미팅 보고서를 불러오는 중입니다." title height={520} />
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
        <h1 className="sr-only">미팅 보고서 작성</h1>
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
  const busy = pending || generating || recovering || submitting || createDealOpen
  const meetingDate = savedReport?.date ?? draft.reportDate ?? item.date
  const meetingTime = savedReport?.time ?? item.time

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
      date: meetingDate,
      time: meetingTime,
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
  // 보고서 열을 여는 조건. 작성을 시작했거나, 이미 결과·저장본이 있는 미팅입니다.
  const showWork =
    opened || generating || Boolean(result) || Boolean(savedReport) || hasDraftContent
  const generationInputError = reportInputError(meetingGenerationRequestOf(payloadForMeeting(), ''))
  const submitInputError = reportInputError({
    ...meetingRequestOf(payloadForMeeting()),
    attachments: attachmentPayloadsOf(draft.attachments),
  })

  // 선택을 풀면 그 딜의 보고서가 화면에서 빠집니다. 내용이 있을 때만 한 번 묻습니다.
  const toggleDeal = (dealId: string) => {
    const state = draft.draftsByDeal[dealId]
    const losesContent =
      draft.salesDealIds.includes(dealId) &&
      (state?.reportId !== undefined ||
        state?.touched === true ||
        !isMeetingBodyBlank(state?.values ?? {}))
    if (losesContent) setConfirm({ kind: 'deselect', dealId })
    else draft.toggleSalesDeal(dealId)
  }

  const generateAll = async (forceFresh = false) => {
    if (
      busy ||
      draft.attachmentsPending ||
      generationAbort.current ||
      !generatable ||
      generationInputError ||
      !draft.canGenerate
    )
      return
    recoveryAbort.current?.abort()
    const targets = [...draft.salesDealIds]
    const payload = payloadForMeeting()
    draft.setReportDate(payload.date)
    const attempt = idempotencyAttemptFor(
      forceFresh ? undefined : generationAttempt.current,
      payload,
    )
    generationAttempt.current = attempt
    const controller = new AbortController()
    generationAbort.current = controller
    setActiveRunId(undefined)
    setCancelledNotice(false)
    stopAnalysisWatch()
    setGenerating(true)
    beginGeneration(targets)
    // 새 초안에는 새 검토가 붙습니다. 직전 실행의 근거를 이 초안의 것으로 보여 주지 않습니다.
    setGenerationEvidence(null)
    setRunError(null)
    setRunErrors({})
    setRestored(false)
    let analysisParentRunId: string | undefined
    try {
      const request = meetingGenerationRequestOf(payload, attempt.key)
      let created: AgentRunResponse<MeetingProcessingOutput>
      let previous: AgentRunResponse<MeetingProcessingOutput> | null = null
      try {
        previous = await latestMeetingProcessing(agendaId, controller.signal)
      } catch (reason: unknown) {
        if (
          controller.signal.aborted ||
          isCancel(reason) ||
          !isAxiosError(reason) ||
          (reason.response && reason.response.status < 500 && reason.response.status !== 404)
        ) {
          throw reason
        }
      }
      const failedReportId =
        !forceFresh && previous && sameReportGenerationInput(previous.generation_input, request)
          ? ([...(previous.child_runs ?? [])]
              .reverse()
              .find(
                (child) =>
                  child.agent_code === 'meeting_report_writing' &&
                  (child.status_code === 'failed' || child.status_code === 'partial'),
              )?.id ?? null)
          : null
      created = failedReportId
        ? await retryMeetingReport<MeetingProcessingOutput>(failedReportId)
        : await createReportGeneration<MeetingProcessingOutput>(request)
      if (controller.signal.aborted || generationAbort.current !== controller) return
      setActiveRunId(
        typeof created.source_refs.parent_run_id === 'string'
          ? created.source_refs.parent_run_id
          : created.id,
      )
      analysisParentRunId =
        typeof created.source_refs.parent_run_id === 'string'
          ? created.source_refs.parent_run_id
          : created.agent_code === 'meeting_processing'
            ? created.id
            : undefined
      const run = await waitForMeetingProcessing(
        created,
        (progress) => {
          if (controller.signal.aborted || generationAbort.current !== controller) return
          receiveProgress({
            ...progress,
            previews: progress.previews.filter(
              (preview) => preview.section !== 'deal' || targets.includes(preview.sales_deal_id!),
            ),
            confirmed_previews: progress.confirmed_previews?.filter(
              (preview) => preview.section !== 'deal' || targets.includes(preview.sales_deal_id!),
            ),
          })
        },
        controller.signal,
      )
      if (controller.signal.aborted || generationAbort.current !== controller) return
      acceptGenerated(run.id, run.output_snapshot)
      setActiveRunId(undefined)
      setGenerationEvidence(run.evidence)
      startAnalysisWatch(run)
      generationAttempt.current = finishIdempotencyAttempt(generationAttempt.current, attempt.key)
      setRunErrors(run.output_snapshot.errors)
    } catch (reason: unknown) {
      if (!controller.signal.aborted && generationAbort.current === controller) {
        if (analysisParentRunId) startAnalysisWatchForParent(analysisParentRunId)
        if (isAgentRunTerminalError(reason)) {
          generationAttempt.current = finishIdempotencyAttempt(
            generationAttempt.current,
            attempt.key,
          )
        }
        generationFailed(targets, reason)
        setRunError(
          errorMessage(reason, 'AI 보고서 작성을 완료하지 못했습니다. 다시 시도해 주세요.'),
        )
      }
    } finally {
      if (generationAbort.current === controller) {
        generationAbort.current = null
        setGenerating(false)
      }
    }
  }

  const requestGeneration = () => {
    setOpened(true)
    if (hasDraftContent) setConfirm({ kind: 'regenerate' })
    else void generateAll()
  }

  const submitAll = async () => {
    if (
      busy ||
      draft.attachmentsPending ||
      submitAbort.current ||
      !canEdit ||
      editableDealIds.length !== draft.salesDealIds.length ||
      submitInputError ||
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
      showToast('미팅 보고서 작성을 완료했습니다.')
      navigate(meetingReportPath(report.id), { replace: true })
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        setRunError(errorMessage(reason, '미팅 보고서 작성을 완료하지 못했습니다.'))
      }
    } finally {
      if (submitAbort.current === controller) {
        submitAbort.current = null
        setSubmitting(false)
      }
    }
  }

  /*
   * 생성 중에는 빈 상자를 미리 세우지 않습니다. 제 내용이 도착한 상자만 나타나고,
   * 상자가 차례로 생겨나는 것 자체가 진행 표시입니다 — 그래서 상자 안마다 같은
   * 진행 문구를 또 둘 이유가 없습니다.
   */
  const previewOf = (section: string, dealId?: string) =>
    draft.processingProgress?.previews.some(
      (preview) =>
        (dealId ? preview.section === 'deal' : preview.section === section) &&
        (dealId ? preview.sales_deal_id === dealId : true),
    ) ?? false
  const sharedArrived = previewOf('common') || previewOf('unassigned')
  /*
   * 지금 서버가 손대고 있는 자리. 위에서 글이 제자리로 바뀌는 동안 아래 줄이 '어디인지'를
   * 말해 줍니다. 진행 데이터에 대상 이름은 없고, 흐르는 중인 preview 가 유일한 신호입니다.
   */
  const liveTarget = (draft.processingProgress?.previews ?? [])
    .filter((preview) => preview.preview_state === 'streaming')
    .map((preview) => {
      if (preview.section === 'common') return '미팅 공통 기록'
      if (preview.section === 'unassigned') return '딜 미지정 기록'
      const deal = deals.deals.find((one) => one.id === preview.sales_deal_id)
      // 카드와 같은 이름을 씁니다(DealReportCard.tsx). 위아래가 다른 이름을 부르면 못 잇습니다.
      return deal ? deal.title.trim() || deal.product : null
    })
    .filter(Boolean)
    .join(' · ')
  // ML 판정은 딜마다 돌지만 알릴 것은 하나입니다. 카드마다 띄우지 않고 전체 로그에 한 줄.
  const analysing = draft.salesDealIds.filter(
    (dealId) => draft.draftsByDeal[dealId]?.analysisPhase === 'running',
  ).length
  const analysisRows = analysing
    ? [
        {
          key: 'ml',
          label: '성사 가능성 분석 중',
          state: 'running' as const,
          detail: draft.salesDealIds.length > 1 ? `딜 ${analysing}개` : undefined,
        },
      ]
    : []

  // 검토·수정 단계가 남긴 말만 검토 메모로 보냅니다. 자료 정리·근거 분류는
  // 사람이 확인할 것이 아니라 진행 상황이므로 활동 줄에 남습니다.
  const reviewNotes = (draft.processingProgress?.stage_results ?? [])
    .filter((item) => item.stage === 'review_initial' || item.stage === 'repair')
    .map((item) => item.body)
  // 고쳐 쓴 본문이 실제로 흐르기 시작하면 메모는 읽고 난 것입니다. 그때 위로 올립니다.
  // 검토가 끝난 시점은 아직 이릅니다 — 올려 두고 한참 기다리게 됩니다. 판(draft_version) 2 는
  // 수정 단계 본문에만 붙고, 병합이 되돌리지 않으므로 한 번 참이면 끝까지 참입니다.
  const revising = (draft.processingProgress?.previews ?? []).some(
    (item) => (item.draft_version ?? 1) >= 2,
  )
  const liveMemo = streaming ? (
    <ReportReviewWarning evidence={generationEvidence} generating notes={reviewNotes} />
  ) : null

  const printable =
    hasSharedBody ||
    draft.salesDealIds.some((dealId) => draft.draftsByDeal[dealId]?.phase === 'ready')

  return (
    <section className={styles.page}>
      <h1 className="sr-only">
        {item.hospital} {item.title} 미팅 보고서 작성
      </h1>

      {/* 어느 미팅을 쓰는 중인지 화면 맨 위에서 바로 읽힙니다. 일시는 제목 아래 한 줄로 붙습니다. */}
      <div className={styles.head}>
        <div className={styles.heading}>
          <Link className={styles.back} to={meetingPickPath(item.date)}>
            <ChevronLeftIcon width={15} height={15} />
            미팅 리스트
          </Link>
          <div className={styles.headingMain}>
            <div className={styles.headingText}>
              <h1 className={styles.title}>
                {item.hospital || '회사 미지정'}
                {item.title && <span> · {item.title}</span>}
              </h1>
              <p className={styles.meta}>
                {fmtDot(parseISO(meetingDate))} {meetingTime}
                {item.contact ? ` · ${item.contact}` : ''}
              </p>
            </div>
            <div className={styles.headActions}>
              {/* 작성 시작 지점입니다. 이미 본문이 있으면 같은 버튼이 다시 생성으로 바뀝니다. */}
              <Button
                type="button"
                variant={hasDraftContent ? 'outline' : 'primary'}
                className={styles.generate}
                aria-busy={generating || recovering}
                onClick={requestGeneration}
                disabled={
                  busy ||
                  !canEdit ||
                  !draft.canGenerate ||
                  Boolean(generationInputError) ||
                  !generatable ||
                  generating ||
                  recovering
                }
              >
                {generating || recovering ? (
                  'AI 보고서 작성 중…'
                ) : hasDraftContent ? (
                  <>
                    <RefreshIcon width={16} height={16} />
                    AI 보고서 다시 생성
                  </>
                ) : (
                  'AI 보고서 작성'
                )}
              </Button>
              {(generating || recovering) && activeRunId && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={cancellation.cancelling}
                  onClick={() => void cancellation.cancel()}
                >
                  <StopIcon />
                  {cancellation.cancelling ? '중단 중…' : '생성 중단'}
                </Button>
              )}
              {cancellation.cancelError && (
                <p className={styles.mutationError} role="alert">
                  {cancellation.cancelError}
                </p>
              )}
              {cancelledNotice && <p role="status">생성이 중단되었습니다.</p>}
            </div>
          </div>
        </div>

        <div className={styles.headNotice}>
          {restored && !runError && (
            <p className={styles.headNote}>
              자동 임시 저장된 내용입니다. 미팅 보고서 작성 완료를 눌러야 저장됩니다.
            </p>
          )}
          {(submitInputError || runError || saveError) && (
            <p className={styles.mutationError} role="alert">
              {submitInputError
                ? reportGenerationMessage(submitInputError)
                : (runError ?? saveError)}
            </p>
          )}
          {Object.keys(runErrors).length > 0 && (
            <div className={styles.mutationError} role="alert">
              <ul>
                {Object.entries(runErrors).map(([step, message]) => (
                  <li key={step}>{meetingRunErrorMessage(step, message)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {lockedDealIds.length > 0 && (
        <p className={styles.locked}>
          팀장 확인이 끝난 딜 보고서 {lockedDealIds.length}건은 수정할 수 없습니다.{' '}
          <Link to={meetingReportPath(savedReport?.id ?? '')}>확인 완료 보고서 열기</Link>
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
          <ColumnHead title={!sideCollapsed && '보고서 작성 자료'} bare={sideCollapsed}>
            {showWork && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                iconOnly
                className={styles.sideToggle}
                aria-expanded={!sideCollapsed}
                aria-controls="compose-side"
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
          </ColumnHead>
          <div
            id="compose-side"
            className={
              sideCollapsed ? `${styles.sideContent} ${styles.collapsed}` : styles.sideContent
            }
          >
            <aside className={styles.reference}>
              <MeetingInfoPanel
                item={{ ...item, date: meetingDate, time: meetingTime }}
                onOpenDetail={() => setDetailOpen(true)}
                deals={deals.deals}
                dealsLoading={deals.loading}
                dealsError={deals.error}
                onReloadDeals={deals.reload}
                selectedDealIds={draft.salesDealIds}
                onToggleDeal={toggleDeal}
                onCreateDeal={() => {
                  if (busy || !canEdit || !item.customerCompanyId || deals.loading) return
                  createDealKey.current = `${item.id}:${item.customerCompanyId}`
                  setCreateDealOpen(true)
                }}
                disabled={busy || !canEdit}
              />
            </aside>

            <div className={styles.input}>
              <MeetingInputPanel
                attachments={draft.attachments}
                onAttach={(files, purpose, acceptedKinds) =>
                  void draft.addAttachments(files, purpose, acceptedKinds)
                }
                onRemoveAttachment={draft.removeAttachment}
                onExtractChange={draft.setAttachmentExtract}
                attachmentError={
                  generationInputError
                    ? reportGenerationMessage(generationInputError)
                    : (draft.inputError ?? draft.attachmentError)
                }
                transcript={draft.transcript}
                onTranscriptChange={draft.setTranscript}
                disabled={busy || !canEdit}
              />
              {draft.salesDealIds.length > 0 && !generatable && (
                <p className={styles.generationNote}>
                  선택한 딜 중 읽기 전용 또는 수정중 상태가 아닌 보고서가 있어 미팅 전체를 다시
                  생성할 수 없습니다.
                </p>
              )}
            </div>
          </div>
        </div>

        {showWork && (
          <section className={styles.work} aria-label="미팅 보고서">
            {/* 왼쪽 열 머리와 같은 줄에 섭니다. 오른쪽 끝은 이 문서를 종이로 내보내는 자리입니다. */}
            <ColumnHead
              title={
                <>
                  보고서 작성
                  {/* 어디까지가 AI 가 쓴 것인지. 문서 안이 아니라 이 열의 머리에서 말합니다. */}
                  {draft.aiFilled && <span className={styles.aiBadge}>AI 작성</span>}
                </>
              }
            >
              <Button
                type="button"
                variant="outline"
                size="sm"
                className={styles.pdfButton}
                disabled={!printable || streaming}
                onClick={() => window.print()}
              >
                <DownloadIcon width={15} height={15} />
                PDF 다운로드
              </Button>
            </ColumnHead>
            {/* 끝난 뒤에 남는 한 줄. 생성 중에는 흐름 맨 아래에서 쌓입니다. */}
            <div className={styles.reviewMemo}>
              {!streaming && <ReportReviewWarning evidence={generationEvidence} />}
              {revising && liveMemo}
            </div>
            <div className={styles.reports}>
              {(streaming || analysing > 0) && (
                <GenerationProgress
                  feed="steps"
                  progress={draft.processingProgress}
                  extras={analysisRows}
                />
              )}
              {(streaming
                ? sharedArrived
                : draft.salesDealIds.length === 0 || result || draft.processingProgress) && (
                <MeetingSharedPanel
                  shared={result?.shared ?? null}
                  progress={draft.processingProgress}
                  generating={generating || recovering}
                  disabled={busy}
                  showCommon={draft.salesDealIds.length === 0}
                  commonDocKey={result?.commonDocKey}
                  unassignedDocKey={result?.unassignedDocKey}
                  onChange={canEdit ? draft.setShared : undefined}
                />
              )}
              {draft.salesDealIds.length > 0 &&
                draft.salesDealIds.map((dealId) => {
                  const state = draft.draftsByDeal[dealId]
                  if (!state) return null
                  // 아직 이 딜의 글이 오지 않았으면 상자를 세우지 않습니다. 생성이 끝나면
                  // 결과가 없는 딜도 이유를 보여야 하므로 전부 섭니다.
                  if (streaming && !previewOf('deal', dealId)) return null
                  const deal = deals.deals.find((one) => one.id === dealId)
                  const savedSection = savedByDeal.get(dealId)

                  return (
                    <DealReportCard
                      key={dealId}
                      dealId={dealId}
                      deal={deal}
                      savedDeal={savedSection?.salesDeal}
                      draft={state}
                      progress={draft.processingProgress}
                      saving={pending}
                      generating={generating || recovering}
                      canGenerate={
                        draft.canGenerate && generatable && !generationInputError && !createDealOpen
                      }
                      readOnly={!canEditDeal(dealId) || createDealOpen}
                      onTitleChange={(value) => draft.setTitle(dealId, value)}
                      onChange={(body) => draft.applyDocument(dealId, body)}
                      onStartManual={() => draft.startManual(dealId)}
                      onGenerate={requestGeneration}
                    />
                  )
                })}
              {/* 검토는 초안 다음에 일어납니다. 수정이 시작되면 이 상자는 위로 올라갑니다. */}
              {!revising && liveMemo}
              {/* 지금 하는 일은 늘 마지막 글입니다. 바닥까지 내려 읽어도 이 줄이 보입니다. */}
              {(streaming || analysing > 0) && (
                <GenerationProgress
                  feed="live"
                  progress={draft.processingProgress}
                  extras={analysisRows}
                  liveTarget={liveTarget}
                />
              )}
              {streaming && <div ref={streamEnd} className={styles.streamEnd} aria-hidden="true" />}
            </div>
            <div className={styles.saveBar} aria-busy={submitting || draft.attachmentsPending}>
              <div className={styles.saveActions}>
                <Button
                  type="button"
                  className={styles.saveAllButton}
                  aria-label="미팅 보고서 작성 완료"
                  disabled={
                    busy ||
                    draft.attachmentsPending ||
                    !canEdit ||
                    editableDealIds.length !== draft.salesDealIds.length ||
                    Boolean(submitInputError) ||
                    missingBody
                  }
                  onClick={() => void submitAll()}
                >
                  {submitting ? '완료 중…' : '미팅 보고서 작성 완료'}
                </Button>
              </div>
            </div>
          </section>
        )}
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
                  void generateAll(true)
                }}
              >
                다시 생성
              </Button>
            </>
          }
        >
          <p>현재 편집 중인 내용은 아직 미팅 보고서로 저장되지 않았습니다.</p>
        </Modal>
      )}
      {confirm?.kind === 'deselect' && (
        <Modal
          title="이 딜을 보고서에서 뺄까요?"
          description="선택을 풀면 이 딜의 보고서가 목록에서 사라집니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  const { dealId } = confirm
                  setConfirm(null)
                  draft.toggleSalesDeal(dealId)
                }}
              >
                해제
              </Button>
            </>
          }
        >
          <p>
            다시 선택하면 작성한 내용이 그대로 돌아옵니다. 뺀 채로 저장하면 이미 저장된 딜 보고서는
            삭제됩니다.
          </p>
        </Modal>
      )}
      {detailOpen && <RecordDrawer item={item} onClose={() => setDetailOpen(false)} />}
      {createDealOpen && item.customerCompanyId && (
        <MeetingDealForm
          activityKey={item.id}
          companyId={item.customerCompanyId}
          contactId={item.customerContactId}
          contactName={item.customerContactName}
          fallbackContactName={item.contact}
          onCreated={(created) => {
            const key = `${item.id}:${item.customerCompanyId}`
            if (
              createDealKey.current !== key ||
              item.id !== agendaId ||
              created.customerCompanyId !== item.customerCompanyId
            )
              return
            deals.addDeal(created)
            draft.toggleSalesDeal(created.id)
            createDealKey.current = ''
            setCreateDealOpen(false)
            showToast('새 딜을 생성하고 보고서에 추가했습니다.')
          }}
          onClose={() => {
            createDealKey.current = ''
            setCreateDealOpen(false)
          }}
        />
      )}
    </section>
  )
}

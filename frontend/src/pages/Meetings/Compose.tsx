// 업무 보고서 작성 화면.
//
// 왼쪽은 미팅 공통 정보·원문이고, 오른쪽은 선택한 딜마다 하나씩 생기는 보고서입니다.
// 저장할 때는 공통 기록과 모든 딜 카드를 미팅 보고서 한 건으로 묶습니다.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { isAxiosError } from 'axios'

import { useCurrentUser } from '@/auth/sessionContext'
import { errorMessage } from '@/api/errorMessage'
import {
  latestMeetingProcessing,
  processMeeting,
  readReport,
  saveMeetingNotes,
  waitForMeetingProcessing,
} from '@/api/reportAgent'
import Button, { buttonClass } from '@/components/Button'
import { ChevronLeftIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { SkeletonDetail } from '@/components/Skeleton'
import { meetingPickPath, meetingReportPath, ROUTES } from '@/constants/routes'
import { isOwnAgendaItem, useAgendaItem } from '@/shared/agenda'
import { showToast } from '@/shared/toast'
import type { MeetingAssignmentOverride, MeetingDealRef, MeetingProgress } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'

import DealReportCard from './components/DealReportCard'
import MeetingInfoPanel from './components/MeetingInfoPanel'
import MeetingInputPanel from './components/MeetingInputPanel'
import MeetingSharedPanel from './components/MeetingSharedPanel'
import { canReassignEvidence } from './generatedDraft'
import {
  acknowledgeMeetingGeneration,
  startMeetingGeneration,
  useMeetingGeneration,
} from './meetingGenerationStore'
import useCompanyDeals from './useCompanyDeals'
import useMeetingDraft from './useMeetingDraft'
import useMeetingReports, {
  type MeetingDealDraftPayload,
  type MeetingDraftPayload,
  saveMeetingDraft,
  toMeetingReport,
  useMeetingReportOfAgenda,
} from './useMeetingReports'

import styles from './Compose.module.scss'

type Confirm = { kind: 'apply'; dealId: string } | null

export default function Compose() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { memberId, isManager } = useCurrentUser()
  const notesAbort = useRef<AbortController | null>(null)
  const saveAbort = useRef<AbortController | null>(null)
  const recoveredReportId = useRef('')
  const mirroredGeneration = useRef({
    requestId: '',
    progress: null as MeetingProgress | null,
    reportId: '',
    terminal: false,
  })
  const [savingNotes, setSavingNotes] = useState(false)
  const [savingAll, setSavingAll] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [runErrors, setRunErrors] = useState<Record<string, string>>({})
  const [notesDirty, setNotesDirty] = useState(false)
  const agendaId = params.get('agenda') ?? ''
  const generation = useMeetingGeneration(agendaId)
  const generating = generation?.status === 'running'
  useEffect(() => {
    setSavingNotes(false)
    setSavingAll(false)
    setSubmitting(false)
    setNotesDirty(false)
    setRunError(null)
    setRunErrors({})
    recoveredReportId.current = ''
    mirroredGeneration.current = {
      requestId: '',
      progress: null,
      reportId: '',
      terminal: false,
    }
    return () => {
      notesAbort.current?.abort()
      notesAbort.current = null
      saveAbort.current?.abort()
      saveAbort.current = null
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
  const { saveDraft, saveReport, error: saveError, pending } = useMeetingReports()
  const draftReady =
    !agendaLoading && !loading && !agendaError && !loadError && item?.id === agendaId
  const draft = useMeetingDraft(item, savedReport, draftReady)
  const { beginGeneration, bindReport, receiveProgress, acceptGenerated, generationFailed } = draft
  useEffect(() => {
    if (!generation || !draftReady) return
    const mirror = mirroredGeneration.current
    if (mirror.requestId !== generation.requestId) {
      mirror.requestId = generation.requestId
      mirror.progress = null
      mirror.reportId = ''
      mirror.terminal = false
      beginGeneration(generation.dealIds)
      setRunError(null)
      setRunErrors({})
    }

    if (generation.status === 'running') {
      if (generation.savedReport && mirror.reportId !== generation.savedReport.id) {
        mirror.reportId = generation.savedReport.id
        bindReport(generation.savedReport)
      }
    }

    if (generation.status === 'running') {
      if (generation.progress && mirror.progress !== generation.progress) {
        mirror.progress = generation.progress
        receiveProgress(generation.progress)
      }
      return
    }
    if (mirror.terminal) return
    mirror.terminal = true
    if (generation.status === 'completed') {
      acceptGenerated(generation.report, generation.writingFailed)
      setRunErrors(generation.errors)
    } else {
      generationFailed(generation.dealIds, new Error(generation.error))
      setRunError(generation.error)
    }
    acknowledgeMeetingGeneration(agendaId, generation.requestId)
  }, [
    generation,
    draftReady,
    agendaId,
    beginGeneration,
    bindReport,
    receiveProgress,
    acceptGenerated,
    generationFailed,
  ])
  useEffect(() => {
    if (
      !draftReady ||
      !savedReport ||
      generation ||
      recoveredReportId.current === savedReport.id ||
      savedReport.ownerMemberId !== memberId ||
      !['draft', 'changes_requested'].includes(savedReport.apiStatus ?? '')
    )
      return
    recoveredReportId.current = savedReport.id
    void latestMeetingProcessing(savedReport.id)
      .then((run) => {
        if (!['queued', 'running'].includes(run.status_code)) return
        const dealIds = savedReport.dealSections.map((section) => section.salesDealId)
        startMeetingGeneration({
          agendaId,
          dealIds,
          resumed: true,
          execute: async (onProgress, onReportSaved) => {
            onReportSaved(savedReport)
            const completed = await waitForMeetingProcessing(run, onProgress)
            const persisted = await readReport(savedReport.id)
            return {
              report: toMeetingReport(persisted),
              writingFailed: completed.output_snapshot.reports === null,
              errors: completed.output_snapshot.errors,
            }
          },
        })
      })
      .catch((reason: unknown) => {
        if (!isAxiosError(reason) || reason.response?.status !== 404) {
          setRunError(errorMessage(reason, '진행 중인 보고서 상태를 확인하지 못했습니다.'))
        }
      })
  }, [agendaId, draftReady, generation, memberId, savedReport])
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
  const busy = pending || generating || savingNotes || savingAll || submitting
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
  const editableDealIds = draft.salesDealIds.filter(
    (id) =>
      canEditDeal(id) &&
      ['draft', 'changes_requested'].includes(draft.draftsByDeal[id]?.statusCode),
  )
  const emptyDealIds = editableDealIds.filter((id) => draft.draftsByDeal[id]?.phase === 'idle')
  const brokenDealIds = editableDealIds.filter(
    (id) => (draft.draftsByDeal[id]?.sectionIssues.length ?? 0) > 0,
  )
  // 잠금 키는 딜이 아니라 미팅입니다. 사전저장부터 서버 apply까지 한 번만 실행합니다.
  const generateAll = async (overrides: MeetingAssignmentOverride[] = []) => {
    if (busy || !generatable || !draft.canGenerate) return false
    if (notesDirty) {
      setRunError('수정한 공통·미지정 메모를 먼저 저장한 뒤 다시 생성하세요.')
      return false
    }
    if (overrides.length && !canReassign) return false
    const targets = [...draft.salesDealIds]
    const payload = payloadForMeeting()
    const rerun = overrides.length
      ? {
          parent_run_id: result!.runId,
          assignment_overrides: [...overrides],
        }
      : undefined
    setRunError(null)
    setRunErrors({})
    return startMeetingGeneration({
      agendaId,
      dealIds: targets,
      execute: async (onProgress, onReportSaved) => {
        const report = await saveMeetingDraft(payload)
        onReportSaved(report)
        const run = await processMeeting(report.id, rerun, (progress) => {
          onProgress({
            ...progress,
            previews: progress.previews.filter(
              (preview) => preview.section !== 'deal' || targets.includes(preview.sales_deal_id!),
            ),
          })
        })
        const persisted = await readReport(report.id)
        return {
          report: toMeetingReport(persisted),
          writingFailed: run.output_snapshot.reports === null,
          errors: run.output_snapshot.errors,
        }
      },
    })
  }

  const saveShared = async (common: string | null, unassigned: string | null) => {
    if (busy || !canEditNotes || !result) return
    const controller = new AbortController()
    notesAbort.current = controller
    setSavingNotes(true)
    setRunError(null)
    try {
      const report = await saveMeetingNotes(
        result.runId,
        result.shared!.revision,
        common,
        unassigned,
      )
      if (controller.signal.aborted) return
      draft.acceptShared(toMeetingReport(report))
      showToast('미팅 공통·미지정 메모를 저장했습니다.')
    } catch (reason: unknown) {
      if (controller.signal.aborted) return
      setRunError(errorMessage(reason, '미팅 메모를 저장하지 못했습니다.'))
    } finally {
      if (notesAbort.current === controller) {
        notesAbort.current = null
        setSavingNotes(false)
      }
    }
  }

  const saveAll = async () => {
    if (
      busy ||
      saveAbort.current ||
      editableDealIds.length !== draft.salesDealIds.length ||
      emptyDealIds.length > 0 ||
      brokenDealIds.length > 0
    )
      return

    const controller = new AbortController()
    saveAbort.current = controller
    setSavingAll(true)
    setRunError(null)

    try {
      const report = await saveDraft(payloadForMeeting(), controller.signal)
      if (controller.signal.aborted || saveAbort.current !== controller) return
      draft.bindReport(report)
      showToast('미팅 보고서 초안을 임시저장했습니다.')
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        setRunError(errorMessage(reason, '미팅 보고서 초안을 임시저장하지 못했습니다.'))
      }
    } finally {
      if (saveAbort.current === controller) {
        saveAbort.current = null
        setSavingAll(false)
      }
    }
  }

  const submitAll = async () => {
    if (
      busy ||
      saveAbort.current ||
      editableDealIds.length !== draft.salesDealIds.length ||
      emptyDealIds.length > 0 ||
      brokenDealIds.length > 0
    )
      return

    const controller = new AbortController()
    saveAbort.current = controller
    setSubmitting(true)
    setRunError(null)

    try {
      const report = await saveReport(payloadForMeeting(), controller.signal)
      if (controller.signal.aborted || saveAbort.current !== controller) return
      draft.bindReport(report)
      showToast('업무보고를 확정했습니다.')
      navigate(meetingReportPath(report.id), { replace: true })
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        setRunError(errorMessage(reason, '업무보고를 확정하지 못했습니다.'))
      }
    } finally {
      if (saveAbort.current === controller) {
        saveAbort.current = null
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
          <p>일부 처리가 완료되지 않았습니다. 저장된 보고서와 기존 작성 내용은 유지됩니다.</p>
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
              canGenerate={draft.canGenerate && generatable && !notesDirty}
              generating={generating}
              contentLabel="미팅 내용"
              generateLabel="미팅 전체 분석·보고서 작성"
              disabled={busy || !canEdit}
              onGenerate={() => void generateAll()}
            />
            {draft.salesDealIds.length > 0 && !generatable && (
              <p className={styles.generationNote}>
                선택한 딜 중 읽기 전용 또는 수정중 상태가 아닌 보고서가 있어 미팅 전체를 다시 생성할
                수 없습니다.
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
          {draft.salesDealIds.length > 0 && (
            <div className={styles.saveBar} aria-busy={savingAll || submitting}>
              <div className={styles.saveCopy}>
                <strong>미팅 보고서</strong>
                <p>공통 기록과 딜 {draft.salesDealIds.length}건을 한 문서로 저장합니다.</p>
              </div>
              <Button
                variant="outline"
                type="button"
                className={styles.saveAllButton}
                aria-label="미팅 보고서 임시저장"
                disabled={
                  busy ||
                  editableDealIds.length !== draft.salesDealIds.length ||
                  emptyDealIds.length > 0 ||
                  brokenDealIds.length > 0
                }
                onClick={() => void saveAll()}
              >
                {savingAll ? '저장 중…' : '임시저장'}
              </Button>
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
              evidence={result?.evidence}
              progress={draft.processingProgress}
              deals={draft.salesDealIds.map(dealRef)}
              disabled={busy}
              canReassign={canReassign}
              onSave={canEditNotes ? saveShared : undefined}
              onDirtyChange={setNotesDirty}
              onAssign={canEdit ? (assignments) => void generateAll(assignments) : undefined}
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

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
import { CheckIcon, ChevronLeftIcon } from '@/components/icons'
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
  type MeetingDraftPayload,
  saveMeetingDraft,
  toMeetingReport,
  useMeetingReportsOfAgenda,
} from './useMeetingReports'

import styles from './Compose.module.scss'

type Confirm = { kind: 'apply'; dealId: string } | null
type SaveFeedback =
  | { kind: 'success'; count: number; snapshot: string }
  | { kind: 'error'; saved: number; failed: string[]; reason: string; snapshot: string }

export default function Compose() {
  const [params] = useSearchParams()
  const { memberId, isManager } = useCurrentUser()
  const notesAbort = useRef<AbortController | null>(null)
  const saveAbort = useRef<AbortController | null>(null)
  const mirroredGeneration = useRef({
    requestId: '',
    progress: null as MeetingProgress | null,
    reportIds: new Set<string>(),
    terminal: false,
  })
  const [savingNotes, setSavingNotes] = useState(false)
  const [savingAll, setSavingAll] = useState(false)
  const [saveFeedback, setSaveFeedback] = useState<SaveFeedback | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [runErrors, setRunErrors] = useState<Record<string, string>>({})
  const [notesDirty, setNotesDirty] = useState(false)
  const agendaId = params.get('agenda') ?? ''
  const generation = useMeetingGeneration(agendaId)
  const generating = generation?.status === 'running'
  useEffect(() => {
    setSavingNotes(false)
    setSavingAll(false)
    setSaveFeedback(null)
    setNotesDirty(false)
    setRunError(null)
    setRunErrors({})
    mirroredGeneration.current = {
      requestId: '',
      progress: null,
      reportIds: new Set<string>(),
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
    reports: savedReports,
    loading,
    error: loadError,
    reload,
  } = useMeetingReportsOfAgenda(agendaId)
  const { saveDraft, pending } = useMeetingReports()
  const draftReady =
    !agendaLoading && !loading && !agendaError && !loadError && item?.id === agendaId
  const draft = useMeetingDraft(item, savedReports, draftReady)
  const { beginGeneration, bindReport, receiveProgress, acceptGenerated, generationFailed } = draft
  useEffect(() => {
    if (!generation || !draftReady) return
    const mirror = mirroredGeneration.current
    if (mirror.requestId !== generation.requestId) {
      mirror.requestId = generation.requestId
      mirror.progress = null
      mirror.reportIds = new Set<string>()
      mirror.terminal = false
      beginGeneration(generation.dealIds)
      setRunError(null)
      setRunErrors({})
    }

    for (const report of generation.savedReports) {
      if (!report.salesDealId || mirror.reportIds.has(report.id)) continue
      mirror.reportIds.add(report.id)
      bindReport(report.salesDealId, report)
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
      acceptGenerated(generation.reports, generation.writingFailed)
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
  const busy = pending || generating || savingNotes || savingAll
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
  const editableDealIds = draft.salesDealIds.filter(
    (id) =>
      canEditDeal(id) &&
      ['draft', 'changes_requested'].includes(draft.draftsByDeal[id]?.statusCode),
  )
  const emptyDealIds = editableDealIds.filter((id) => draft.draftsByDeal[id]?.phase === 'idle')
  const brokenDealIds = editableDealIds.filter(
    (id) => (draft.draftsByDeal[id]?.sectionIssues.length ?? 0) > 0,
  )
  const saveSnapshot = JSON.stringify({
    transcript: draft.transcript,
    attachments: draft.attachments,
    reports: editableDealIds.map((id) => {
      const state = draft.draftsByDeal[id]
      return [id, state?.title, state?.values, state?.sectionIssues]
    }),
  })

  // 잠금 키는 딜이 아니라 미팅입니다. 사전저장부터 서버 apply까지 한 번만 실행합니다.
  const generateAll = async (overrides: MeetingAssignmentOverride[] = []) => {
    if (busy || !generatable || !draft.canGenerate) return false
    if (notesDirty) {
      setRunError('수정한 공통·미지정 메모를 먼저 저장한 뒤 다시 생성하세요.')
      return false
    }
    if (overrides.length && !canReassign) return false
    const targets = [...draft.salesDealIds]
    const payloads = targets.map(payloadFor)
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
        const saved = await Promise.allSettled(
          payloads.map(async (payload) => {
            const report = await saveMeetingDraft(payload)
            onReportSaved(report)
            return report
          }),
        )
        const failed = saved.find((entry) => entry.status === 'rejected')
        if (failed?.status === 'rejected') throw failed.reason
        const reports = saved.flatMap((entry) =>
          entry.status === 'fulfilled' ? [entry.value] : [],
        )
        const run = await processMeeting(
          reports.map((report) => report.id),
          rerun,
          (progress) => {
            onProgress({
              ...progress,
              previews: progress.previews.filter(
                (preview) => preview.section !== 'deal' || targets.includes(preview.sales_deal_id!),
              ),
            })
          },
        )
        const persisted = await applyMeetingProcessing(run.id)
        return {
          reports: persisted.map(toMeetingReport),
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
      editableDealIds.length === 0 ||
      emptyDealIds.length > 0 ||
      brokenDealIds.length > 0
    )
      return

    const targets = [...editableDealIds]
    const snapshot = saveSnapshot
    const controller = new AbortController()
    saveAbort.current = controller
    setSavingAll(true)
    setSaveFeedback(null)

    try {
      const results = await Promise.allSettled(
        targets.map(async (id) => {
          const report = await saveDraft(payloadFor(id), controller.signal)
          if (!controller.signal.aborted && saveAbort.current === controller) {
            draft.bindReport(id, report)
          }
          return report
        }),
      )
      if (controller.signal.aborted || saveAbort.current !== controller) return

      const failed = results.flatMap((result, index) =>
        result.status === 'rejected' ? [dealRef(targets[index]).label] : [],
      )
      if (failed.length > 0) {
        const firstFailure = results.find((result) => result.status === 'rejected')
        setSaveFeedback({
          kind: 'error',
          saved: targets.length - failed.length,
          failed,
          snapshot,
          reason:
            firstFailure?.status === 'rejected'
              ? errorMessage(firstFailure.reason, '저장 요청을 완료하지 못했습니다.')
              : '저장 요청을 완료하지 못했습니다.',
        })
        return
      }

      setSaveFeedback({ kind: 'success', count: targets.length, snapshot })
      showToast(`${targets.length}개 딜 보고서를 모두 저장했습니다.`)
    } finally {
      if (saveAbort.current === controller) {
        saveAbort.current = null
        setSavingAll(false)
      }
    }
  }

  let saveNotice = {
    tone: 'idle',
    title: `딜 보고서 ${editableDealIds.length}건`,
    detail: '편집 가능한 딜 보고서를 한 번에 저장합니다.',
  }
  if (savingAll) {
    saveNotice = {
      tone: 'saving',
      title: '전체 저장 중',
      detail: `${editableDealIds.length}개 딜 보고서를 저장하고 있습니다.`,
    }
  } else if (saveFeedback?.kind === 'error' && saveFeedback.snapshot === saveSnapshot) {
    saveNotice = {
      tone: 'error',
      title: `저장 ${saveFeedback.saved}건 · 실패 ${saveFeedback.failed.length}건`,
      detail: `실패: ${saveFeedback.failed.join(', ')} · ${saveFeedback.reason}`,
    }
  } else if (saveFeedback?.kind === 'success' && saveFeedback.snapshot === saveSnapshot) {
    saveNotice = {
      tone: 'success',
      title: '전체 저장 완료',
      detail: `${saveFeedback.count}개 딜 보고서를 모두 저장했습니다.`,
    }
  } else if (emptyDealIds.length > 0) {
    saveNotice = {
      tone: 'dirty',
      title: '저장 전 작성이 필요합니다',
      detail: `${emptyDealIds.map((id) => dealRef(id).label).join(', ')} 보고서를 먼저 작성하세요.`,
    }
  } else if (brokenDealIds.length > 0) {
    saveNotice = {
      tone: 'dirty',
      title: '저장 전 항목 복원이 필요합니다',
      detail: `${brokenDealIds.map((id) => dealRef(id).label).join(', ')} 보고서의 사라진 항목 제목을 되살리세요.`,
    }
  } else if (editableDealIds.length === 0) {
    saveNotice = {
      tone: 'idle',
      title: '저장할 보고서가 없습니다',
      detail: '수정 가능한 딜 보고서가 없습니다.',
    }
  } else if (saveFeedback) {
    saveNotice = {
      tone: 'dirty',
      title: '저장하지 않은 변경사항',
      detail: '이전 저장 시도 후 바뀐 내용이 있습니다. 다시 전체 저장하세요.',
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

      {runError && (
        <p className={styles.mutationError} role="alert">
          {runError}
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
          {draft.salesDealIds.length > 0 && (
            <div className={styles.saveBar} data-tone={saveNotice.tone} aria-busy={savingAll}>
              <span className={styles.saveMark} aria-hidden="true">
                {saveNotice.tone === 'success' ? (
                  <CheckIcon width={16} height={16} />
                ) : saveNotice.tone === 'error' ? (
                  '!'
                ) : saveNotice.tone === 'saving' ? (
                  '…'
                ) : null}
              </span>
              <div
                className={styles.saveCopy}
                role={saveNotice.tone === 'error' ? 'alert' : 'status'}
                aria-live={saveNotice.tone === 'error' ? 'assertive' : 'polite'}
              >
                <strong>{saveNotice.title}</strong>
                <p>{saveNotice.detail}</p>
              </div>
              <Button
                type="button"
                className={styles.saveAllButton}
                aria-label="딜 보고서 전체 저장"
                disabled={
                  busy ||
                  editableDealIds.length === 0 ||
                  emptyDealIds.length > 0 ||
                  brokenDealIds.length > 0
                }
                onClick={() => void saveAll()}
              >
                {savingAll ? '저장 중…' : '전체 저장'}
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

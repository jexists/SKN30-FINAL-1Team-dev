// 업무 보고서 작성 화면.
//
// 왼쪽은 참고 자료(미팅 정보 / AI 원본)를 탭으로 갈아 끼우고, 오른쪽은 언제나 최종
// 보고서입니다. 탭이 무엇이든 오른쪽이 그대로 남아야 "원본을 보면서 고친다" 가 됩니다.
//
// AI 원본과 최종 보고서는 useMeetingDraft 가 두 벌로 나눠 들고 있습니다.
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import { SkeletonDetail } from '@/components/Skeleton'
import Tabs from '@/components/Tabs'
import { meetingReportPath, ROUTES } from '@/constants/routes'
import DailyListLink from '@/pages/Daily/components/DailyListLink'
import { useAgendaItem } from '@/shared/agenda'
import { showToast } from '@/shared/toast'
import { fmtDot, parseISO } from '@/utils/date'

import AiOriginalPanel from './components/AiOriginalPanel'
import MeetingInfoPanel from './components/MeetingInfoPanel'
import MeetingInputPanel from './components/MeetingInputPanel'
import ReportSheet from './components/ReportSheet'
import useCompanyDeals from './useCompanyDeals'
import useGenerationSteps from './useGenerationSteps'
import useMeetingDraft from './useMeetingDraft'
import useMeetingReports, {
  useMeetingReportOfAgenda,
  type MeetingDraftPayload,
} from './useMeetingReports'

import styles from './Compose.module.scss'

/** 되돌릴 수 없는 세 갈래. 각각 먼저 묻습니다. */
type Confirm = { kind: 'apply' } | { kind: 'save' } | null

/** 왼쪽 참고 열에서 무엇을 보고 있는지. */
type Reference = 'info' | 'ai'

export default function Compose() {
  const [params] = useSearchParams()
  const navigate = useNavigate()

  const agendaId = params.get('agenda') ?? ''
  const {
    item,
    loading: agendaLoading,
    error: agendaError,
    reload: reloadAgenda,
  } = useAgendaItem(agendaId)

  const { report: saved, loading, error: loadError, reload } = useMeetingReportOfAgenda(agendaId)
  const { saveReport, saveDraft, error: saveError, pending } = useMeetingReports()
  const error = loadError ?? saveError
  // 팀장 확인이 끝나기 전까지는 다시 열어 고칠 수 있습니다.
  const locked = saved?.review === 'approved'

  const draft = useMeetingDraft(item, saved)
  const deals = useCompanyDeals(item?.customerCompanyId)
  const generation = useGenerationSteps(draft.phase === 'generating')

  const [reference, setReference] = useState<Reference>('info')
  const [confirm, setConfirm] = useState<Confirm>(null)

  if (agendaLoading || loading) {
    return (
      <section>
        <SkeletonDetail label="업무 보고서를 불러오는 중입니다." title height={520} />
      </section>
    )
  }

  if (agendaError || error) {
    return (
      <section>
        <p className={styles.notFound} role="alert">
          {agendaError ?? error}
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

  // 일정이 없으면 무엇에 대한 기록인지 알 수 없습니다. 빈 폼을 띄우지 않습니다.
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

  /*
   * 고른 딜의 이름표. 목록에 있으면 지금 값으로, 없으면 저장해 둔 이름표를 씁니다 —
   * 담당이 바뀌어 목록에서 빠진 딜이라도 그때 무엇을 골랐는지는 남아야 합니다.
   */
  const salesDeals = draft.salesDealIds.map((id) => {
    const deal = deals.deals.find((one) => one.id === id)
    if (deal) return { id, label: deal.no, note: deal.title.trim() || deal.product }
    return saved?.salesDeals?.find((one) => one.id === id) ?? { id, label: id }
  })

  const payload: MeetingDraftPayload = {
    agendaId: item.id,
    template: draft.template,
    date: item.date,
    time: item.time,
    hospital: item.hospital,
    dept: item.dept,
    contact: item.contact,
    product: item.product,
    place: item.place,
    title: draft.title,
    transcript: draft.transcript,
    values: draft.values,
    attachments: draft.attachments,
    salesDealIds: draft.salesDealIds,
    salesDeals,
    evidence: draft.evidence,
    aiValues: draft.aiValues,
    aiEvidence: draft.aiEvidence,
    aiGeneratedAt: draft.aiGeneratedAt,
  }

  // 에이전트는 저장된 보고서를 읽으므로 먼저 임시저장해 id 를 만듭니다.
  const onGenerate = async () => {
    const first = !draft.hasAiOriginal
    try {
      const report = await saveDraft(payload)
      // 실패해도 generate 는 던지지 않고 화면에 사유를 남깁니다. 그때 AI 원본으로
      // 넘기면 있지도 않은 탭을 펼치게 되므로, 만들어졌을 때만 옮깁니다.
      if (!(await draft.generate(report.id, generation.onStatus))) return
      // 만든 뒤에는 언제나 왼쪽을 AI 원본으로 넘깁니다. 첫 생성에서야 이 탭이 처음
      // 생기는데, 화면이 그대로면 참고 자료가 두 벌이 됐다는 것을 알 길이 없습니다.
      setReference('ai')
      showToast(
        first
          ? 'AI 초안을 만들어 보고서에 넣었습니다. 왼쪽에서 원본을 볼 수 있습니다.'
          : '새 AI 원본을 만들었습니다. 왼쪽에서 확인하세요.',
      )
    } catch {
      // 저장 훅이 같은 화면에 오류를 표시합니다.
    }
  }

  const onSubmit = async () => {
    if (locked) return
    try {
      const report = await saveReport(payload)
      setConfirm(null)
      navigate(meetingReportPath(report.id))
    } catch {
      // 훅이 같은 화면에 오류를 표시합니다.
    }
  }

  // 만든 적이 없으면 볼 것이 없으므로 탭 자체를 두지 않습니다.
  // AI 원본은 만들어졌을 때만 볼 것이 있습니다. 없는데 그쪽을 가리키고 있으면
  // 제목은 '미팅 정보' 인데 내용은 빈 원본판인 화면이 됩니다.
  const showAi = reference === 'ai' && draft.hasAiOriginal

  const references = [
    { value: 'info' as const, label: '미팅 정보' },
    ...(draft.hasAiOriginal
      ? [
          {
            value: 'ai' as const,
            label: 'AI 원본',
            ...(draft.pendingAi ? { tone: 'purple' as const } : {}),
          },
        ]
      : []),
  ]

  return (
    <section className={styles.page}>
      <h1 className="sr-only">
        {item.hospital} {item.title} 업무 보고서 작성
      </h1>

      {/*
        누가·언제인지는 왼쪽 미팅 정보가 이미 말합니다. 머리말이 맡는 것은
        여기서 나가는 길 하나뿐이라 버튼만 오른쪽 끝에 둡니다.
      */}
      <header className={styles.head}>
        <DailyListLink tab="meeting" />
      </header>

      {locked && saved && (
        <p className={styles.locked}>
          팀장 확인이 끝난 업무 보고서라 수정할 수 없습니다.{' '}
          <Link to={meetingReportPath(saved.id)}>보고서 열기</Link>
        </p>
      )}

      <div className={styles.layout}>
        <div className={styles.side}>
          <aside className={styles.reference}>
            {/*
              패널의 머리. 볼 것이 둘이면 탭으로 고르고, 하나뿐이면 그냥 제목입니다.
              한 칸짜리 탭은 고를 것이 없는데 고르라고 하는 셈입니다.
            */}
            <div className={styles.refHead}>
              {draft.hasAiOriginal ? (
                <Tabs
                  items={references}
                  value={reference}
                  onChange={setReference}
                  label="참고 자료"
                  variant="segmented"
                />
              ) : (
                <h2 className={styles.refTitle}>미팅 정보</h2>
              )}

              {!showAi && item.stage && <span className={styles.pill}>{item.stage}</span>}
            </div>

            {showAi ? (
              <AiOriginalPanel
                template={draft.template}
                values={draft.aiValues}
                evidence={draft.aiEvidence}
                generatedAt={draft.aiGeneratedAt}
                pending={draft.pendingAi}
                disabled={locked}
                onApply={() => setConfirm({ kind: 'apply' })}
              />
            ) : (
              <MeetingInfoPanel
                item={item}
                deals={deals.deals}
                dealsLoading={deals.loading}
                dealsError={deals.error}
                onReloadDeals={deals.reload}
                selectedDealIds={draft.salesDealIds}
                onToggleDeal={draft.toggleSalesDeal}
                disabled={locked || pending}
              />
            )}
          </aside>

          <div className={styles.input}>
            <MeetingInputPanel
              attachments={draft.attachments}
              onAttach={(files) => void draft.addAttachments(files)}
              onRemoveAttachment={draft.removeAttachment}
              attachmentError={draft.attachmentError}
              transcript={draft.transcript}
              onTranscriptChange={draft.setTranscript}
              canGenerate={draft.canGenerate}
              generating={draft.phase === 'generating'}
              hasAiOriginal={draft.hasAiOriginal}
              disabled={locked || pending}
              onGenerate={() => void onGenerate()}
            />
          </div>
        </div>

        {/* 넣는 것과 나오는 것이 한 열에 위아래로 섭니다. 왼쪽은 참고만 하는 열입니다. */}
        <div className={styles.work}>
          <ReportSheet
            phase={draft.phase}
            template={draft.template}
            title={draft.title}
            onTitleChange={draft.setTitle}
            when={`${fmtDot(parseISO(item.date))} ${item.time}`}
            values={draft.values}
            docKey={draft.docKey}
            onChange={draft.applyDocument}
            sectionIssues={draft.sectionIssues}
            onRestoreSections={draft.restoreSections}
            evidence={draft.evidence}
            generationStep={generation.step}
            generationError={draft.generationError}
            onRetryGenerate={() => void onGenerate()}
            locked={locked}
            saving={pending}
            hasAiOriginal={draft.hasAiOriginal}
            onStartManual={draft.startManual}
            onRegenerate={() => void onGenerate()}
            onPrint={() => window.print()}
            onSubmit={() => setConfirm({ kind: 'save' })}
          />
        </div>
      </div>

      {confirm?.kind === 'apply' && (
        <Modal
          title="새 AI 원본을 최종 보고서에 적용할까요?"
          description="AI가 작성하는 항목이 새 원본으로 바뀝니다. 직접 고친 내용도 함께 바뀝니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  draft.applyAi()
                  setConfirm(null)
                  setReference('info')
                  showToast('새 AI 원본을 최종 보고서에 적용했습니다.')
                }}
              >
                적용
              </Button>
            </>
          }
        >
          <p>적용하지 않고 원본만 참고하면서 오른쪽을 직접 고쳐도 됩니다.</p>
        </Modal>
      )}

      {confirm?.kind === 'save' && (
        <Modal
          title="업무 보고서를 제출할까요?"
          description="제출하면 고객 히스토리와 그날 업무보고의 활동 내역에 반영됩니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button type="button" disabled={pending} onClick={() => void onSubmit()}>
                {pending ? '제출 중…' : '제출'}
              </Button>
            </>
          }
        >
          <p>
            {item.hospital} · {fmtDot(parseISO(item.date))} {item.time} · 첨부{' '}
            {draft.attachments.length}건
          </p>
        </Modal>
      )}
    </section>
  )
}

// 미팅 보고서 작성 화면.
//
// 왼쪽은 참고 자료(미팅 정보 / AI 원본)를 탭으로 갈아 끼우고, 오른쪽은 언제나 최종
// 보고서입니다. 탭이 무엇이든 오른쪽이 그대로 남아야 "원본을 보면서 고친다" 가 됩니다.
//
// AI 원본과 최종 보고서는 useMeetingDraft 가 두 벌로 나눠 들고 있습니다.
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import Button from '@/components/Button'
import { ChevronLeftIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { SkeletonDetail } from '@/components/Skeleton'
import Tabs from '@/components/Tabs'
import { meetingReportPath, ROUTES } from '@/constants/routes'
import { useAgendaState } from '@/shared/agenda'
import { showToast } from '@/shared/toast'
import { fmtDot, parseISO } from '@/utils/date'

import AiOriginalPanel from './components/AiOriginalPanel'
import MeetingInfoPanel from './components/MeetingInfoPanel'
import ReportSheet from './components/ReportSheet'
import useMeetingDraft from './useMeetingDraft'
import useMeetingReports, { type MeetingDraftPayload } from './useMeetingReports'

import styles from './Compose.module.scss'

/** 되돌릴 수 없는 세 갈래. 각각 먼저 묻습니다. */
type Confirm = { kind: 'apply' } | { kind: 'save' } | { kind: 'reset' } | null

/** 왼쪽 참고 열에서 무엇을 보고 있는지. */
type Reference = 'info' | 'ai'

export default function Compose() {
  const [params] = useSearchParams()
  const navigate = useNavigate()

  const agendaId = params.get('agenda') ?? ''
  const {
    items: agenda,
    loading: agendaLoading,
    error: agendaError,
    reload: reloadAgenda,
  } = useAgendaState(undefined, undefined, true)
  const item = agendaId ? agenda.find((entry) => entry.id === agendaId) : undefined

  const { findByAgenda, saveReport, saveDraft, loading, error, pending, reload } =
    useMeetingReports()
  const saved = agendaId ? findByAgenda(agendaId) : undefined
  const locked = saved?.status === '확정'

  const draft = useMeetingDraft(item, saved)

  const [reference, setReference] = useState<Reference>('info')
  const [confirm, setConfirm] = useState<Confirm>(null)
  const [savedNote, setSavedNote] = useState(false)

  if (agendaLoading || loading) {
    return (
      <section>
        <SkeletonDetail label="미팅 보고서를 불러오는 중입니다." title height={520} />
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
        <h1 className="sr-only">미팅 보고서 작성</h1>
        <p className={styles.notFound}>
          기록할 일정을 찾을 수 없습니다.{' '}
          <Link to={ROUTES.DASHBOARD}>대시보드에서 일정을 고르세요.</Link>
        </p>
      </section>
    )
  }

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
      await draft.generate(report.id)
      // 처음 만든 것은 최종 보고서에 바로 놓이므로 오른쪽을 보면 됩니다. 두 번째부터는
      // 최종 보고서를 건드리지 않으니 새 원본이 어디 있는지 알려 줘야 합니다.
      if (!first) {
        setReference('ai')
        showToast('새 AI 원본을 만들었습니다. 왼쪽에서 확인하세요.')
      }
    } catch {
      // 저장 훅이 같은 화면에 오류를 표시합니다.
    }
  }

  const onSaveDraft = async () => {
    try {
      await saveDraft(payload)
      setSavedNote(true)
    } catch {
      setSavedNote(false)
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
        {item.hospital} {item.title} 미팅 보고서 작성
      </h1>

      <header className={styles.head}>
        <Link className={styles.back} to={ROUTES.DASHBOARD}>
          <ChevronLeftIcon />
          대시보드
        </Link>
        <p className={styles.pageTitle}>미팅 보고서</p>
      </header>

      {savedNote && (
        <p className={styles.savedNote}>임시저장했습니다. 이 일정에서 다시 열면 이어서 씁니다.</p>
      )}

      {locked && saved && (
        <p className={styles.locked}>
          이 미팅 보고서는 이미 제출되어 수정할 수 없습니다.{' '}
          <Link to={meetingReportPath(saved.id)}>확정한 보고서 열기</Link>
        </p>
      )}

      <div className={styles.layout}>
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

            {reference === 'info' && item.stage && (
              <span className={styles.pill}>{item.stage}</span>
            )}
          </div>

          {reference === 'info' ? (
            <MeetingInfoPanel
              item={item}
              attachments={draft.attachments}
              transcript={draft.transcript}
              onTranscriptChange={draft.setTranscript}
              canGenerate={draft.canGenerate}
              generating={draft.phase === 'generating'}
              hasAiOriginal={draft.hasAiOriginal}
              disabled={locked || pending}
              generationError={draft.generationError}
              onGenerate={() => void onGenerate()}
              onReset={() => setConfirm({ kind: 'reset' })}
            />
          ) : (
            <AiOriginalPanel
              template={draft.template}
              values={draft.aiValues}
              evidence={draft.aiEvidence}
              generatedAt={draft.aiGeneratedAt}
              pending={draft.pendingAi}
              disabled={locked}
              onApply={() => setConfirm({ kind: 'apply' })}
            />
          )}
        </aside>

        <ReportSheet
          phase={draft.phase}
          template={draft.template}
          title={draft.title}
          onTitleChange={draft.setTitle}
          when={`${fmtDot(parseISO(item.date))} ${item.time}`}
          values={draft.values}
          aiFilledIds={draft.aiFilledIds}
          onChange={draft.setValue}
          evidence={draft.evidence}
          missing={draft.missing}
          locked={locked}
          saving={pending}
          hasAiOriginal={draft.hasAiOriginal}
          onStartManual={draft.startManual}
          onSaveDraft={() => void onSaveDraft()}
          onRegenerate={() => void onGenerate()}
          onPrint={() => window.print()}
          onSubmit={() => setConfirm({ kind: 'save' })}
        />
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

      {confirm?.kind === 'reset' && (
        <Modal
          title="처음부터 다시 쓸까요?"
          description="입력한 미팅 내용과 최종 보고서가 마지막 저장 상태로 돌아갑니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  draft.reset()
                  setConfirm(null)
                  setSavedNote(false)
                  setReference('info')
                }}
              >
                다시 쓰기
              </Button>
            </>
          }
        >
          <p>저장하지 않은 변경은 남지 않습니다.</p>
        </Modal>
      )}

      {confirm?.kind === 'save' && (
        <Modal
          title="미팅 보고서를 확정할까요?"
          description="확정하면 고객 히스토리와 그날 업무보고의 활동 내역에 반영됩니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button type="button" disabled={pending} onClick={() => void onSubmit()}>
                {pending ? '저장 중…' : '확정'}
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

// demo/layout_v2.html 의 #meetingDialog 를 화면 하나로 편 것입니다.
//
// 왼쪽은 "들은 것"(첨부·직접 입력), 오른쪽은 "정리한 것"(구조화 결과)입니다.
// 둘을 나란히 두어야 AI 가 채운 값이 무엇에서 나왔는지 눈으로 대볼 수 있습니다.
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import AttachmentPanel from '@/components/AttachmentPanel'
import Button from '@/components/Button'
import { ChevronLeftIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import ReportFields from '@/components/ReportFields'
import { meetingReportPath, ROUTES } from '@/constants/routes'
import { useAgendaState } from '@/shared/agenda'
import { fmtDay, parseISO } from '@/utils/date'

import MeetingFacts from './components/MeetingFacts'
import useMeetingDraft from './useMeetingDraft'
import useMeetingReports, { type MeetingDraftPayload } from './useMeetingReports'

import styles from './Compose.module.scss'

/** 확인이 필요한 두 갈래. 하나는 덮어쓰기, 하나는 확정입니다. */
type Confirm = { kind: 'regenerate' } | { kind: 'save' } | null

export default function Compose() {
  const [params] = useSearchParams()
  const navigate = useNavigate()

  const agendaId = params.get('agenda') ?? ''
  const {
    items: agenda,
    loading: agendaLoading,
    error: agendaError,
    reload: reloadAgenda,
  } = useAgendaState()
  const item = agendaId ? agenda.find((entry) => entry.id === agendaId) : undefined

  const { findByAgenda, saveReport, saveDraft, loading, error, pending, reload } =
    useMeetingReports()
  const saved = agendaId ? findByAgenda(agendaId) : undefined
  const locked = saved?.status === '확정'

  const draft = useMeetingDraft(item, saved)

  const [confirm, setConfirm] = useState<Confirm>(null)
  const [savedNote, setSavedNote] = useState(false)

  if (agendaLoading || loading) {
    return <p role="status">미팅 기록을 불러오는 중입니다.</p>
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
        <h1 className="sr-only">미팅보고서 작성</h1>
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
    title: item.title,
    transcript: draft.transcript,
    values: draft.values,
    attachments: draft.attachments,
    evidence: draft.evidence,
  }

  const runGenerate = async () => {
    try {
      const report = await saveDraft(payload)
      await draft.generate(report.id)
    } catch {
      // 저장 훅이 오류를 표시합니다.
    }
  }

  const onGenerate = () => {
    // 사람이 손댄 항목이 있으면 덮어써도 되는지 먼저 묻습니다.
    if (draft.phase === 'ready' && draft.dirtyIds.size > 0) {
      setConfirm({ kind: 'regenerate' })
      return
    }
    void runGenerate()
  }

  const onSave = async () => {
    if (locked) return
    try {
      const report = await saveReport(payload)
      setConfirm(null)
      navigate(meetingReportPath(report.id))
    } catch {
      // 훅이 같은 화면에 오류를 표시합니다.
    }
  }

  const generateLabel =
    draft.phase === 'generating'
      ? '정리하는 중…'
      : draft.phase === 'ready'
        ? '다시 구조화'
        : 'AI로 구조화'

  const basis =
    draft.attachments.length > 0
      ? `첨부 ${draft.attachments.length}건 · 직접 입력 기준`
      : '직접 입력한 내용 기준'

  return (
    <section>
      <h1 className="sr-only">
        {item.hospital} {item.title} 미팅보고서 작성
      </h1>

      <header className={styles.head}>
        <Link className={styles.back} to={ROUTES.DASHBOARD}>
          <ChevronLeftIcon />
          대시보드
        </Link>

        <p className={styles.title}>
          {item.hospital}
          <span className={styles.subject}>{item.title}</span>
        </p>

        <span className={styles.when}>
          {fmtDay(parseISO(item.date))} {item.time}
        </span>

        <div className={styles.headActions}>
          <Button
            variant="outline"
            type="button"
            onClick={() => {
              draft.reset()
              setSavedNote(false)
            }}
          >
            처음부터 다시
          </Button>
          <Button
            variant="outline"
            type="button"
            disabled={pending || locked}
            onClick={async () => {
              try {
                await saveDraft(payload)
                setSavedNote(true)
              } catch {
                setSavedNote(false)
              }
            }}
          >
            {pending ? '저장 중…' : '임시저장'}
          </Button>
        </div>
      </header>

      {savedNote && (
        <p className={styles.savedNote}>임시저장했습니다. 이 일정에서 다시 열면 이어서 씁니다.</p>
      )}

      {saved?.status === '확정' && (
        <p className={styles.locked}>
          이 미팅 기록은 이미 제출되어 수정할 수 없습니다.{' '}
          <Link to={meetingReportPath(saved.id)}>기록한 보고서 열기</Link>
        </p>
      )}

      <div className={styles.layout}>
        <div className={styles.col}>
          <article className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>미팅 정보</h2>
              {item.stage && <span className={styles.pill}>{item.stage}</span>}
            </div>
            <p className={styles.panelNote}>캘린더 일정에서 가져왔습니다.</p>

            <MeetingFacts
              dept={item.dept}
              contact={item.contact}
              product={item.product}
              place={item.place}
            />

            <p className={styles.brief}>{item.brief}</p>
          </article>

          <article className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>첨부 자료</h2>
              <span className={styles.pill}>선택 사항</span>
            </div>

            <AttachmentPanel attachments={draft.attachments} readOnly />
          </article>

          <article className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>미팅 내용</h2>
            </div>
            <p className={styles.panelNote}>
              기억나는 미팅 내용을 적으세요. 이 내용이 구조화의 근거가 됩니다.
            </p>

            <label className="sr-only" htmlFor="transcript">
              미팅 내용 직접 입력
            </label>
            <textarea
              id="transcript"
              className={styles.transcript}
              rows={7}
              value={draft.transcript}
              placeholder="누구와 무엇을 이야기했는지 그대로 적으세요."
              onChange={(event) => draft.setTranscript(event.target.value)}
            />
          </article>

          <div className={styles.generate}>
            <Button
              type="button"
              onClick={onGenerate}
              disabled={pending || locked || !draft.canGenerate || draft.phase === 'generating'}
            >
              {generateLabel}
            </Button>
            <p className={styles.basis}>{draft.canGenerate ? basis : '미팅 내용을 입력하세요.'}</p>
            {draft.generationError && (
              <p className={styles.missing} role="alert">
                {draft.generationError}
              </p>
            )}
          </div>
        </div>

        <div className={styles.col}>
          <article className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>구조화 결과</h2>
              <span className={styles.pill}>확인 필요</span>
            </div>
            <p className={styles.panelNote}>
              {draft.template.owner ? `${draft.template.owner} 지정` : '기본 화면'} 양식 · 항목{' '}
              {draft.template.fields.length}개 · 확정 전까지 고객 히스토리와 업무보고에 반영되지
              않습니다.
            </p>

            {draft.phase === 'idle' && (
              <div className={styles.blank}>
                <p>왼쪽에 미팅 내용을 적은 뒤 “AI로 구조화”를 누르세요.</p>
                <p className={styles.blankSub}>직접 입력해서 채워도 됩니다.</p>
              </div>
            )}

            {draft.phase === 'generating' && (
              <div className={styles.blank}>
                <p>미팅 내용에서 참석자와 결정사항을 찾고 있습니다…</p>
              </div>
            )}

            {draft.phase === 'ready' && (
              <>
                <ReportFields
                  template={draft.template}
                  values={draft.values}
                  aiFilledIds={draft.aiFilledIds}
                  onChange={draft.setValue}
                />
                {draft.evidence && <p className={styles.evidence}>{draft.evidence}</p>}
              </>
            )}
          </article>

          <article className={styles.panel}>
            <p className={draft.missing.length > 0 ? styles.missing : styles.okay}>
              {draft.missing.length > 0
                ? `확정 전 확인: ${draft.missing.join(', ')}`
                : '확정할 수 있습니다.'}
            </p>

            <Button
              type="button"
              className={styles.submit}
              disabled={locked || draft.missing.length > 0}
              onClick={() => setConfirm({ kind: 'save' })}
            >
              확정하고 저장
            </Button>
          </article>
        </div>
      </div>

      {confirm?.kind === 'regenerate' && (
        <Modal
          title="직접 고친 내용을 덮어쓸까요?"
          description="AI가 채우는 항목만 새로 씁니다. 직접 입력한 항목은 그대로 둡니다."
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
                다시 구조화
              </Button>
            </>
          }
        >
          <p>
            지금까지 {draft.dirtyIds.size}개 항목을 직접 고쳤습니다. 고친 항목은 유지되고 나머지만
            새로 정리됩니다.
          </p>
        </Modal>
      )}

      {confirm?.kind === 'save' && (
        <Modal
          title="미팅 기록을 확정할까요?"
          description="확정하면 고객 히스토리와 그날 업무보고의 활동 내역에 반영됩니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button type="button" disabled={pending} onClick={onSave}>
                {pending ? '저장 중…' : '확정'}
              </Button>
            </>
          }
        >
          <p>
            {item.hospital} · {fmtDay(parseISO(item.date))} {item.time} · 첨부{' '}
            {draft.attachments.length}건
          </p>
        </Modal>
      )}
    </section>
  )
}

import { useCallback, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import AttachmentPanel from '@/components/AttachmentPanel'
import Button from '@/components/Button'
import { ChevronLeftIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import ReportFields from '@/components/ReportFields'
import { APPROVERS } from '@/shared/reports'
import { dailyReportPath, ROUTES } from '@/constants/routes'
import { fmtDot, parseISO, TODAY_ISO } from '@/utils/date'

import ActivityList from './components/ActivityList'
import { PERIOD_KIND, toPeriod } from './periods'
import useDailyDraft from './useDailyDraft'
import useDailyReports from './useDailyReports'

import styles from './Compose.module.scss'

/** 확인이 필요한 두 갈래. 둘 다 "쓰던 걸 버려도 되나"를 묻습니다. */
type Confirm = { kind: 'regenerate' } | { kind: 'date'; next: string } | { kind: 'submit' } | null

export default function Compose() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  const dateISO = params.get('date') ?? TODAY_ISO
  // ?kind= 는 기간 탭(?tab=)과 같은 어휘를 씁니다. 없으면 일일보고입니다.
  const kind = PERIOD_KIND[toPeriod(params.get('kind'))] ?? '일일'

  const draft = useDailyDraft(dateISO, kind)
  const { findByDate, submitReport, saveDraft } = useDailyReports()

  const [approver, setApprover] = useState<string>(APPROVERS[0])
  const [confirm, setConfirm] = useState<Confirm>(null)
  const [saved, setSaved] = useState(false)

  const existing = findByDate(dateISO, kind)
  const locked = existing?.status === '검토 대기' || existing?.status === '확정'

  const hasWork = draft.phase !== 'idle' || draft.dirtyIds.size > 0

  const payload = {
    date: dateISO,
    kind,
    approver,
    values: draft.values,
    activities: draft.activities,
    attachments: draft.attachments,
  }

  // 날짜만 바꿉니다. 종류(?kind=)는 그대로 두어야 양식이 바뀌지 않습니다.
  const changeDate = useCallback(
    (next: string) => {
      const query = new URLSearchParams(params)
      if (next === TODAY_ISO) query.delete('date')
      else query.set('date', next)
      setParams(query, { replace: true })
    },
    [params, setParams],
  )

  const onDateInput = (next: string) => {
    if (next === '' || next === dateISO) return
    // 쓰던 내용은 날짜가 바뀌면 사라집니다. 먼저 물어봅니다.
    if (hasWork) {
      setConfirm({ kind: 'date', next })
      return
    }
    changeDate(next)
  }

  const onGenerate = () => {
    // 사람이 손댄 항목이 있으면 덮어써도 되는지 먼저 묻습니다.
    if (draft.phase === 'ready' && draft.dirtyIds.size > 0) {
      setConfirm({ kind: 'regenerate' })
      return
    }
    draft.generate()
  }

  const onSubmit = () => {
    const report = submitReport(payload)
    setConfirm(null)
    navigate(dailyReportPath(report.id))
  }

  const generateLabel =
    draft.phase === 'generating'
      ? '초안 만드는 중…'
      : draft.phase === 'ready'
        ? '다시 작성'
        : 'AI로 보고서 작성'

  const basis =
    draft.attachments.length > 0
      ? `활동 ${draft.includedCount}건 · 첨부 ${draft.attachments.length}건 기준`
      : `활동 ${draft.includedCount}건 기준`

  return (
    <section>
      <h1 className="sr-only">{kind}업무보고 작성</h1>

      <header className={styles.head}>
        <Link className={styles.back} to={ROUTES.DAILY}>
          <ChevronLeftIcon />
          업무 보고
        </Link>

        <label className={styles.dateField}>
          <span>보고 일자</span>
          <input
            type="date"
            value={dateISO}
            max={TODAY_ISO}
            onChange={(event) => onDateInput(event.target.value)}
          />
        </label>

        <p className={styles.template}>{draft.template.name}</p>

        <div className={styles.headActions}>
          <Button
            variant="outline"
            type="button"
            onClick={() => {
              draft.reset()
              setSaved(false)
            }}
          >
            초안 다시 불러오기
          </Button>
          <Button
            variant="outline"
            type="button"
            onClick={() => {
              saveDraft(payload)
              setSaved(true)
            }}
          >
            임시저장
          </Button>
        </div>
      </header>

      {saved && <p className={styles.saved}>임시저장했습니다. 목록에서 이어서 쓸 수 있습니다.</p>}

      {locked && (
        <p className={styles.locked}>
          {fmtDot(parseISO(dateISO))} 보고서는 이미 제출했습니다.{' '}
          <Link to={dailyReportPath(existing.id)}>제출한 보고서 열기</Link>
        </p>
      )}

      <div className={styles.layout}>
        <div className={styles.col}>
          <article className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>활동 내역</h2>
              <span className={styles.pill}>{draft.includedCount}건 선택</span>
            </div>
            <p className={styles.panelNote}>
              캘린더와 미팅보고서에서 자동으로 불러왔습니다. 체크를 풀면 보고서에서 빠집니다.
            </p>

            <ActivityList
              activities={draft.activities}
              onToggle={draft.toggleActivity}
              onRemove={draft.removeActivity}
              onAdd={draft.addManual}
            />
          </article>

          <article className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>첨부 자료</h2>
              <span className={styles.pill}>선택 사항</span>
            </div>

            <AttachmentPanel
              attachments={draft.attachments}
              onAttach={draft.attach}
              onRemove={draft.removeAttachment}
            />
          </article>

          {/* 주간·월간 양식은 AI 가 채우는 항목이 없어 초안 생성이 없습니다. */}
          {draft.hasAiFields && (
            <div className={styles.generate}>
              <Button
                type="button"
                onClick={onGenerate}
                disabled={!draft.canGenerate || draft.phase === 'generating'}
              >
                {generateLabel}
              </Button>
              <p className={styles.basis}>
                {draft.canGenerate ? basis : '활동을 1건 이상 선택하세요.'}
              </p>
              {draft.analyzingCount > 0 && (
                <p className={styles.hint}>
                  분석 중인 첨부 {draft.analyzingCount}건은 이번 초안에서 빠집니다.
                </p>
              )}
              {draft.staleAttachments && draft.phase === 'ready' && (
                <p className={styles.hint}>
                  새로 분석된 자료가 있습니다. 다시 작성하면 반영됩니다.
                </p>
              )}
            </div>
          )}
        </div>

        <div className={styles.col}>
          <article className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>보고 내용</h2>
            </div>
            <p className={styles.panelNote}>
              {draft.template.owner}이 지정한 양식 · 항목 {draft.template.fields.length}개
            </p>

            {draft.hasAiFields && draft.phase === 'idle' && (
              <div className={styles.blank}>
                <p>왼쪽 활동을 확인한 뒤 “AI로 보고서 작성”을 누르세요.</p>
                <p className={styles.blankSub}>
                  첨부가 없어도 캘린더 일정만으로 초안이 만들어집니다.
                </p>
              </div>
            )}

            {draft.phase === 'generating' && (
              <div className={styles.blank}>
                <p>활동 내역을 정리하고 있습니다…</p>
              </div>
            )}

            {(!draft.hasAiFields || draft.phase === 'ready' || draft.phase === 'submitted') && (
              <ReportFields
                template={draft.template}
                values={draft.values}
                aiFilledIds={draft.aiFilledIds}
                onChange={draft.setValue}
              />
            )}
          </article>

          <article className={styles.panel}>
            <label className={styles.approverField}>
              <span>보고 대상</span>
              <select value={approver} onChange={(event) => setApprover(event.target.value)}>
                {APPROVERS.map((name) => (
                  <option key={name}>{name}</option>
                ))}
              </select>
            </label>

            <p className={draft.missing.length > 0 ? styles.missing : styles.okay}>
              {draft.missing.length > 0
                ? `제출 전 확인: ${draft.missing.join(', ')}`
                : `제출 가능 · 활동 ${draft.includedCount}건 포함`}
            </p>

            <Button
              type="button"
              className={styles.submit}
              disabled={draft.missing.length > 0 || locked}
              onClick={() => setConfirm({ kind: 'submit' })}
            >
              팀장에게 제출
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
                  draft.generate()
                }}
              >
                다시 작성
              </Button>
            </>
          }
        >
          <p>
            지금까지 {draft.dirtyIds.size}개 항목을 직접 고쳤습니다. 고친 항목은 유지되고 나머지만
            새로 만들어집니다.
          </p>
        </Modal>
      )}

      {confirm?.kind === 'date' && (
        <Modal
          title="보고 일자를 바꿀까요?"
          description="다른 날짜로 옮기면 그날 일정으로 활동을 다시 모으고 작성 중인 내용은 사라집니다."
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
                날짜 바꾸기
              </Button>
            </>
          }
        >
          <p>{fmtDot(parseISO(confirm.next))} 보고서로 옮깁니다.</p>
        </Modal>
      )}

      {confirm?.kind === 'submit' && (
        <Modal
          title="보고서를 제출할까요?"
          description="제출하면 보고 대상에게 검토 요청이 갑니다."
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="outline" type="button" onClick={() => setConfirm(null)}>
                취소
              </Button>
              <Button type="button" onClick={onSubmit}>
                제출
              </Button>
            </>
          }
        >
          <p>
            {fmtDot(parseISO(dateISO))} · 활동 {draft.includedCount}건 · 보고 대상 {approver}
          </p>
        </Modal>
      )}
    </section>
  )
}

// 업무보고 작성 화면. 일일·주간·월간이 한 화면을 나눠 씁니다.
//
// 왼쪽은 "무엇을 근거로 쓰는지", 오른쪽은 "무엇을 낼지"입니다. 왼쪽에 오는 자료가
// 종류마다 다릅니다. 일일은 그날 일정과 미팅보고서, 주간은 그 주의 일일보고서,
// 월간은 그 달의 주간보고서입니다(useDailyDraft → sources.ts).
import { useCallback, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import AttachmentPanel from '@/components/AttachmentPanel'
import Button, { buttonClass } from '@/components/Button'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import ReportFields from '@/components/ReportFields'
import { APPROVERS } from '@/shared/reports'
import { dailyComposePath, dailyReportPath, ROUTES } from '@/constants/routes'
import type { ReportKind } from '@/types'
import { fmtDot, parseISO, TODAY_ISO } from '@/utils/date'

import ActivityList from './components/ActivityList'
import ReportStatusBadge from './components/ReportStatusBadge'
import { PERIOD_KIND, periodLabelFor, periodStart, toPeriod } from './periods'
import useDailyDraft from './useDailyDraft'
import useDailyReports from './useDailyReports'

import styles from './Compose.module.scss'

/** 확인이 필요한 세 갈래. 셋 다 "쓰던 걸 버려도 되나"를 묻습니다. */
type Confirm = { kind: 'regenerate' } | { kind: 'date'; next: string } | { kind: 'submit' } | null

/** 종류마다 무엇을 고르는 화면인지. 문구가 갈리는 자리를 여기 모읍니다. */
const COPY: Record<
  ReportKind,
  { dateLabel: string; panel: string; note: string; empty: string; cta: string; to: string }
> = {
  일일: {
    dateLabel: '보고 일자',
    panel: '활동 내역',
    note: '그날 일정과 확정한 미팅보고서를 모았습니다. 체크를 풀면 보고서에서 빠집니다.',
    empty: '이 날짜에는 일정도 미팅 기록도 없습니다.',
    cta: '캘린더에서 일정 보기',
    to: ROUTES.CALENDAR,
  },
  주간: {
    dateLabel: '기준 주',
    panel: '일일업무보고서',
    note: '제출한 일일보고서만 고를 수 있습니다. 고른 것만 초안과 보고서에 들어갑니다.',
    empty: '이 주에 제출된 일일업무보고서가 없습니다.',
    cta: '일일업무보고서 작성하기',
    to: dailyComposePath(TODAY_ISO, '일일'),
  },
  월간: {
    dateLabel: '기준 월',
    panel: '주간업무보고서',
    note: '제출한 주간보고서만 고를 수 있습니다. 고른 것만 초안과 보고서에 들어갑니다.',
    empty: '이 달에 제출된 주간업무보고서가 없습니다.',
    cta: '주간업무보고서 작성하기',
    to: dailyComposePath(TODAY_ISO, '주간'),
  },
}

export default function Compose() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  // ?kind= 는 기간 탭(?tab=)과 같은 어휘를 씁니다. 없으면 일일보고입니다.
  const kind = PERIOD_KIND[toPeriod(params.get('kind'))] ?? '일일'
  // 주·월은 아무 날짜로 들어와도 그 기간의 첫날 하나로 봅니다. 같은 주에 보고서가
  // 둘 생기지 않는 것도, 이어서 쓰는 것도 이 값이 같은지로 갈립니다.
  const dateISO = periodStart(kind, params.get('date') ?? TODAY_ISO)
  const pickId = params.get('pick') ?? undefined

  const draft = useDailyDraft(dateISO, kind, { pickId })
  const { submitReport, saveDraft, pending, error, reload } = useDailyReports()
  const loadError = draft.error ?? error

  const [confirm, setConfirm] = useState<Confirm>(null)
  const [saved, setSaved] = useState(false)

  const copy = COPY[kind]
  const periodLabel = periodLabelFor(kind, dateISO)
  const existing = draft.existing
  const locked = existing?.status === '검토 대기' || existing?.status === '확정'
  // 아직 오지 않은 기간은 쓸 것이 없습니다. 주소를 직접 쳐도 막습니다.
  const isFuture = dateISO > TODAY_ISO

  const hasWork = draft.phase !== 'idle' || draft.dirtyIds.size > 0

  const payload = {
    date: dateISO,
    kind,
    approver: draft.approver,
    values: draft.values,
    activities: draft.activities,
    template: draft.template,
    attachments: draft.attachments,
  }

  // 기간만 바꿉니다. 종류(?kind=)는 그대로 두어야 양식이 바뀌지 않습니다.
  const changeDate = useCallback(
    (next: string) => {
      const query = new URLSearchParams(params)
      // 미리 골라 둔 자료는 그 날짜의 것이라 함께 버립니다.
      query.delete('pick')
      if (next === TODAY_ISO) query.delete('date')
      else query.set('date', next)
      setParams(query, { replace: true })
    },
    [params, setParams],
  )

  const onDateInput = (next: string) => {
    if (next === '' || periodStart(kind, next) === dateISO) return
    // 쓰던 내용은 기간이 바뀌면 사라집니다. 먼저 물어봅니다.
    if (hasWork) {
      setConfirm({ kind: 'date', next })
      return
    }
    changeDate(next)
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

  const onSubmit = async () => {
    try {
      const report = await submitReport(payload)
      setConfirm(null)
      navigate(dailyReportPath(report.id))
    } catch {
      // 훅이 같은 화면에 오류를 표시합니다.
    }
  }

  const generateLabel =
    draft.phase === 'generating'
      ? '초안 만드는 중…'
      : draft.phase === 'ready'
        ? '다시 작성'
        : 'AI로 보고서 작성'

  const basis =
    draft.attachments.length > 0
      ? `자료 ${draft.includedCount}건 · 첨부 ${draft.attachments.length}건 기준`
      : `자료 ${draft.includedCount}건 기준`

  if (isFuture) {
    return (
      <section>
        <h1 className="sr-only">{kind}업무보고 작성</h1>
        <header className={styles.head}>
          <Link className={styles.back} to={ROUTES.DAILY}>
            <ChevronLeftIcon />
            업무 보고
          </Link>
        </header>
        <div className={styles.blank}>
          <p>아직 오지 않은 기간입니다. 지난 기간의 보고서만 쓸 수 있습니다.</p>
          <Link
            className={buttonClass({ variant: 'outline' }, styles.blankCta)}
            to={dailyComposePath(TODAY_ISO, kind)}
          >
            이번 {kind}보고서로 이동
            <ChevronRightIcon />
          </Link>
        </div>
      </section>
    )
  }

  return (
    <section>
      <h1 className="sr-only">{kind}업무보고 작성</h1>

      <header className={styles.head}>
        <Link className={styles.back} to={ROUTES.DAILY}>
          <ChevronLeftIcon />
          업무 보고
        </Link>

        <label className={styles.dateField}>
          <span>{copy.dateLabel}</span>
          {kind === '월간' ? (
            <input
              type="month"
              value={dateISO.slice(0, 7)}
              max={TODAY_ISO.slice(0, 7)}
              onChange={(event) => event.target.value && onDateInput(`${event.target.value}-01`)}
            />
          ) : (
            <input
              type="date"
              value={dateISO}
              max={TODAY_ISO}
              onChange={(event) => onDateInput(event.target.value)}
            />
          )}
        </label>

        {periodLabel && <p className={styles.period}>{periodLabel}</p>}

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
            disabled={pending}
            onClick={async () => {
              try {
                await saveDraft(payload)
                setSaved(true)
              } catch {
                setSaved(false)
              }
            }}
          >
            {pending ? '저장 중…' : '임시저장'}
          </Button>
        </div>
      </header>

      {loadError && (
        <p className={styles.locked} role="alert">
          {loadError}{' '}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              draft.reload()
              reload()
            }}
          >
            다시 시도
          </Button>
        </p>
      )}
      {!loadError && draft.loading && <p role="status">보고서 자료를 불러오는 중입니다.</p>}

      {saved && <p className={styles.saved}>임시저장했습니다. 목록에서 이어서 쓸 수 있습니다.</p>}

      {/* 이미 있는 보고서는 덮어쓰지 않고 이어서 씁니다. 낸 뒤라면 잠급니다. */}
      {existing && !locked && (
        <p className={styles.saved}>
          이 기간에 {existing.status}인 보고서가 있어 이어서 씁니다. 새 보고서를 만들지 않습니다.
        </p>
      )}

      {locked && existing && (
        <p className={styles.locked}>
          {periodLabel ?? fmtDot(parseISO(dateISO))} 보고서는 이미 제출했습니다 · {existing.status}.{' '}
          <Link to={dailyReportPath(existing.id)}>제출한 보고서 열기</Link>
        </p>
      )}

      <div className={styles.layout}>
        <div className={styles.col}>
          <article className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>{copy.panel}</h2>
              <span className={styles.pill}>{draft.includedCount}건 선택</span>
            </div>
            <p className={styles.panelNote}>{copy.note}</p>

            {draft.activities.length === 0 ? (
              <div className={styles.blank}>
                <p>{copy.empty}</p>
                <Link className={buttonClass({ variant: 'outline' }, styles.blankCta)} to={copy.to}>
                  {copy.cta}
                  <ChevronRightIcon />
                </Link>
              </div>
            ) : (
              <ActivityList
                activities={draft.activities}
                // 주간·월간은 제출된 보고서만 자료로 씁니다. 직접 적을 것이 없습니다.
                canAdd={kind === '일일'}
                renderAside={(item) => {
                  const meta = draft.meta.get(item.id)
                  if (!meta) return null
                  return (
                    <>
                      {meta.tracked && <ReportStatusBadge status={meta.status} />}
                      {meta.to && meta.label && <Link to={meta.to}>{meta.label}</Link>}
                    </>
                  )
                }}
                onToggle={draft.toggleActivity}
                onRemove={draft.removeActivity}
                onAdd={draft.addManual}
              />
            )}

            {/* 아직 고를 수 없는 자리. 왜 목록이 짧은지 여기서 읽힙니다. */}
            {draft.pending.length > 0 && (
              <div className={styles.pending}>
                <h3>고를 수 없는 자료 {draft.pending.length}건</h3>
                <ul>
                  {draft.pending.map((item) => (
                    <li key={item.key}>
                      <span className={styles.pendingTitle}>{item.title}</span>
                      <ReportStatusBadge status={item.status} />
                      <Link to={item.to}>{item.action}</Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </article>

          <article className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>첨부 자료</h2>
              <span className={styles.pill}>선택 사항</span>
            </div>

            <AttachmentPanel attachments={draft.attachments} readOnly />
          </article>

          {/* AI 가 채우는 항목이 없는 양식에서는 초안 생성이 없습니다. */}
          {draft.hasAiFields && (
            <div className={styles.generate}>
              <Button
                type="button"
                onClick={onGenerate}
                disabled={pending || locked || !draft.canGenerate || draft.phase === 'generating'}
              >
                {generateLabel}
              </Button>
              <p className={styles.basis}>
                {draft.canGenerate ? basis : '자료를 1건 이상 선택하세요.'}
              </p>
              {draft.generationError && (
                <p className={styles.missing} role="alert">
                  {draft.generationError}
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
              {draft.template.owner ? `${draft.template.owner} 지정` : '기본 화면'} 양식 · 항목{' '}
              {draft.template.fields.length}개
            </p>

            {draft.hasAiFields && draft.phase === 'idle' && (
              <div className={styles.blank}>
                <p>왼쪽 자료를 확인한 뒤 “AI로 보고서 작성”을 누르세요.</p>
                <p className={styles.blankSub}>
                  {kind === '일일'
                    ? '첨부가 없어도 캘린더 일정만으로 초안이 만들어집니다.'
                    : '고른 보고서에 적힌 내용만 모읍니다.'}
                </p>
              </div>
            )}

            {draft.phase === 'generating' && (
              <div className={styles.blank}>
                <p>고른 자료를 정리하고 있습니다…</p>
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
              <select
                value={draft.approver}
                onChange={(event) => draft.setApprover(event.target.value)}
              >
                {APPROVERS.map((name) => (
                  <option key={name}>{name}</option>
                ))}
              </select>
            </label>

            <p className={draft.missing.length > 0 ? styles.missing : styles.okay}>
              {draft.missing.length > 0
                ? `제출 전 확인: ${draft.missing.join(', ')}`
                : `제출 가능 · 자료 ${draft.includedCount}건 포함`}
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
                  void runGenerate()
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
          title={`${copy.dateLabel}를 바꿀까요?`}
          description="다른 기간으로 옮기면 자료를 다시 모으고 작성 중인 내용은 사라집니다."
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
                기간 바꾸기
              </Button>
            </>
          }
        >
          <p>
            {periodLabelFor(kind, confirm.next) ?? fmtDot(parseISO(confirm.next))} 보고서로
            옮깁니다.
          </p>
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
              <Button type="button" disabled={pending} onClick={onSubmit}>
                {pending ? '제출 중…' : '제출'}
              </Button>
            </>
          }
        >
          <p>
            {periodLabel ?? fmtDot(parseISO(dateISO))} · 자료 {draft.includedCount}건 · 보고 대상{' '}
            {draft.approver}
          </p>
        </Modal>
      )}
    </section>
  )
}

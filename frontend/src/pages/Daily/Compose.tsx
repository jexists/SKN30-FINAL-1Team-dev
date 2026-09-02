// 업무보고 작성 화면. 일일·주간·월간이 한 화면을 나눠 씁니다.
//
// 뼈대는 업무보고서 작성 화면(pages/Meetings/Compose.tsx)과 같습니다. 왼쪽은 "무엇을
// 근거로 쓰는지"라 놓여 있고, 오른쪽 보고서 시트만 떠 있습니다. 어느 쪽이 결과인지
// 두 화면이 같은 방식으로 말합니다.
//
// 갈리는 것은 왼쪽에 오는 자료뿐입니다. 일일은 그날 일정과 업무보고서를 체크해서 고르고,
// 주간·월간은 그 기간에 실제로 쓴 아래 보고서가 자동으로 섭니다(useDailyDraft → sources.ts).
import { useCallback, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import Button, { buttonClass } from '@/components/Button'
import DayHeader from '@/components/DayHeader'
import ErrorToast from '@/components/ErrorToast'
import { ChevronRightIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import ReportFields from '@/components/ReportFields'
import Skeleton from '@/components/Skeleton'
import { dailyComposePath, dailyReportPath, ROUTES } from '@/constants/routes'
import type { ReportKind } from '@/types'
import { fmtDot, parseISO, TODAY_ISO } from '@/utils/date'

import MeetingInputPanel from '@/pages/Meetings/components/MeetingInputPanel'

import ActivityList from './components/ActivityList'
import DailyListLink from './components/DailyListLink'
import ReportStatusBadge from './components/ReportStatusBadge'
import { kindToPeriod, PERIOD_KIND, periodLabelFor, periodStart, toPeriod } from './periods'
import useDailyDraft from './useDailyDraft'
import useDailyReports from './useDailyReports'

import styles from './Compose.module.scss'

/** 자료를 기다리는 동안 잡아 두는 목록 높이. 서너 줄쯤 들어가는 자리입니다. */
const SOURCE_LIST_H = 240

/** 확인이 필요한 세 갈래. 셋 다 "쓰던 걸 버려도 되나"를 묻습니다. */
type Confirm = { kind: 'regenerate' } | { kind: 'date'; next: string } | { kind: 'submit' } | null

/** 종류마다 무엇을 자료로 쓰는 화면인지. 문구가 갈리는 자리를 여기 모읍니다. */
const COPY: Record<ReportKind, { dateLabel: string; empty: string; cta: string; to: string }> = {
  일일: {
    dateLabel: '보고 일자',
    empty: '이 날짜에는 일정도 미팅 기록도 없습니다.',
    cta: '캘린더에서 일정 보기',
    to: ROUTES.CALENDAR,
  },
  주간: {
    dateLabel: '기준 주',
    empty: '이 주에 제출된 일일업무보고서가 없습니다.',
    cta: '일일업무보고서 작성하기',
    to: dailyComposePath(TODAY_ISO, '일일'),
  },
  월간: {
    dateLabel: '기준 월',
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
  const { submitReport, pending, error } = useDailyReports()
  const loadError = draft.error ?? error

  const [confirm, setConfirm] = useState<Confirm>(null)

  const copy = COPY[kind]
  const periodLabel = periodLabelFor(kind, dateISO)
  const existing = draft.existing
  const locked = existing?.status === '검토 대기' || existing?.status === '확정'
  // 아직 오지 않은 기간은 쓸 것이 없습니다. 주소를 직접 쳐도 막습니다.
  const isFuture = dateISO > TODAY_ISO
  // 일일만 체크해서 고릅니다. 주간·월간은 쓴 보고서가 그대로 섭니다.
  const picks = kind === '일일'

  const hasWork = draft.phase !== 'idle' || draft.dirtyIds.size > 0

  const payload = {
    reportId: existing?.id,
    version: existing?.version,
    statusCode: existing?.apiStatus,
    date: dateISO,
    kind,
    approver: draft.approver,
    values: draft.values,
    activities: draft.activities,
    template: draft.template,
    attachments: draft.attachments,
    transcript: draft.transcript,
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
      await draft.generate()
    } catch {
      // 생성 훅이 오류를 표시합니다.
    }
  }

  const onGenerate = () => {
    // 사람이 손댄 항목이 있으면 덮어써도 되는지 먼저 묻습니다.
    if (draft.phase === 'ready' && (existing || draft.dirtyIds.size > 0)) {
      setConfirm({ kind: 'regenerate' })
      return
    }
    void runGenerate()
  }

  const onSubmit = async () => {
    try {
      const report = await submitReport(payload, draft.generationRunId)
      setConfirm(null)
      navigate(dailyReportPath(report.id))
    } catch {
      // 훅이 같은 화면에 오류를 표시합니다.
    }
  }

  if (isFuture) {
    return (
      <section>
        <h1 className="sr-only">{kind}업무보고 작성</h1>
        <div className={styles.head}>
          <DailyListLink back tab={kindToPeriod(kind)} className={styles.back} />
        </div>
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
    <section className={styles.page}>
      <h1 className="sr-only">{kind}업무보고 작성</h1>

      {/*
        머리말 한 줄. 왼쪽은 나가는 길, 오른쪽은 이 문서를 종이로 뽑는 길입니다.
        업무보고서 작성 화면과 같은 자리, 같은 모양입니다.
      */}
      <div className={styles.head}>
        <DailyListLink back tab={kindToPeriod(kind)} className={styles.back} />

        <Button
          variant="outline"
          type="button"
          disabled={draft.phase === 'idle'}
          onClick={() => window.print()}
        >
          PDF 다운로드
        </Button>
      </div>

      <ErrorToast message={loadError} onRetry={draft.reload} />

      {/* 이미 있는 보고서는 덮어쓰지 않고 이어서 씁니다. 낸 뒤라면 잠급니다. */}
      {existing && !locked && (
        <p className={styles.saved}>
          이 기간에 {existing.status}인 보고서가 있어 이어서 씁니다. 새 보고서를 만들지 않습니다.
        </p>
      )}

      {existing?.reviewNote && (
        <div className={styles.review} role="note">
          <strong>반려 사유</strong>
          <p>{existing.reviewNote}</p>
        </div>
      )}

      {locked && existing && (
        <p className={styles.locked}>
          {periodLabel ?? fmtDot(parseISO(dateISO))} 보고서는 이미 제출했습니다 · {existing.status}.{' '}
          <Link to={dailyReportPath(existing.id)}>제출한 보고서 열기</Link>
        </p>
      )}

      <div className={styles.layout}>
        <div className={styles.side}>
          <article className={styles.reference}>
            {/*
              날짜가 이 카드의 머리말입니다. 주간·월간은 하루가 아니라 덮는 기간을 세우고,
              누르면 그 단위의 달력(주는 날짜, 월은 월)이 열립니다.
            */}
            <DayHeader
              dateISO={dateISO}
              label={periodLabel}
              pickerType={kind === '월간' ? 'month' : 'date'}
              maxISO={TODAY_ISO}
              onDateChange={onDateInput}
            >
              <span className={styles.pill}>
                {picks ? `${draft.includedCount}건 선택` : `${draft.activities.length}건`}
              </span>
            </DayHeader>

            {draft.loading ? (
              // 아직 자료를 받아 오는 중입니다. 여기서 .blank 를 먼저 보여 주면
              // "고를 자료가 없다" 고 잘못 읽힙니다.
              <div role="status">
                <span className="sr-only">보고서 자료를 불러오는 중입니다.</span>
                <Skeleton height={SOURCE_LIST_H} radius="var(--r-md)" />
              </div>
            ) : draft.activities.length === 0 ? (
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
                disabled={draft.recovering}
                // 주간·월간은 제출된 보고서가 그대로 실립니다. 고를 것도,
                // 그래서 체크 모양도 없습니다.
                readOnly={!picks}
                showMark={picks}
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
              />
            )}
          </article>

          {/*
            넣는 것을 모은 면. 업무보고서 작성 화면과 같은 판을 그대로 씁니다 —
            첨부도, 직접 적는 칸도, 누르는 버튼도 두 화면에서 같은 것이어야 합니다.
            AI 가 채우는 항목이 없는 양식에서는 초안 생성이 없어 판도 서지 않습니다.
          */}
          {draft.hasAiFields && (
            <div className={styles.input}>
              <MeetingInputPanel
                attachments={draft.attachments}
                onAttach={(files) => void draft.addAttachments(files)}
                onRemoveAttachment={draft.removeAttachment}
                attachmentError={draft.attachmentError}
                transcript={draft.transcript}
                onTranscriptChange={draft.setTranscript}
                contentLabel={`${kind}보고 내용 (선택)`}
                canGenerate={draft.canGenerate}
                generating={draft.phase === 'generating'}
                // 다시 만드는 버튼이 따로 없습니다. 이 자리 하나로 처음도 다시도 누릅니다.
                disabled={locked || pending || draft.recovering}
                onGenerate={onGenerate}
              />
            </div>
          )}
        </div>

        {/* 화면에서 유일하게 떠 있는 면. 그것만으로 "내는 것은 여기" 가 전달됩니다. */}
        <div className={styles.work}>
          <article className={styles.sheet}>
            {/* 만들지 못했을 때. 결과가 나왔어야 할 자리에서 이유를 알립니다. */}
            {draft.generationError && draft.phase !== 'generating' && (
              <p className={styles.failed} role="alert">
                {draft.generationError}
              </p>
            )}

            {draft.hasAiFields && draft.phase === 'idle' ? (
              <div className={styles.sheetBlank}>
                <h2>아직 보고서가 작성되지 않았습니다</h2>
                <p>왼쪽 자료를 확인한 뒤 ‘AI 보고서 작성’을 누르세요. 직접 써도 됩니다.</p>
                <Button
                  variant="outline"
                  type="button"
                  disabled={locked || draft.recovering}
                  onClick={() => draft.setPhase('ready')}
                >
                  직접 작성하기
                </Button>
              </div>
            ) : draft.phase === 'generating' ? (
              <div className={styles.sheetBlank}>
                <p>고른 자료를 정리하고 있습니다…</p>
              </div>
            ) : (
              <>
                <ReportFields
                  template={draft.template}
                  values={draft.values}
                  aiFilledIds={draft.aiFilledIds}
                  readOnly={locked || draft.recovering}
                  onChange={draft.setValue}
                />

                {/* 제출을 막는 이유만 답니다. 낼 수 있을 때는 버튼이 스스로 말합니다. */}
                {draft.missing.length > 0 && (
                  <p className={styles.missing}>제출 전 확인: {draft.missing.join(', ')}</p>
                )}
              </>
            )}
          </article>

          <div className={styles.actions}>
            <Button
              type="button"
              className={styles.submit}
              disabled={
                draft.missing.length > 0 ||
                locked ||
                pending ||
                draft.phase === 'idle' ||
                draft.phase === 'generating' ||
                draft.recovering
              }
              onClick={() => setConfirm({ kind: 'submit' })}
            >
              보고서 제출
            </Button>
          </div>
        </div>
      </div>

      {draft.pendingRecovery && (
        <Modal
          title="이전에 생성하던 후보를 복구할까요?"
          description="복구하면 당시 자료 선택·첨부·직접 입력과 생성 결과가 현재 보고서 위에 올라옵니다."
          onClose={draft.discardPendingRecovery}
          footer={
            <>
              <Button variant="outline" type="button" onClick={draft.discardPendingRecovery}>
                현재 내용 유지
              </Button>
              <Button type="button" onClick={draft.acceptPendingRecovery}>
                후보 복구
              </Button>
            </>
          }
        >
          <p>사용자가 복구를 선택하기 전까지 저장된 보고서 내용은 바뀌지 않습니다.</p>
        </Modal>
      )}

      {confirm?.kind === 'regenerate' && (
        <Modal
          title="직접 고친 내용을 덮어쓸까요?"
          description="AI가 채우는 항목은 새 결과로 바뀝니다. 직접 입력 전용 항목은 유지됩니다."
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
            {existing
              ? '저장된 보고서의 AI 작성 항목이 새 후보로 바뀝니다.'
              : `지금까지 ${draft.dirtyIds.size}개 항목을 직접 고쳤습니다. AI 작성 항목의 수정 내용이 새 후보로 바뀝니다.`}
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
            {periodLabel ?? fmtDot(parseISO(dateISO))} · 자료 {draft.includedCount}건
          </p>
        </Modal>
      )}
    </section>
  )
}

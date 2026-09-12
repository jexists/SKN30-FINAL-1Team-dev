// 기간 보고서 작성. 생성 당시 하위 보고서 참조를 최종 제출까지 보존합니다.
import { useCallback, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import Button, { buttonClass } from '@/components/Button'
import AttachmentPanel from '@/components/AttachmentPanel'
import DayHeader from '@/components/DayHeader'
import ErrorToast from '@/components/ErrorToast'
import FormField from '@/components/FormField'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  InfoIcon,
  RefreshIcon,
} from '@/components/icons'
import Modal from '@/components/Modal'
import ReportFields from '@/components/ReportFields'
import Skeleton from '@/components/Skeleton'
import Tabs from '@/components/Tabs'
import { dailyComposePath, dailyReportPath } from '@/constants/routes'
import { reportTextLength } from '@/shared/reports'
import type { ReportKind } from '@/types'
import { fmtDot, parseISO, TODAY_ISO } from '@/utils/date'

import ActivityList from './components/ActivityList'
import DailyListLink from './components/DailyListLink'
import ReportStatusBadge from './components/ReportStatusBadge'
import { kindToPeriod, PERIOD_KIND, periodLabelFor, periodStart, toPeriod } from './periods'
import useDailyDraft from './useDailyDraft'
import useDailyReports from './useDailyReports'

import styles from './Compose.module.scss'

/** 자료를 기다리는 동안 잡아 두는 목록 높이. 서너 줄쯤 들어가는 자리입니다. */
const SOURCE_LIST_H = 240

/** 확인이 필요한 네 갈래. 앞의 셋은 "쓰던 걸 버려도 되나", 마지막은 "빠뜨려도 되나"를 묻습니다. */
type Confirm =
  | { kind: 'regenerate' }
  | { kind: 'date'; next: string }
  | { kind: 'submit' }
  | { kind: 'unwritten' }
  | null

const DATE_LABEL: Record<ReportKind, string> = {
  일일: '보고 일자를',
  주간: '기준 주를',
  월간: '기준 월을',
}

export default function Compose() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  // ?kind= 는 기간 탭(?tab=)과 같은 어휘를 씁니다. 없으면 일일보고입니다.
  const kind = PERIOD_KIND[toPeriod(params.get('kind'))] ?? '일일'
  // 주·월은 아무 날짜로 들어와도 그 기간의 첫날 하나로 봅니다. 같은 주에 보고서가
  // 둘 생기지 않는 것도, 이어서 쓰는 것도 이 값이 같은지로 갈립니다.
  const dateISO = periodStart(kind, params.get('date') ?? TODAY_ISO)

  const draft = useDailyDraft(dateISO, kind)
  const { submitReport, pending, error } = useDailyReports()
  const loadError = draft.error ?? error

  const [confirm, setConfirm] = useState<Confirm>(null)
  // 미팅 작성 화면과 같은 손잡이입니다. 보고서만 넓게 볼 때 자료 열을 접습니다.
  const [sideCollapsed, setSideCollapsed] = useState(false)
  // 관련 보고서 목록에서 지금 보고 있는 묶음. 생성에 쓰이는 쪽을 먼저 세웁니다.
  const [refTab, setRefTab] = useState<'written' | 'unwritten'>('written')

  const sourceKind = kind === '일일' ? '미팅' : kind === '주간' ? '일일' : '주간'
  const periodLabel = periodLabelFor(kind, dateISO)
  const existing = draft.existing
  const locked = existing?.status === '확정'
  // 아직 오지 않은 기간은 쓸 것이 없습니다. 주소를 직접 쳐도 막습니다.
  const isFuture = dateISO > TODAY_ISO

  const hasWork = draft.phase !== 'idle' || draft.dirtyIds.size > 0 || draft.transcript.length > 0
  // 생성 버튼이 머리말에 서므로 '지금 만들 수 있는가'와 '이미 만든 것이 있는가'를 한 곳에서 봅니다.
  const generating = draft.phase === 'generating'
  const busy = locked || pending || draft.recovering || generating
  const hasDraftContent = draft.phase === 'ready'
  // 등록 단계에서는 아직 만든 것이 없습니다. 결과 자리를 비워 두지 않고 한 열만 씁니다.
  const showWork = !draft.hasAiFields || draft.phase !== 'idle'

  const payload = {
    reportId: existing?.id,
    version: existing?.version,
    statusCode: existing?.apiStatus,
    date: dateISO,
    kind,
    approver: draft.approver,
    values: draft.values,
    activities: draft.activities,
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

  // 생성에 쓰이는 줄(제출을 마친 것)과 그렇지 않은 줄을 나눠 세웁니다. 작성중은 뒤쪽입니다.
  const written = draft.activities.filter((item) => item.included)
  const unwritten = draft.activities.filter((item) => !item.included)
  const refList = refTab === 'written' ? written : unwritten
  const renderAside = (item: (typeof draft.activities)[number]) => {
    const meta = draft.meta.get(item.id)
    if (!meta) return null
    return (
      <>
        {/* 탭이 이미 말하는 상태는 줄에서 뺍니다. 검토 대기·반려처럼 탭과 다른 것만 답니다. */}
        {meta.tracked &&
          meta.status != null &&
          meta.status !== '확정' &&
          meta.status !== '작성완료' && <ReportStatusBadge status={meta.status} />}
        {/*
          쓰던 보고서를 두고 떠나지 않도록 원본은 새 창에서 엽니다.
          그래서 <Link> 가 아니라 버튼 모양의 <a target="_blank"> 입니다.
        */}
        {meta.to && (
          <a
            className={buttonClass({ variant: 'outline', size: 'sm' })}
            href={meta.to}
            target="_blank"
            rel="noopener noreferrer"
          >
            {meta.status == null ? '보고서 작성' : '보고서 확인'}
          </a>
        )}
      </>
    )
  }

  const runGenerate = async () => {
    try {
      await draft.generate()
    } catch {
      // 생성 훅이 오류를 표시합니다.
    }
  }

  const askRegenerate = () => {
    // 사람이 손댄 항목이 있으면 덮어써도 되는지 먼저 묻습니다.
    if (draft.phase === 'ready' && (existing || draft.dirtyIds.size > 0)) {
      setConfirm({ kind: 'regenerate' })
      return
    }
    void runGenerate()
  }

  const onGenerate = () => {
    // 생성에 쓰이는 것은 제출을 마친 줄뿐입니다. 남은 줄이 있으면 그 사실부터 알립니다.
    if (unwritten.length > 0) {
      setConfirm({ kind: 'unwritten' })
      return
    }
    askRegenerate()
  }

  const onSubmit = async () => {
    if (
      draft.attachmentsPending ||
      draft.recovering ||
      draft.loading ||
      draft.error ||
      draft.missing.length > 0 ||
      draft.phase !== 'ready' ||
      locked ||
      pending
    )
      return
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
    <section className={showWork ? styles.page : `${styles.page} ${styles.pageSolo}`}>
      <h1 className="sr-only">{kind}업무보고 작성</h1>

      {/*
        머리말 한 줄. 왼쪽은 나가는 길, 오른쪽은 이 문서를 종이로 뽑는 길입니다.
        업무보고서 작성 화면과 같은 자리, 같은 모양입니다.
      */}
      <div className={styles.head}>
        <DailyListLink back tab={kindToPeriod(kind)} className={styles.back} />

        {/* 가운데는 알림 자리입니다. 비어 있어도 좌우 조작부의 자리가 흔들리지 않습니다. */}
        <div className={styles.headNotice}>
          {draft.generationError && !generating && (
            <p className={styles.headNote} role="alert">
              {draft.generationError}
            </p>
          )}
        </div>

        {/* 작성 시작 지점입니다. 이미 본문이 있으면 같은 버튼이 다시 작성으로 바뀝니다. */}
        {draft.hasAiFields && (
          <div className={styles.headActions}>
            <Button
              type="button"
              variant={hasDraftContent ? 'outline' : 'primary'}
              aria-busy={generating || draft.recovering}
              disabled={busy || !draft.canGenerate}
              onClick={onGenerate}
            >
              {generating ? (
                'AI 보고서 작성 중…'
              ) : hasDraftContent ? (
                <>
                  <RefreshIcon width={16} height={16} />
                  AI 보고서 다시 작성
                </>
              ) : (
                'AI 보고서 작성'
              )}
            </Button>
          </div>
        )}
      </div>

      <ErrorToast message={loadError} onRetry={draft.reload} />

      {/* 이미 있는 보고서는 덮어쓰지 않고 이어서 씁니다. 승인 뒤에만 잠급니다. */}
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
          {/* 접으면 판째로 사라지므로 다시 펴는 손잡이만 왼쪽 레일에 남깁니다. */}
          {showWork && sideCollapsed && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              iconOnly
              className={styles.sideToggle}
              aria-expanded={false}
              aria-controls="period-compose-side"
              aria-label="관련 보고서·참고자료 펼치기"
              onClick={() => setSideCollapsed(false)}
            >
              <ChevronRightIcon width={15} height={15} />
            </Button>
          )}
          <div
            id="period-compose-side"
            className={
              sideCollapsed ? `${styles.sideContent} ${styles.collapsed}` : styles.sideContent
            }
          >
            <article className={styles.reference}>
              <h2 className={styles.inputTitle}>
                관련 보고서
                {/* 생성에 무엇이 쓰이는지는 목록 위가 아니라 카드 이름 옆에서 미리 알립니다. */}
                <span className={styles.refNote}>
                  <InfoIcon width={14} height={14} aria-hidden="true" />
                  작성 완료된 {sourceKind} 보고서만 반영됩니다.
                </span>
                {/* 접을 상대는 보고서 열입니다. 등록 단계에는 아직 없어 손잡이도 서지 않습니다. */}
                {showWork && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    iconOnly
                    className={styles.collapseAction}
                    aria-expanded
                    aria-controls="period-compose-side"
                    aria-label="관련 보고서·참고자료 접기"
                    onClick={() => setSideCollapsed(true)}
                  >
                    <ChevronLeftIcon width={15} height={15} />
                  </Button>
                )}
              </h2>
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
              />

              {draft.relatedLoading ? (
                <div role="status">
                  <span className="sr-only">관련 보고서를 불러오는 중입니다.</span>
                  <Skeleton height={SOURCE_LIST_H} radius="var(--r-md)" />
                </div>
              ) : draft.relatedError ? (
                <div className={styles.blank}>
                  <p role="alert">{draft.relatedError}</p>
                  <Button variant="outline" onClick={draft.reloadRelated}>
                    다시 시도
                  </Button>
                </div>
              ) : (
                /* 탭과 목록은 한 덩이입니다 — 사이가 벌어지면 어느 묶음을 보는 중인지 흐려집니다. */
                <div>
                  <Tabs
                    items={[
                      { value: 'written', label: '작성완료', count: written.length },
                      { value: 'unwritten', label: '미작성', count: unwritten.length },
                    ]}
                    value={refTab}
                    onChange={setRefTab}
                    label="관련 보고서 작성 상태"
                    size="sm"
                    className={styles.refTabs}
                  />
                  <ActivityList
                    activities={refList}
                    renderAside={renderAside}
                    flush
                    empty={
                      refTab === 'written'
                        ? undefined
                        : `아직 ${sourceKind} 보고서가 없는 일정이 없습니다.`
                    }
                  />
                </div>
              )}
            </article>

            {draft.hasAiFields && (
              <div className={styles.input}>
                <h2 className={styles.inputTitle}>
                  보고서 참고자료 <span>선택</span>
                </h2>
                <AttachmentPanel
                  attachments={draft.attachments}
                  onAttach={(files) => void draft.addAttachments(files)}
                  onRemove={draft.removeAttachment}
                  note={`AI는 제출된 ${sourceKind} 보고서, 첨부 참고자료, 추가 결정사항 및 메모, 현재 작성한 본문을 바탕으로 작성합니다.`}
                  readOnly={locked || pending || draft.recovering || draft.phase === 'generating'}
                />
                {draft.attachmentError && (
                  <p className={styles.failed} role="alert">
                    {draft.attachmentError}
                  </p>
                )}
                <FormField label="추가 결정사항 및 메모" error={draft.guidanceError ?? undefined}>
                  <textarea
                    id="period-report-guidance"
                    rows={4}
                    value={draft.transcript}
                    readOnly={locked || pending || draft.recovering || draft.phase === 'generating'}
                    placeholder="보고서에 추가할 결정사항, 후속 조치, 참고할 상황을 입력하세요."
                    onChange={(event) => draft.setTranscript(event.target.value)}
                  />
                  <span className={styles.guidanceMeta}>
                    {reportTextLength(draft.transcript).toLocaleString()} / 2,000자
                  </span>
                </FormField>
              </div>
            )}
          </div>
        </div>

        {/* 화면에서 유일하게 떠 있는 면. 그것만으로 "내는 것은 여기" 가 전달됩니다. */}
        {showWork && (
          <div className={styles.work}>
            <div className={styles.reports}>
              <article className={styles.sheet}>
                {draft.phase === 'generating' ? (
                  <div className={styles.sheetBlank}>
                    <p>{sourceKind} 보고서와 참고자료를 바탕으로 작성하고 있습니다…</p>
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
            </div>

            {/* 이 화면의 제출 지점입니다. 왼쪽은 종이로 뽑는 길, 오른쪽이 내는 길입니다. */}
            <div className={styles.saveBar}>
              <div className={styles.saveActions}>
                <Button
                  variant="outline"
                  type="button"
                  className={styles.pdfButton}
                  disabled={draft.phase === 'idle' || draft.phase === 'generating'}
                  onClick={() => window.print()}
                >
                  <DownloadIcon width={15} height={15} />
                  PDF 다운로드
                </Button>
                <Button
                  type="button"
                  className={styles.submit}
                  disabled={
                    draft.missing.length > 0 ||
                    locked ||
                    pending ||
                    draft.phase === 'idle' ||
                    draft.phase === 'generating' ||
                    draft.recovering ||
                    draft.attachmentsPending ||
                    draft.loading ||
                    Boolean(draft.error)
                  }
                  onClick={() => setConfirm({ kind: 'submit' })}
                >
                  보고서 제출
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {confirm?.kind === 'unwritten' && (
        <Modal
          title={`미작성 보고서가 ${unwritten.length}건 있습니다`}
          description={`작성을 마친 ${written.length}건만으로 ${kind}보고서를 작성합니다.`}
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
                  askRegenerate()
                }}
              >
                이대로 작성
              </Button>
            </>
          }
        >
          <p>
            미작성 일정은 이번 작성에 반영되지 않습니다. 먼저 쓰려면 목록에서 보고서 작성을
            누르세요.
          </p>
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
          title={`${DATE_LABEL[kind]} 바꿀까요?`}
          description="다른 기간으로 옮기면 작성 중인 내용은 사라집니다."
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
              <Button
                type="button"
                disabled={
                  pending ||
                  draft.attachmentsPending ||
                  draft.recovering ||
                  draft.missing.length > 0
                }
                onClick={onSubmit}
              >
                {pending ? '제출 중…' : '제출'}
              </Button>
            </>
          }
        >
          <p>{periodLabel ?? fmtDot(parseISO(dateISO))}</p>
        </Modal>
      )}
    </section>
  )
}

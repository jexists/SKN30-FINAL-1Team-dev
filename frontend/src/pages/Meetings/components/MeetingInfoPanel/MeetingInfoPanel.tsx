// 왼쪽 첫 번째 탭. AI 에게 준 것을 그대로 보여 줍니다.
//
// 참고 자료 열이라 카드로 띄우지 않고 hairline 으로만 나눕니다. 화면에서 떠 있는 면은
// 오른쪽 보고서 하나뿐이어야 지금 무엇을 고치는 중인지 헷갈리지 않습니다.
import { Link } from 'react-router'

import AttachmentPanel from '@/components/AttachmentPanel'
import Button from '@/components/Button'
import { ROUTES } from '@/constants/routes'
import type { AgendaItem, ReportAttachment } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'

import MeetingFacts from '../MeetingFacts'

import styles from './MeetingInfoPanel.module.scss'

interface Props {
  item: AgendaItem
  attachments: ReportAttachment[]
  transcript: string
  onTranscriptChange: (value: string) => void
  /** 'AI 보고서 작성' 을 누를 수 있는지. 미팅 내용이 있어야 누릅니다. */
  canGenerate: boolean
  generating: boolean
  /** 이미 한 번 만든 뒤인지. 버튼 글씨가 달라집니다. */
  hasAiOriginal: boolean
  disabled: boolean
  generationError: string | null
  onGenerate: () => void
  onReset: () => void
}

export default function MeetingInfoPanel({
  item,
  attachments,
  transcript,
  onTranscriptChange,
  canGenerate,
  generating,
  hasAiOriginal,
  disabled,
  generationError,
  onGenerate,
  onReset,
}: Props) {
  // 한 번 만든 뒤로 다시 만드는 일은 보고서 아래 액션 바가 맡습니다. 같은 버튼을
  // 두 군데 두면 어느 쪽을 눌러야 하는지 묻게 됩니다.
  const generateLabel = generating ? 'AI 보고서 작성 중…' : 'AI 보고서 작성'

  return (
    <div className={styles.root}>
      <section className={styles.block}>
        <MeetingFacts
          hospital={item.hospital}
          dept={item.dept}
          contact={item.contact}
          product={item.product}
          place={item.place}
          when={`${fmtDot(parseISO(item.date))} ${item.time}`}
        />

        {item.brief && <p className={styles.brief}>{item.brief}</p>}

        <p className={styles.source}>
          캘린더 일정에서 가져왔습니다. 값이 틀렸다면{' '}
          <Link to={ROUTES.CALENDAR}>캘린더에서 일정을 고치세요.</Link>
        </p>
      </section>

      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h2>첨부 자료</h2>
        </div>

        <AttachmentPanel attachments={attachments} readOnly />
      </section>

      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h2>미팅 내용</h2>
        </div>
        <p className={styles.note}>내가 적은 원본입니다. AI 는 이 내용을 보고 씁니다.</p>

        <label className="sr-only" htmlFor="transcript">
          미팅 내용 직접 입력
        </label>
        <textarea
          id="transcript"
          className={styles.transcript}
          rows={8}
          value={transcript}
          disabled={disabled}
          placeholder="누구와 무엇을 이야기했는지 그대로 적으세요."
          onChange={(event) => onTranscriptChange(event.target.value)}
        />
      </section>

      <div className={styles.foot}>
        {!hasAiOriginal && (
          <>
            <Button
              type="button"
              className={styles.generate}
              onClick={onGenerate}
              disabled={disabled || !canGenerate || generating}
            >
              {generateLabel}
            </Button>

            <p className={styles.basis}>
              {canGenerate
                ? attachments.length > 0
                  ? `첨부 ${attachments.length}건 · 미팅 내용 기준`
                  : '미팅 내용 기준'
                : '미팅 내용을 입력하면 누를 수 있습니다.'}
            </p>
          </>
        )}

        {generationError && (
          <p className={styles.error} role="alert">
            {generationError}
          </p>
        )}

        <button type="button" className={styles.reset} onClick={onReset} disabled={disabled}>
          처음부터 다시 쓰기
        </button>
      </div>
    </div>
  )
}

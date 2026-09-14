// 보고서 본문을 읽는 화면. 구획과 후속 조치가 보이는 유일한 자리입니다.
//
// 흐르는 중(GenerationProgress)·고치기 전(EditableReport)·낸 뒤(Detail) 가 모두 이것을 씁니다.
// 셋이 다르면 다 쓰이는 순간 글이 한 번 튑니다.
import ReportBody from '@/components/ReportBody'
import StatusBadge from '@/components/StatusBadge'
import { reportSections, type ReportAction } from '@/shared/reportSections'

import styles from './ReportView.module.scss'

/* 채워지지 않은 값. 사람이 이 보고서에서 가장 자주 고치는 곳이라 눈에 갈려야 합니다. */
const BLANK = /^(미확인|미지정|미정|담당 미지정|기한 미확인|완료 기준 미확인|해당사항 없음)/

function blank(value: string) {
  return BLANK.test(value.trim())
}

/* 이행이 확인된 것만 채웁니다. 근거가 없으면 빈 칸으로 두는 것이 사실입니다. */
const DONE = /^(완료|이행)/

function Action({ action }: { action: ReportAction }) {
  const status = action.fields.find((field) => field.label === '상태')
  const fulfilled = action.fields.find((field) => field.label === '이행 여부')
  const rest = action.fields.filter((field) => field !== status && field !== fulfilled)
  const done = Boolean(fulfilled && DONE.test(fulfilled.value.trim()))
  return (
    <li className={styles.action}>
      <div className={styles.actionHead}>
        {/*
          누르는 칸이 아니라 이행 여부를 읽어 그리는 표시입니다. 여기서 체크를
          바꿔도 보고서 본문은 달라지지 않으므로 조작처럼 보이게 두지 않습니다.
        */}
        <span className={done ? `${styles.check} ${styles.isDone}` : styles.check} aria-hidden />
        <span className="sr-only">이행 여부: {fulfilled?.value ?? '미확인'}</span>
        <p className={blank(action.task) ? `${styles.task} ${styles.blank}` : styles.task}>
          {action.task}
        </p>
        {/*
          합의와 요청은 같은 것이 아닙니다. 서버가 가장 조심하는 구분이므로
          (report-style: '요청을 합의로 바꾸지 않습니다') 화면에서도 갈라 둡니다.
        */}
        {status && (
          <StatusBadge
            label={status.value}
            tone={
              blank(status.value) ? 'neutral' : status.value.startsWith('합의') ? 'green' : 'blue'
            }
          />
        )}
      </div>
      {rest.length > 0 && (
        <dl className={styles.fields}>
          {rest.map((field) => (
            <div key={field.label}>
              <dt>{field.label}</dt>
              <dd className={blank(field.value) ? styles.blank : undefined}>{field.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </li>
  )
}

export default function ReportView({ body, className = '' }: { body: string; className?: string }) {
  const sections = reportSections(body)
  // 아는 꼴이 아니면 구획으로 나누지 않고 원문 그대로 그립니다. 옛 줄글 보고서와
  // 공통·미지정 평목록이 이 길입니다. 다만 본문 타이포(.text)는 구획이 있는 길과
  // 똑같이 씌웁니다 — 같은 화면에 나란히 서므로 크기가 달라지면 안 됩니다.
  if (!sections) return <ReportBody className={`${styles.text} ${className}`.trim()} body={body} />

  return (
    <div className={`${styles.root} ${className}`.trim()}>
      {sections.map((section, index) => (
        <section className={styles.section} key={`${index}-${section.heading}`}>
          {section.heading && <h3 className={styles.heading}>{section.heading}</h3>}
          {section.actions ? (
            <ul className={styles.actions}>
              {section.actions.map((action, at) => (
                <Action key={`${at}-${action.task}`} action={action} />
              ))}
            </ul>
          ) : (
            section.body && (
              <ReportBody
                className={blank(section.body) ? `${styles.text} ${styles.blank}` : styles.text}
                body={section.body}
              />
            )
          )}
        </section>
      ))}
    </div>
  )
}

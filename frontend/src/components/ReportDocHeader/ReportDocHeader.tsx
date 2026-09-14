/*
 * 보고서의 머리글. 사내 업무보고 양식의 첫머리 — 제목 한 줄과 작성자·부서·직책·작성일 표입니다.
 *
 * 인쇄용 마크업을 따로 만들지 않습니다. 화면에 보이는 이 표가 그대로 PDF 머리글이 되어야
 * 화면과 종이가 같은 문서로 읽힙니다.
 */
import type { ReactNode } from 'react'

import styles from './ReportDocHeader.module.scss'

interface Props {
  /** 예: "9월 3일 (목) 일일 업무 보고서" */
  title: string
  author: string
  jobTitle?: string
  department?: string
  company?: string
  /** 작성일. 이미 사람이 읽는 꼴로 다듬어 넘깁니다. */
  writtenOn: string
  approver?: string
  /**
   * 보고 대상을 고칠 수 있게 합니다. 넘기지 않으면 읽기 전용 칸입니다 —
   * 낸 뒤에 읽는 화면에서는 고칠 자리가 아닙니다.
   */
  onApproverChange?: (value: string) => void
}

/* 빈 칸을 줄째로 빼지 않습니다 — 칸이 사라지면 양식이 무너집니다. */
function value(text?: string) {
  return text?.trim() ? text.trim() : '미지정'
}

/*
 * 직책만 조직상 기본값이 있습니다. 팀장이 아닌 사람은 모두 팀원이므로, 계정에 직함을
 * 적어 두지 않았다고 해서 '미지정' 으로 둘 이유가 없습니다.
 */
function jobTitleValue(text?: string) {
  return text?.trim() ? text.trim() : '팀원'
}

export default function ReportDocHeader({
  title,
  author,
  jobTitle,
  department,
  company,
  writtenOn,
  approver,
  onApproverChange,
}: Props) {
  /*
   * 보고 대상만 사람이 적는 칸입니다. 고칠 수 있을 때는 칸을 비워 두고 — 아직 정하지
   * 않은 것을 '미지정' 이라고 단정하지 않습니다 — 손이 올라갈 때 배경 한 겹으로만
   * 고칠 수 있다고 알립니다. 종이에서는 안내 문구가 지워지고 적은 글만 남습니다.
   */
  const approverCell: ReactNode = onApproverChange ? (
    <input
      className={styles.input}
      type="text"
      value={approver ?? ''}
      maxLength={40}
      placeholder="보고 대상"
      aria-label="보고 대상"
      onChange={(event) => onApproverChange(event.target.value)}
    />
  ) : (
    value(approver)
  )

  const rows: [string, ReactNode][] = [
    ['작성자', value(author)],
    ['부서명', value(department)],
    ['직책', jobTitleValue(jobTitle)],
    ['작성일', value(writtenOn)],
    ['회사명', value(company)],
    ['보고 대상', approverCell],
  ]

  return (
    <header className={styles.root}>
      <h1 className={styles.title}>{title}</h1>
      <dl className={styles.meta}>
        {rows.map(([label, cell]) => (
          <div className={styles.row} key={label}>
            <dt>{label}</dt>
            <dd>{cell}</dd>
          </div>
        ))}
      </dl>
    </header>
  )
}

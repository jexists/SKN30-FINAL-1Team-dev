// 왼쪽 두 번째 탭. AI 가 최초로 만든 원본입니다.
//
// 오른쪽 최종 보고서와 같은 항목 순서·같은 라벨로 그립니다. 두 열의 "고객 반응" 이
// 눈높이에서 만나야 무엇이 달라졌는지 대조할 수 있습니다. 값은 절대 고칠 수 없습니다.
import Button from '@/components/Button'
import ReportFields from '@/components/ReportFields'
import type { ReportTemplate } from '@/types'

import styles from './AiOriginalPanel.module.scss'

interface Props {
  template: ReportTemplate
  values: Record<string, string>
  evidence?: string
  /** ISO 8601. 몇 번째 원본인지 사람이 가늠하는 유일한 단서입니다. */
  generatedAt?: string
  /** 최종 보고서에 아직 옮기지 않은 새 원본인지. */
  pending: boolean
  disabled: boolean
  onApply: () => void
}

const fmtStamp = (iso?: string) => {
  if (!iso) return ''
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ''
  const time = at.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  return `${at.getMonth() + 1}월 ${at.getDate()}일 ${time} 생성`
}

export default function AiOriginalPanel({
  template,
  values,
  evidence,
  generatedAt,
  pending,
  disabled,
  onApply,
}: Props) {
  const stamp = fmtStamp(generatedAt)

  return (
    <div className={styles.root}>
      <p className={styles.note}>
        AI가 최초 생성한 원본입니다. 오른쪽을 고쳐도 이 내용은 바뀌지 않습니다.
        {stamp && <span className={styles.stamp}>{stamp}</span>}
      </p>

      {pending && (
        <div className={styles.pending}>
          <p>새 원본이 생겼습니다. 오른쪽 최종 보고서는 아직 그대로입니다.</p>
          <Button variant="outline" size="sm" type="button" disabled={disabled} onClick={onApply}>
            새 결과 적용
          </Button>
        </div>
      )}

      <ReportFields template={template} values={values} readOnly />

      {evidence && <p className={styles.evidence}>{evidence}</p>}
    </div>
  )
}

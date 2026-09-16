// 평소에는 문서로 읽고, [수정] 을 눌러야 고칩니다.
//
// 읽는 동안 서식 단추가 떠 있으면 이 자리가 문서가 아니라 입력칸으로 읽힙니다. 그래서
// 편집기는 수정에 들어갈 때만 세웁니다. 저장 값은 양쪽 모두 같은 Markdown 한 덩어리라
// 오가는 사이에 본문이 달라질 일이 없습니다.
//
// 수정 상태와 나가는 길([취소]·[수정 완료])은 부모가 쥡니다. 한 화면에 문서가 여럿일 때
// 조작부가 문서마다 흩어지지 않고 화면에 하나만 서야 하기 때문입니다.
import { lazy, Suspense } from 'react'

import ReportView from '@/components/ReportView'

import styles from './EditableReport.module.scss'

/*
 * 편집기는 수정에 들어간 뒤에야 필요합니다. 여기서 갈라 두면 읽기만 하는 사람은 TinyMCE 를
 * 아예 내려받지 않고, 이 파일을 부르는 쪽도 브라우저 전역 없이 그릴 수 있습니다.
 */
const ReportDocument = lazy(() => import('../ReportDocument'))

interface Props {
  body: string
  /** 문서를 통째로 다시 세워야 할 때 올라갑니다. 편집 중에는 절대 바뀌지 않아야 합니다. */
  docKey: number
  disabled: boolean
  onChange: (body: string) => void
  /** 부모가 쥔 수정 상태. 잠긴 문서는 켜져 있어도 읽기로 남습니다. */
  editing: boolean
  /** 빈 본문일 때 뜨는 안내. */
  placeholder?: string
}

export default function EditableReport({
  body,
  docKey,
  disabled,
  onChange,
  editing,
  placeholder = '[수정] 을 눌러 내용을 적으세요.',
}: Props) {
  if (editing && !disabled) {
    return (
      <div className={styles.root}>
        {/* 편집기가 내려오는 동안에도 글은 그대로 보입니다. */}
        <Suspense fallback={<ReportView body={body} />}>
          <ReportDocument body={body} docKey={docKey} disabled={false} onChange={onChange} />
        </Suspense>
      </div>
    )
  }

  return (
    <div className={styles.root}>
      {body.trim() ? (
        <ReportView body={body} />
      ) : (
        <p className={styles.placeholder}>{disabled ? '기록된 내용 없음' : placeholder}</p>
      )}
    </div>
  )
}

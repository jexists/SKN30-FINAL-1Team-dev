// 평소에는 문서로 읽고, 누르면 그 자리에서 고칩니다.
//
// 읽는 동안 서식 단추가 떠 있으면 이 자리가 문서가 아니라 입력칸으로 읽힙니다. 그래서
// 편집기는 손이 닿을 때만 세웁니다. 저장 값은 양쪽 모두 같은 Markdown 한 덩어리라
// 오가는 사이에 본문이 달라질 일이 없습니다.
import { lazy, Suspense, useEffect, useRef, useState } from 'react'

import ReportView from '@/components/ReportView'

import styles from './EditableReport.module.scss'

/*
 * 편집기는 누른 뒤에야 필요합니다. 여기서 갈라 두면 읽기만 하는 사람은 TinyMCE 를
 * 아예 내려받지 않고, 이 파일을 부르는 쪽도 브라우저 전역 없이 그릴 수 있습니다.
 */
const ReportDocument = lazy(() => import('../ReportDocument'))

interface Props {
  body: string
  /** 문서를 통째로 다시 세워야 할 때 올라갑니다. 편집 중에는 절대 바뀌지 않아야 합니다. */
  docKey: number
  disabled: boolean
  onChange: (body: string) => void
  /** 빈 본문일 때 눌러 볼 자리에 뜨는 안내. */
  placeholder?: string
  'aria-label'?: string
}

export default function EditableReport({
  body,
  docKey,
  disabled,
  onChange,
  placeholder = '내용을 적으려면 누르세요.',
  'aria-label': label,
}: Props) {
  const [editing, setEditing] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  /* 누른 자리. 편집기가 선 뒤에 여기에 커서를 세워야 화면이 튀지 않습니다. */
  const point = useRef<{ x: number; y: number } | null>(null)

  /*
   * 바깥을 누르면 읽기로 돌아갑니다. blur 의 relatedTarget 은 빈 곳을 눌렀을 때 null 이라
   * 툴바와 여백을 가려내지 못합니다. 눌린 자리가 이 안인지만 봅니다.
   */
  useEffect(() => {
    if (!editing) return
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setEditing(false)
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [editing])

  useEffect(() => {
    if (disabled) setEditing(false)
  }, [disabled])

  if (editing && !disabled) {
    return (
      <div
        ref={root}
        className={styles.root}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setEditing(false)
        }}
      >
        {/* 편집기가 내려오는 동안에도 글은 그대로 보입니다. */}
        <Suspense fallback={<ReportView body={body} />}>
          <ReportDocument
            autoFocus
            body={body}
            caretAt={point.current}
            docKey={docKey}
            disabled={false}
            onChange={onChange}
          />
        </Suspense>
      </div>
    )
  }

  return (
    <div
      ref={root}
      className={disabled ? styles.root : `${styles.root} ${styles.editable}`}
      role={disabled ? undefined : 'button'}
      tabIndex={disabled ? undefined : 0}
      aria-label={disabled ? undefined : (label ?? '보고서 본문 고치기')}
      onClick={(event) => {
        if (disabled) return
        // 키보드로 들어온 클릭은 좌표가 0 입니다. 그때는 좌표 없이 열어 맨 앞에서 시작합니다.
        point.current = event.detail ? { x: event.clientX, y: event.clientY } : null
        setEditing(true)
      }}
      onKeyDown={(event) => {
        if (disabled) return
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          point.current = null
          setEditing(true)
        }
      }}
    >
      {body.trim() ? (
        <ReportView body={body} />
      ) : (
        <p className={styles.placeholder}>{disabled ? '기록된 내용 없음' : placeholder}</p>
      )}
    </div>
  )
}

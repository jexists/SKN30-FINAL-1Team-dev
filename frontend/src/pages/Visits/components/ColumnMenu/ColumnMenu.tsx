// 컬럼 헤더의 ⋯ 메뉴입니다. 이름·색을 바꾸고 컬럼을 더하거나 지웁니다.
//
// 이름 바꾸기를 별도 모달로 띄우지 않고 여기 입력칸을 둡니다. 한 글자 고치려고
// 화면을 덮을 일은 아닙니다.
import { useEffect, useState } from 'react'

import Popover from '@/components/Popover'
import type { ColumnTone } from '@/types'

import { TONE_LABEL, TONES, type BoardColumn } from '../../board'

import styles from './ColumnMenu.module.scss'

interface Props {
  column: BoardColumn
  /** 카드를 옮길 후보. 자기 자신은 빠져 있습니다. */
  others: BoardColumn[]
  cardCount: number
  onRename: (name: string) => void
  onRecolor: (tone: ColumnTone) => void
  onAddAfter: () => void
  onRemove: (moveToId: string) => void
}

export default function ColumnMenu({
  column,
  others,
  cardCount,
  onRename,
  onRecolor,
  onAddAfter,
  onRemove,
}: Props) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(column.name)
  const [moveTo, setMoveTo] = useState(others[0]?.id ?? '')

  // 다른 곳에서 이름이 바뀌었거나 메뉴를 다시 열었을 때 입력칸을 맞춰 둡니다.
  useEffect(() => {
    if (open) setName(column.name)
  }, [open, column.name])

  useEffect(() => {
    if (others.length > 0 && !others.some((col) => col.id === moveTo)) setMoveTo(others[0].id)
  }, [others, moveTo])

  const commitName = () => {
    const next = name.trim()
    if (next !== '' && next !== column.name) onRename(next)
    else setName(column.name)
  }

  return (
    <Popover
      open={open}
      onClose={() => setOpen(false)}
      align="end"
      label={`${column.name} 컬럼 설정`}
      trigger={
        <button
          type="button"
          className={styles.trigger}
          aria-label={`${column.name} 컬럼 설정`}
          aria-expanded={open}
          onClick={() => setOpen((prev) => !prev)}
        >
          ⋯
        </button>
      }
    >
      <div className={styles.panel}>
        <label className={styles.field}>
          <span className={styles.label}>이름</span>
          <input
            className={styles.input}
            value={name}
            onChange={(event) => setName(event.target.value)}
            onBlur={commitName}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                commitName()
              }
            }}
          />
        </label>

        <div className={styles.field}>
          <span className={styles.label}>색</span>
          <div className={styles.tones}>
            {TONES.map((tone) => (
              <button
                key={tone}
                type="button"
                className={[styles.tone, styles[tone], tone === column.tone && styles.isOn]
                  .filter(Boolean)
                  .join(' ')}
                aria-label={TONE_LABEL[tone]}
                aria-pressed={tone === column.tone}
                onClick={() => onRecolor(tone)}
              />
            ))}
          </div>
        </div>

        <button
          type="button"
          className={styles.action}
          onClick={() => {
            onAddAfter()
            setOpen(false)
          }}
        >
          오른쪽에 컬럼 추가
        </button>

        <div className={styles.remove}>
          {others.length === 0 ? (
            <p className={styles.hint}>마지막 컬럼이라 지울 수 없습니다.</p>
          ) : (
            <>
              {cardCount > 0 && (
                <label className={styles.field}>
                  <span className={styles.label}>남은 {cardCount}건을 옮길 곳</span>
                  <select
                    className={styles.input}
                    value={moveTo}
                    onChange={(event) => setMoveTo(event.target.value)}
                  >
                    {others.map((col) => (
                      <option key={col.id} value={col.id}>
                        {col.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <button
                type="button"
                className={`${styles.action} ${styles.danger}`}
                onClick={() => {
                  onRemove(moveTo)
                  setOpen(false)
                }}
              >
                컬럼 삭제
              </button>
            </>
          )}
        </div>
      </div>
    </Popover>
  )
}

// 컬럼 표시·순서·폭은 사람마다 다르게 맞춰 두고 계속 씁니다.
// AppShell 의 사이드바 접힘과 같은 방식으로 localStorage 에 남깁니다.
import { useCallback, useState } from 'react'

import { ALL_COLUMNS, COLUMN_BY_ID, DEFAULT_VISIBLE } from './columns'

const KEY = 'salesluv.customers.columns.v4'

export interface ColumnPrefs {
  order: string[]
  visible: string[]
  widths: Record<string, number>
}

const defaults = (): ColumnPrefs => ({
  order: ALL_COLUMNS.map((c) => c.id),
  visible: [...DEFAULT_VISIBLE],
  widths: {},
})

function read(): ColumnPrefs {
  const base = defaults()
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return base
    const saved = JSON.parse(raw) as Partial<ColumnPrefs>

    // 저장된 뒤에 컬럼이 추가·삭제됐을 수 있어 항상 현재 정의와 맞춥니다.
    const savedOrder = (saved.order ?? []).filter((id) => COLUMN_BY_ID.has(id))
    const merged = [...savedOrder, ...base.order.filter((id) => !savedOrder.includes(id))]
    // 고정 컬럼이 바뀐 뒤 저장값이 남아 있으면 sticky 열이 첫 자리를 벗어나 표가 깨집니다.
    const order = [
      ...merged.filter((id) => COLUMN_BY_ID.get(id)?.fixed),
      ...merged.filter((id) => !COLUMN_BY_ID.get(id)?.fixed),
    ]
    const visible = (saved.visible ?? base.visible).filter((id) => COLUMN_BY_ID.has(id))

    return {
      order,
      // 고정 컬럼은 숨길 수 없으므로 저장값이 어떻든 항상 살려 둡니다.
      visible: visible.length > 0 ? visible : base.visible,
      widths: saved.widths ?? {},
    }
  } catch {
    // 값이 깨졌거나 localStorage 가 막혔으면 기본값으로 시작합니다.
    return base
  }
}

function persist(prefs: ColumnPrefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs))
  } catch {
    // 저장에 실패해도 이번 세션 동안의 설정은 그대로 동작합니다.
  }
}

export default function useColumnPrefs() {
  const [prefs, setPrefs] = useState(read)

  const update = useCallback((patch: (prev: ColumnPrefs) => ColumnPrefs) => {
    setPrefs((prev) => {
      const next = patch(prev)
      persist(next)
      return next
    })
  }, [])

  const toggleColumn = useCallback(
    (id: string) => {
      if (COLUMN_BY_ID.get(id)?.fixed) return
      update((prev) => ({
        ...prev,
        visible: prev.visible.includes(id)
          ? prev.visible.filter((v) => v !== id)
          : [...prev.visible, id],
      }))
    },
    [update],
  )

  const moveColumn = useCallback(
    (id: string, delta: -1 | 1) => {
      // 고정 컬럼은 sticky 로 왼쪽에 붙어 있어 자리를 옮기면 표가 깨집니다.
      if (COLUMN_BY_ID.get(id)?.fixed) return
      update((prev) => {
        const from = prev.order.indexOf(id)
        const to = from + delta
        if (from < 0 || to < 0 || to >= prev.order.length) return prev
        if (COLUMN_BY_ID.get(prev.order[to])?.fixed) return prev
        const order = [...prev.order]
        ;[order[from], order[to]] = [order[to], order[from]]
        return { ...prev, order }
      })
    },
    [update],
  )

  const setWidth = useCallback(
    (id: string, width: number) => {
      update((prev) => ({ ...prev, widths: { ...prev.widths, [id]: width } }))
    },
    [update],
  )

  const reset = useCallback(() => update(defaults), [update])

  return { prefs, toggleColumn, moveColumn, setWidth, reset }
}

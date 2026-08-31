interface AiField {
  id: string
  aiFilled: boolean
}

/** 빈 초안일 때만 AI 작성 항목을 최종본에 넣고, 기존 작성본은 그대로 보존합니다. */
export function mergeGeneratedValues(
  fields: readonly AiField[],
  current: Record<string, string>,
  generated: Record<string, string>,
  applyToFinal: boolean,
) {
  const values = { ...current }
  if (applyToFinal) {
    for (const field of fields) {
      if (field.aiFilled) values[field.id] = generated[field.id] ?? ''
    }
  }
  return values
}

/** 사전저장부터 최종 자동저장까지 같은 딜의 중복 실행·편집을 막습니다. */
export async function runDealGeneration(
  active: Set<string>,
  dealId: string,
  onChange: () => void,
  generate: () => Promise<boolean>,
) {
  if (active.has(dealId)) return false
  active.add(dealId)
  onChange()
  try {
    return await generate()
  } finally {
    active.delete(dealId)
    onChange()
  }
}

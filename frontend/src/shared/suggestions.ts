// AI 추천 도메인. 시드는 mocks/ 에서 받습니다.
import { suggestionSeed } from '@/mocks'
import type { AiSuggestion } from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

export const aiSuggestions: AiSuggestion[] = suggestionSeed
  .map((seed) => ({ ...seed, date: iso(addDays(TODAY, seed.off)) }))
  .sort((a, b) => a.date.localeCompare(b.date) || a.time.localeCompare(b.time))

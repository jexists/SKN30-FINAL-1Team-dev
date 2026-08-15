// 자료실 도메인. 시드는 mocks/ 에서 받습니다.
import { documentSeed } from '@/mocks'
import type { SalesDocument, SalesDocumentSeed } from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

function toDocument(seed: SalesDocumentSeed): SalesDocument {
  return {
    ...seed,
    versions: seed.versions.map(({ uploadedOff, ...rest }) => ({
      ...rest,
      uploaded: iso(addDays(TODAY, uploadedOff)),
    })),
  }
}

export const documents: SalesDocument[] = documentSeed.map(toDocument)

import type {
  DocumentCategory,
  DocumentFile,
  DocumentFileKind,
  DocumentLink,
  SalesDocument,
} from '@/types'

export type CategoryTone = 'blue' | 'purple' | 'green' | 'orange' | 'gray'

export const DOCUMENT_CATEGORIES: DocumentCategory[] = [
  '견적서',
  '계약서',
  '발주서',
  '상품설명서',
  '기타',
]

/** 선택 칸에 그대로 넣는 목록. 분류 이름이 곧 값입니다. */
export const CATEGORY_OPTIONS = DOCUMENT_CATEGORIES.map((category) => ({
  value: category,
  label: category,
}))

export const TONE_OF: Record<DocumentCategory, CategoryTone> = {
  계약서: 'blue',
  발주서: 'purple',
  상품설명서: 'green',
  견적서: 'orange',
  기타: 'gray',
}

export const KIND_LABEL: Record<DocumentFileKind, string> = {
  pdf: 'PDF',
  doc: '문서',
  sheet: '시트',
  slide: '슬라이드',
  image: '이미지',
  etc: '파일',
}

/** 업로드 화면에서 고를 수 있는 연결. '고객사'·'발주' 는 예전 자료에만 남습니다. */
export const LINK_KINDS = ['none', '상품', '딜'] as const

/**
 * 자료실은 방 둘로 나뉩니다. 거래에 딸린 문서와 영업이 돌려 보는 자료는 쓰임이
 * 달라서, 방마다 담는 분류와 고를 수 있는 연결이 다릅니다. 목록을 가르는 실제
 * 판단은 서버가 room 파라미터로 합니다.
 */
export interface DocumentRoom {
  label: string
  /** 분류 탭에 세울 목록. 서버가 이 방에 실어 주는 분류와 같아야 합니다. */
  categories: readonly DocumentCategory[]
  /** 고를 수 있는 연결. 하나뿐이면 고르는 자리를 두지 않고 그것으로 고정합니다. */
  linkKinds: readonly DocumentLink['kind'][]
}

export const ROOMS = {
  trade: {
    label: '거래문서실',
    categories: ['견적서', '계약서', '발주서'],
    // 거래문서는 딜에 붙는 것이 곧 방 소속이라 딜 연결로 고정합니다.
    linkKinds: ['딜'],
  },
  sales: {
    label: '영업자료실',
    categories: ['상품설명서', '기타'],
    linkKinds: LINK_KINDS,
  },
} as const satisfies Record<string, DocumentRoom>

export type RoomId = keyof typeof ROOMS

/**
 * 자료를 등록·수정할 때 고를 수 있는 분류.
 *
 * 영업자료실의 상품설명서는 어느 상품을 설명하는지가 있어야 뜻이 서므로 상품에
 * 연결할 때만 고를 수 있습니다.
 */
export function uploadCategories(room: RoomId, kind: DocumentLink['kind']): DocumentCategory[] {
  if (room === 'trade') return [...ROOMS.trade.categories]
  return kind === '상품' ? ['상품설명서', '기타'] : ['기타']
}

/** 허용 목록 밖의 분류는 기타로 접습니다. 연결을 바꿔 고를 수 없게 된 분류가 그렇습니다. */
export const clampCategory = (
  category: DocumentCategory,
  allowed: DocumentCategory[],
): DocumentCategory => (allowed.includes(category) ? category : '기타')

const EXT_KIND: Record<string, DocumentFileKind> = {
  pdf: 'pdf',
  doc: 'doc',
  docx: 'doc',
  hwp: 'doc',
  hwpx: 'doc',
  txt: 'doc',
  xls: 'sheet',
  xlsx: 'sheet',
  csv: 'sheet',
  ppt: 'slide',
  pptx: 'slide',
  key: 'slide',
  jpg: 'image',
  jpeg: 'image',
  png: 'image',
  gif: 'image',
  webp: 'image',
  heic: 'image',
}

export function kindOfFile(file: Pick<File, 'name'>): DocumentFileKind {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return EXT_KIND[ext] ?? 'etc'
}

/**
 * 원본을 어떻게 보여 줄지.
 *
 * - render: 브라우저가 원본을 그대로 그립니다(PDF·이미지).
 * - plain: 원본이 곧 글입니다. 받아서 그대로 읽습니다.
 * - extracted: 브라우저가 그리지 못하는 형식(docx·pptx·hwp·html)이라, 문서에서
 *   뽑아 둔 글로 대신합니다.
 */
export type SourceMode = 'render' | 'plain' | 'extracted'

const PLAIN_TEXT_EXT = new Set(['txt', 'md', 'markdown'])

export function sourceMode(file: Pick<File, 'name'>): SourceMode {
  const kind = kindOfFile(file)
  if (kind === 'pdf' || kind === 'image') return 'render'
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return PLAIN_TEXT_EXT.has(ext) ? 'plain' : 'extracted'
}

const NAME_HINTS: [RegExp, DocumentCategory][] = [
  [/계약|contract/i, '계약서'],
  [/발주|구매요청|po[-_]/i, '발주서'],
  [/설명서|카탈로그|소개|사양|단가|catalog|spec/i, '상품설명서'],
  [/견적|quote|estimate/i, '견적서'],
]

export function guessCategory(fileName: string): DocumentCategory {
  return NAME_HINTS.find(([pattern]) => pattern.test(fileName))?.[1] ?? '기타'
}

/**
 * 파일을 담을 때 분류를 대신 찍어 줄지.
 *
 * 파일명에서 아무것도 읽어 내지 못하면 기타가 나오는데, 그것으로 고른 값을 덮으면
 * 고르고 온 분류가 기타로 튑니다. 읽어 낸 것이 있을 때만 값을 냅니다.
 */
export function categoryFromFileName(
  fileName: string,
  allowed: DocumentCategory[],
): DocumentCategory | null {
  const guessed = clampCategory(guessCategory(fileName), allowed)
  return guessed === '기타' ? null : guessed
}

export function fileOf(doc: SalesDocument): DocumentFile {
  return doc.file
}

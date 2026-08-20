import type { DocumentCategory, DocumentFileKind, DocumentVersion, SalesDocument } from '@/types'

export type CategoryTone = 'blue' | 'purple' | 'green' | 'orange' | 'gray'

export const DOCUMENT_CATEGORIES: DocumentCategory[] = [
  '계약서',
  '발주서',
  '상품설명서',
  '견적서',
  '기타',
]

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

export const LINK_KINDS = ['none', '고객사', '계약', '발주'] as const

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

const NAME_HINTS: [RegExp, DocumentCategory][] = [
  [/계약|contract/i, '계약서'],
  [/발주|구매요청|po[-_]/i, '발주서'],
  [/설명서|카탈로그|소개|사양|단가|catalog|spec/i, '상품설명서'],
  [/견적|quote|estimate/i, '견적서'],
]

export function guessCategory(fileName: string): DocumentCategory {
  return NAME_HINTS.find(([pattern]) => pattern.test(fileName))?.[1] ?? '기타'
}

export function latestOf(doc: SalesDocument): DocumentVersion {
  return doc.versions[doc.versions.length - 1]
}

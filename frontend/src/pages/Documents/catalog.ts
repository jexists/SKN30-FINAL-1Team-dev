// 자료실 화면의 어휘입니다. 분류가 무엇이고 무슨 색으로 보이는지, 파일 종류를
// 어떻게 판정하는지를 여기서 정합니다. 발주의 pipeline.ts 와 같은 자리입니다.
//
// (파일 이름이 documents.ts 가 아닌 이유: Documents.tsx 와 대소문자만 달라 충돌합니다.)
import { documents as seed } from '@/shared/documents'
import type { DocumentCategory, DocumentFileKind, DocumentVersion, SalesDocument } from '@/types'

export type CategoryTone = 'blue' | 'purple' | 'green' | 'orange' | 'gray'

/** 분류 선택지. 탭 순서와 정렬 순서가 이 배열 하나를 씁니다. */
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

/** 연결 대상 선택지. 업로드 폼의 종류 select 가 씁니다. */
export const LINK_KINDS = ['none', '고객사', '계약', '발주'] as const

/** 필터 선택지. 데이터에서 뽑아야 목록과 어긋나지 않습니다. */
export const OWNERS: string[] = [
  ...new Set(seed.flatMap((doc) => doc.versions.map((v) => v.owner))),
].sort()

// utils/attachment.ts 의 kindOf 는 audio/image/pdf 셋뿐이라 자료실에 쓸 수 없습니다.
// 여기서는 MIME 대신 확장자를 봅니다. xlsx·pptx 는 브라우저마다 type 이 비거나 다릅니다.
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

export function kindOfFile(file: File): DocumentFileKind {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return EXT_KIND[ext] ?? 'etc'
}

// 파일명에 든 낱말로 분류를 찍어 둡니다. 업로드 폼에서 사람이 고칠 수 있어
// 틀려도 손해가 없고, 맞으면 파일마다 select 를 여는 수고가 사라집니다.
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
 * 현재 버전. versions 는 오래된 것부터라 마지막이 최신입니다.
 * 표·드로어·검색이 모두 이 하나를 거쳐 같은 값을 봅니다.
 */
export function latestOf(doc: SalesDocument): DocumentVersion {
  return doc.versions[doc.versions.length - 1]
}

/** 시드를 목록의 초기 상태로. 등록일 최신순으로 세워 둡니다. */
export function initialDocuments(): SalesDocument[] {
  return [...seed].sort((a, b) => latestOf(b).uploaded.localeCompare(latestOf(a).uploaded))
}

/** 다음 문서 번호. 올해 번호 중 가장 큰 것에 1 을 더합니다. 발주번호와 같은 방식입니다. */
export function nextDocumentId(list: SalesDocument[]): string {
  const prefix = `FM-DOC-${new Date().getFullYear()}-`
  const last = list.reduce((max, doc) => {
    if (!doc.id.startsWith(prefix)) return max
    const n = Number(doc.id.slice(prefix.length))
    return Number.isNaN(n) ? max : Math.max(max, n)
  }, 0)
  return `${prefix}${String(last + 1).padStart(4, '0')}`
}

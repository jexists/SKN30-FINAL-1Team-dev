// 첨부 파일을 화면용 정보로 바꾸는 것들입니다.
// 일일업무보고와 미팅보고서가 같은 규칙으로 첨부를 다룹니다.
//
// extract 는 아직 흉내입니다. STT·OCR 이 붙으면 fakeExtract 대신 그 결과를 씁니다.
import type { AttachmentKind } from '@/types'

export function kindOf(file: File): AttachmentKind {
  if (file.type.startsWith('audio/')) return 'audio'
  if (file.type.startsWith('image/')) return 'image'
  return 'pdf'
}

export function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

/** 실제 분석 대신 종류별로 그럴듯한 한 줄을 돌려줍니다. */
export function fakeExtract(kind: AttachmentKind, name: string): string {
  if (kind === 'audio') return `${name} 음성에서: 유지보수 조건 재협의 요청, 4분기 예산 검토 언급`
  if (kind === 'image') return `${name} 이미지에서: 화이트보드에 적힌 도입 일정 3단계`
  return `${name} 문서에서: 견적 총액과 납기 조건 요약`
}

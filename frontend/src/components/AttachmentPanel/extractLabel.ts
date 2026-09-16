import type { AttachmentKind } from '@/types'

/** 종류마다 무엇을 뽑아내는지가 다릅니다. 완료 표시와 토글 문구에 함께 씁니다. */
export const EXTRACT_LABEL: Record<AttachmentKind, string> = {
  audio: 'STT',
  image: 'OCR',
  pdf: '텍스트 추출',
}

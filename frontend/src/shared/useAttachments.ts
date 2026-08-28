// 보고서 작성 화면들이 함께 쓰는 첨부 목록.
//
// 업무보고서와 업무보고(일일·주간·월간)가 같은 첨부판을 씁니다. 받는 형식도, 음성을
// 글로 바꿔 내용 칸에 붙이는 것도 같아야 해서 규칙을 여기 하나만 둡니다.
import { useCallback, useRef, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { transcribeAudio } from '@/api/transcriptions'
import type { AttachmentKind, ReportAttachment } from '@/types'
import { sizeLabel } from '@/utils/attachment'

/**
 * 받는 세 가지. 그 밖의 형식은 골라도 목록에 넣지 않습니다.
 *
 * 파일 자체를 보관하는 자리는 아직 없습니다. 음성만 글로 바꿔 내용 칸에 남기고,
 * 사진·PDF 는 무엇을 보고 썼는지 알 수 있게 이름만 목록에 남깁니다.
 */
const kindOf = (file: File): AttachmentKind | null => {
  if (file.type.startsWith('audio/')) return 'audio'
  if (file.type.startsWith('image/')) return 'image'
  if (file.type === 'application/pdf') return 'pdf'
  return null
}

/**
 * @param onTranscribed 음성에서 뽑은 글. 부르는 쪽이 내용 칸에 이어 붙입니다.
 */
export default function useAttachments(onTranscribed: (text: string) => void) {
  const [attachments, setAttachments] = useState<ReportAttachment[]>([])
  /** 첨부를 받지 못했거나 음성 변환이 실패한 이유. */
  const [attachmentError, setAttachmentError] = useState<string | null>(null)

  // 콜백이 매번 새로 와도 addAttachments 는 그대로여야 합니다. 의존성에 넣으면
  // 화면이 다시 그려질 때마다 함수가 새로 생겨 아래 effect 들이 함께 흔들립니다.
  const notify = useRef(onTranscribed)
  notify.current = onTranscribed

  // 지금 화면에 있는 첨부. 변환을 기다리는 동안 목록이 바뀌었는지 보는 데 씁니다.
  const current = useRef(attachments)
  current.current = attachments

  /**
   * 고른 파일을 첨부 목록에 넣습니다.
   *
   * 음성은 넣자마자 글로 바꿔 내용 칸에 이어 붙입니다. 녹음을 넣은 사람이 그 내용을
   * 다시 타이핑할 이유가 없고, AI 는 그 내용 칸을 보고 씁니다.
   */
  const addAttachments = useCallback(async (files: FileList | File[]) => {
    const picked = Array.from(files)
      .map((file) => ({ file, kind: kindOf(file) }))
      .filter((entry): entry is { file: File; kind: AttachmentKind } => entry.kind !== null)

    if (picked.length === 0) {
      setAttachmentError('음성·사진·PDF 만 넣을 수 있습니다.')
      return
    }
    setAttachmentError(null)

    const added = picked.map(({ file, kind }) => ({
      file,
      item: {
        id: crypto.randomUUID(),
        kind,
        name: file.name,
        size: sizeLabel(file.size),
        // 음성만 변환을 기다립니다. 나머지는 넣은 순간 끝입니다.
        state: kind === 'audio' ? ('analyzing' as const) : ('done' as const),
      },
    }))

    setAttachments((prev) => [...prev, ...added.map((entry) => entry.item)])

    for (const { file, item: attachment } of added) {
      if (attachment.kind !== 'audio') continue
      try {
        const text = await transcribeAudio(file)
        // 기다리는 동안 그 첨부가 지워졌거나 다른 초안이 올라왔으면 흘려 보냅니다.
        // 뒤늦은 결과를 내용 칸에 붙이면 지금 보고 있는 글에 남의 것이 섞입니다.
        if (!current.current.some((one) => one.id === attachment.id)) continue
        setAttachments((prev) =>
          prev.map((one) =>
            one.id === attachment.id ? { ...one, state: 'done', extract: text } : one,
          ),
        )
        notify.current(text)
      } catch (reason: unknown) {
        setAttachments((prev) =>
          prev.map((one) => (one.id === attachment.id ? { ...one, state: 'failed' } : one)),
        )
        setAttachmentError(errorMessage(reason, `${file.name} 을(를) 글로 바꾸지 못했습니다.`))
      }
    }
  }, [])

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((one) => one.id !== id))
  }, [])

  return {
    attachments,
    /** 이어 쓰는 보고서의 첨부를 그대로 얹을 때 씁니다. */
    setAttachments,
    attachmentError,
    setAttachmentError,
    addAttachments,
    removeAttachment,
  }
}

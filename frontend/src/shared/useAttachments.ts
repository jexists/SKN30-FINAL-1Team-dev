// 보고서 작성 화면들이 공유하는 첨부 목록. 서버가 보관한 원본 ID와 교정된
// 추출 내용을 생성 입력·최종 제출본에 함께 보존합니다.
import { useCallback, useEffect, useRef, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { uploadReportAttachment } from '@/api/reportAttachments'
import type { AttachmentKind, AttachmentPurpose, ReportAttachment } from '@/types'

const AUDIO_EXTENSIONS = new Set(['.mp3', '.m4a', '.wav', '.webm'])
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp'])
const MAX_ATTACHMENTS = 10

/** 서버가 실제 내용까지 다시 검사하므로 화면에서는 허용 확장자만 빠르게 거릅니다. */
export const kindOf = (file: File): AttachmentKind | null => {
  const dot = file.name.lastIndexOf('.')
  const extension = dot > 0 ? file.name.slice(dot).toLowerCase() : ''
  if (AUDIO_EXTENSIONS.has(extension)) return 'audio'
  if (IMAGE_EXTENSIONS.has(extension)) return 'image'
  if (extension === '.pdf') return 'pdf'
  return null
}

export default function useAttachments() {
  const [attachments, setAttachmentState] = useState<ReportAttachment[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const current = useRef(attachments)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  /** 비동기 완료 직전 삭제·초기화를 즉시 볼 수 있도록 ref와 상태를 함께 바꿉니다. */
  const setAttachments = useCallback((next: ReportAttachment[]) => {
    current.current = next
    setAttachmentState(next)
  }, [])

  const updateAttachments = useCallback(
    (update: (previous: ReportAttachment[]) => ReportAttachment[]) => {
      setAttachments(update(current.current))
    },
    [setAttachments],
  )

  const addAttachments = useCallback(
    async (
      files: FileList | File[],
      purpose: AttachmentPurpose = 'reference',
      acceptedKinds?: readonly AttachmentKind[],
    ) => {
      const supported = Array.from(files)
        .map((file) => ({ file, kind: kindOf(file) }))
        .filter(
          (entry): entry is { file: File; kind: AttachmentKind } =>
            entry.kind !== null && (!acceptedKinds || acceptedKinds.includes(entry.kind)),
        )
      const formatError = acceptedKinds
        ? `이 입력에는 ${acceptedKinds.map((kind) => ({ audio: '음성', image: '사진', pdf: 'PDF' })[kind]).join('·')} 파일만 넣을 수 있습니다.`
        : 'MP3·M4A·WAV·WebM 음성, PNG·JPG·WebP 사진, PDF만 넣을 수 있습니다.'

      if (supported.length === 0) {
        setAttachmentError(formatError)
        return
      }
      const picked = supported.slice(0, Math.max(0, MAX_ATTACHMENTS - current.current.length))
      if (picked.length === 0) {
        setAttachmentError('첨부 파일은 최대 10개까지 넣을 수 있습니다.')
        return
      }
      setAttachmentError(
        picked.length < supported.length
          ? '첨부 파일은 최대 10개까지 넣을 수 있습니다.'
          : supported.length < files.length
            ? formatError
            : null,
      )

      const added = picked.map(({ file, kind }) => ({
        file,
        item: {
          id: crypto.randomUUID(),
          kind,
          purpose,
          name: file.name,
          byteSize: file.size,
          state: 'analyzing' as const,
        },
      }))
      updateAttachments((previous) => [...previous, ...added.map(({ item }) => item)])

      await Promise.all(
        added.map(async ({ file, item }) => {
          try {
            const uploaded = await uploadReportAttachment(file)
            // 업로드 중 삭제·초기화된 파일의 늦은 응답은 화면이나 원문에 되살리지 않습니다.
            if (
              !mounted.current ||
              !current.current.some((attachment) => attachment.id === item.id)
            ) {
              return
            }

            updateAttachments((previous) =>
              previous.map((attachment) =>
                attachment.id === item.id
                  ? ({
                      ...attachment,
                      id: uploaded.id,
                      kind: uploaded.kind,
                      name: uploaded.name,
                      byteSize: uploaded.byte_size,
                      state: 'done',
                      extract: uploaded.extract,
                      ...(uploaded.original_stored
                        ? { originalStored: uploaded.original_stored }
                        : {}),
                    } satisfies ReportAttachment)
                  : attachment,
              ),
            )
          } catch (reason: unknown) {
            if (
              mounted.current &&
              current.current.some((attachment) => attachment.id === item.id)
            ) {
              updateAttachments((previous) =>
                previous.map((attachment) =>
                  attachment.id === item.id ? { ...attachment, state: 'failed' } : attachment,
                ),
              )
              setAttachmentError(
                errorMessage(reason, `${file.name} 파일을 올려 분석하지 못했습니다.`),
              )
            }
          }
        }),
      )
    },
    [updateAttachments],
  )

  const removeAttachment = useCallback(
    (id: string) => {
      updateAttachments((previous) => previous.filter((item) => item.id !== id))
    },
    [updateAttachments],
  )

  const setAttachmentExtract = useCallback(
    (id: string, extract: string) => {
      updateAttachments((previous) =>
        previous.map((item) =>
          item.id === id && item.state === 'done' ? { ...item, extract } : item,
        ),
      )
    },
    [updateAttachments],
  )

  return {
    attachments,
    /** AgentRun 복구 입력을 그대로 얹을 때 씁니다. */
    setAttachments,
    attachmentError,
    setAttachmentError,
    pending: attachments.some((attachment) => attachment.state === 'analyzing'),
    addAttachments,
    removeAttachment,
    setAttachmentExtract,
  }
}

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { DocumentFile, DownloadResponse } from '@/types'

export type DocumentArtifact = 'text' | 'txt' | 'md' | 'json' | 'summary'

export async function downloadFile(file: DocumentFile) {
  if (!file.documentId || !file.id) {
    window.alert('내려받을 파일이 없습니다.')
    return
  }

  try {
    const { data } = await client.get<DownloadResponse>(
      `/documents/${file.documentId}/files/${file.id}/download`,
    )
    // 서명 URL 은 다른 오리진이라 download 속성이 무시됩니다. 현재 탭이 파일로
    // 넘어가지 않도록 새 탭에서 엽니다. 파일 이름은 스토리지가 헤더로 정합니다.
    const link = document.createElement('a')
    link.href = data.url
    link.target = '_blank'
    link.rel = 'noopener noreferrer'
    link.click()
  } catch (reason: unknown) {
    window.alert(errorMessage(reason, '파일을 내려받지 못했습니다.'))
  }
}

export async function downloadArtifact(
  documentId: string,
  fileId: string,
  artifact: DocumentArtifact,
) {
  try {
    const { data } = await client.get<Blob>(
      `/documents/${documentId}/files/${fileId}/artifacts/${artifact}`,
      { responseType: 'blob' },
    )
    const url = URL.createObjectURL(data)
    const extension = artifact === 'summary' ? 'md' : artifact
    const link = document.createElement('a')
    link.href = url
    link.download = `document-${fileId}.${extension}`
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000)
  } catch (reason: unknown) {
    window.alert(errorMessage(reason, '처리 결과를 내려받지 못했습니다.'))
  }
}

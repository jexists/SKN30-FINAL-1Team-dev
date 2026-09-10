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

/**
 * 원본을 화면에서 그대로 보여 주기 위해 한 번에 받아 옵니다.
 *
 * 서명 주소는 60초만 삽니다(DOWNLOAD_EXPIRES_IN). 그 주소를 pdf.js 에 넘기면
 * 페이지를 넘길 때마다 뒤늦게 조각을 더 받으러 가다가 만료된 주소를 만납니다.
 * 통째로 받아 File 로 감싸 두면 만료와 무관해지고, 원본 뷰어가 지금까지 다루던
 * 것과 같은 File 이 됩니다.
 */
export async function fetchSourceFile(file: DocumentFile): Promise<File> {
  if (!file.documentId || !file.id) throw new Error('document_file_missing')

  const { data } = await client.get<DownloadResponse>(
    `/documents/${file.documentId}/files/${file.id}/download`,
  )
  const response = await fetch(data.url)
  if (!response.ok) throw new Error(`document_source_fetch_failed:${response.status}`)
  // media_type 이 비어 오는 행이 있습니다. 뷰어는 그럴 때 확장자로 갈라 봅니다.
  return new File([await response.blob()], data.file_name || file.fileName, {
    type: data.media_type ?? '',
  })
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

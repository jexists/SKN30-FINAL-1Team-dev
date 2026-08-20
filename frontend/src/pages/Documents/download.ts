import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { DocumentVersion, DownloadResponse } from '@/types'

export async function downloadVersion(version: DocumentVersion) {
  if (!version.documentId || !version.id) {
    window.alert('내려받을 파일이 없습니다.')
    return
  }

  try {
    const { data } = await client.get<DownloadResponse>(
      `/documents/${version.documentId}/files/${version.id}/download`,
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

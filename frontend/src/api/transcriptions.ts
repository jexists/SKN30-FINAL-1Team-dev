// 음성 파일을 글로 바꿉니다. 첨부한 녹음을 미팅 내용에 채우는 데 씁니다.
import { client } from './client'

interface TranscriptionResponse {
  transcript: string
}

/**
 * 음성 변환은 파일 길이만큼 걸립니다. client 의 기본 10초로는 중간에 끊깁니다.
 * 서버가 받는 한도(25MB) 안의 파일이면 이 시간 안에 끝납니다.
 */
const TIMEOUT_MS = 120_000

export async function transcribeAudio(file: File): Promise<string> {
  const form = new FormData()
  form.append('audio', file)

  const { data } = await client.post<TranscriptionResponse>('/transcriptions', form, {
    timeout: TIMEOUT_MS,
  })
  return data.transcript
}

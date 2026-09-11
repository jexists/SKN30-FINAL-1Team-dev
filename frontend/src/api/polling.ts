export interface SummaryProcessingResponse {
  // API는 업로드·처리 중 상태도 반환하므로, 폴러는 여기서 필요한 상태만 판별한다.
  processing_status: string
  processing_error?: string | null
}

interface PollSummaryOptions<T extends SummaryProcessingResponse> {
  start: () => Promise<void>
  read: () => Promise<T>
  intervalMs?: number
  timeoutMs?: number
  now?: () => number
  sleep?: (milliseconds: number) => Promise<void>
}

const DEFAULT_INTERVAL_MS = 1_000
// 배치 요약은 서버에서 한 건씩 차례로 돕니다. 뒤에 선 파일은 앞 건들이 끝날 때까지
// 기다리므로, 여러 개를 한 번에 올린 경우 5분으로는 대기만 하다 끊깁니다.
const DEFAULT_TIMEOUT_MS = 10 * 60 * 1_000

const defaultSleep = (milliseconds: number) =>
  new Promise<void>((resolve) => globalThis.setTimeout(resolve, milliseconds))

/** 요약 시작 후 완료·실패·시간초과 상태를 일관되게 기다린다. */
export async function pollSummary<T extends SummaryProcessingResponse>({
  start,
  read,
  intervalMs = DEFAULT_INTERVAL_MS,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  now = Date.now,
  sleep = defaultSleep,
}: PollSummaryOptions<T>): Promise<T> {
  await start()
  const startedAt = now()

  while (now() - startedAt < timeoutMs) {
    const result = await read()
    if (
      result.processing_status === 'completed' ||
      result.processing_status === 'review_required'
    ) {
      return result
    }
    if (result.processing_status === 'failed') {
      throw new Error(result.processing_error || 'document_summary_failed')
    }
    await sleep(intervalMs)
  }

  throw new Error('document_summary_timeout')
}

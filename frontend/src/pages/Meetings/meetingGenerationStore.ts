import { useSyncExternalStore } from 'react'

import { errorMessage } from '../../api/errorMessage.ts'
import { meetingComposePath } from '../../constants/routes.ts'
import { showToast } from '../../shared/toast.ts'
import type { MeetingProgress, MeetingReport } from '../../types'

import { runDealGeneration } from './generatedDraft.ts'

export interface MeetingGenerationResult {
  reports: MeetingReport[]
  writingFailed: boolean
  errors: Record<string, string>
}

export type MeetingGenerationState = {
  requestId: string
  agendaId: string
  dealIds: string[]
  progress: MeetingProgress | null
  savedReports: MeetingReport[]
} & (
  | { status: 'running' }
  | ({ status: 'completed' } & MeetingGenerationResult)
  | { status: 'failed'; error: string }
)

interface StartOptions {
  agendaId: string
  dealIds: string[]
  execute: (
    onProgress: (progress: MeetingProgress) => void,
    onReportSaved: (report: MeetingReport) => void,
  ) => Promise<MeetingGenerationResult>
}

const active = new Set<string>()
const states = new Map<string, MeetingGenerationState>()
const listeners = new Set<() => void>()

function publish(state: MeetingGenerationState) {
  states.set(state.agendaId, state)
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export const getMeetingGeneration = (agendaId: string) => states.get(agendaId) ?? null

/** 화면이 완료·실패 결과를 반영한 뒤 과거 결과가 다시 적용되지 않게 비웁니다. */
export function acknowledgeMeetingGeneration(agendaId: string, requestId: string) {
  const current = states.get(agendaId)
  if (!current || current.requestId !== requestId || current.status === 'running') return
  states.delete(agendaId)
  for (const listener of listeners) listener()
}

export function useMeetingGeneration(agendaId: string) {
  return useSyncExternalStore(subscribe, () => getMeetingGeneration(agendaId))
}

/** 실행 Promise를 페이지 밖에 보관해 라우트가 바뀌어도 apply와 알림까지 끝냅니다. */
export function startMeetingGeneration({ agendaId, dealIds, execute }: StartOptions) {
  if (!agendaId || active.has(agendaId)) return false
  const requestId = crypto.randomUUID()
  const running: MeetingGenerationState = {
    requestId,
    agendaId,
    dealIds: [...dealIds],
    progress: null,
    savedReports: [],
    status: 'running',
  }

  void runDealGeneration(
    active,
    agendaId,
    () => {},
    async () => {
      publish(running)
      showToast('보고서 작성을 시작했습니다. 다른 화면으로 이동해도 계속됩니다.')
      try {
        const result = await execute(
          (progress) => {
            const current = states.get(agendaId)
            if (current?.requestId === requestId && current.status === 'running') {
              publish({ ...current, progress })
            }
          },
          (report) => {
            const current = states.get(agendaId)
            if (current?.requestId === requestId && current.status === 'running') {
              publish({
                ...current,
                savedReports: [
                  ...current.savedReports.filter(
                    (saved) => saved.salesDealId !== report.salesDealId,
                  ),
                  report,
                ],
              })
            }
          },
        )
        publish({ ...running, ...result, savedReports: result.reports, status: 'completed' })
        const partial = result.writingFailed || Object.keys(result.errors).length > 0
        showToast(
          partial
            ? '미팅 처리가 일부 완료됐습니다. 결과를 확인하세요.'
            : `${dealIds.length}개 딜 보고서와 ML 분석이 완료됐습니다.`,
          {
            tone: partial ? 'error' : 'success',
            persistent: true,
            to: meetingComposePath(agendaId),
            actionLabel: '보고서 보기',
          },
        )
        return true
      } catch (reason: unknown) {
        const message = errorMessage(reason, '미팅 처리를 완료하지 못했습니다.')
        const current = states.get(agendaId)
        publish({
          ...running,
          savedReports: current?.requestId === requestId ? current.savedReports : [],
          status: 'failed',
          error: message,
        })
        showToast(`미팅 보고서 생성 실패 · ${message}`, {
          tone: 'error',
          persistent: true,
          to: meetingComposePath(agendaId),
          actionLabel: '실패 확인',
        })
        return false
      }
    },
  )
  return true
}

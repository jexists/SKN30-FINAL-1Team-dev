import axios, {
  type AxiosError,
  type InternalAxiosRequestConfig,
  isAxiosError,
  isCancel,
} from 'axios'

import { env } from '@/config/env'

import { markReachable, markUnreachable, notifySessionExpired } from './connectionState'

export const client = axios.create({
  baseURL: `${env.apiBaseUrl}/api`,
  timeout: 10_000,
  withCredentials: true,
})

/** 요청당 한 번만 재시도합니다. 무한 갱신 고리를 막습니다. */
interface RetriableConfig extends InternalAxiosRequestConfig {
  retriedAfterRefresh?: boolean
}

/**
 * 갱신을 시도하지 않는 경로입니다.
 *
 * - `/auth/me` 의 401 은 최초 진입의 정상적인 비로그인 상태입니다.
 * - `/auth/login` 의 401 은 비밀번호 오류라 갱신할 세션이 없습니다.
 * - `/auth/refresh` 자신을 다시 부르면 고리가 됩니다.
 */
const NO_REFRESH_PATHS = ['/auth/me', '/auth/login', '/auth/refresh', '/auth/logout']

function skipsRefresh(url: string | undefined): boolean {
  if (!url) return false
  return NO_REFRESH_PATHS.some((path) => url === path || url.endsWith(path))
}

/**
 * 실패를 스스로 설명하는 화면이 있어서 전역 안내가 겹치면 곤란한 경로입니다.
 *
 * 로그인 폼은 어떤 실패든 입력란 아래에 문구를 띄웁니다. 같은 내용을 모달로
 * 한 번 더 말하면 중복이라 여기서만 빼 둡니다.
 */
const OWN_ERROR_SURFACE_PATHS = ['/auth/login']

function ownsItsErrorSurface(url: string | undefined): boolean {
  if (!url) return false
  return OWN_ERROR_SURFACE_PATHS.some((path) => url === path || url.endsWith(path))
}

/** 응답이 아예 없으면 네트워크·timeout 이고, 5xx 는 서버가 답을 못 준 경우입니다. */
function isUnreachable(error: AxiosError): boolean {
  const status = error.response?.status
  if (status === undefined) return true
  return status >= 500
}

let refreshInFlight: Promise<void> | null = null

/** 동시에 여러 요청이 401 을 받아도 갱신은 한 번만 나갑니다. */
function refreshSession(): Promise<void> {
  refreshInFlight ??= client
    .post('/auth/refresh')
    .then(() => undefined)
    .finally(() => {
      refreshInFlight = null
    })
  return refreshInFlight
}

client.interceptors.response.use(
  (response) => {
    markReachable()
    return response
  },
  async (error: unknown) => {
    if (!isAxiosError(error)) throw error

    // 취소는 화면이 스스로 그만둔 것이라 응답이 없어도 연결 실패가 아닙니다.
    // 연결 상태를 건드리면 취소할 때마다 안내가 떴다 사라집니다.
    if (isCancel(error)) throw error

    if (isUnreachable(error)) {
      if (!ownsItsErrorSurface(error.config?.url)) markUnreachable()
      throw error
    }
    markReachable()

    const config = error.config as RetriableConfig | undefined
    const shouldRefresh =
      error.response?.status === 401 &&
      config !== undefined &&
      !config.retriedAfterRefresh &&
      !skipsRefresh(config.url)
    if (!shouldRefresh) throw error

    try {
      await refreshSession()
    } catch (refreshError: unknown) {
      // 갱신도 안 되면 서버 기준으로 세션이 끝난 것입니다.
      if (isAxiosError(refreshError) && isUnreachable(refreshError)) markUnreachable()
      else notifySessionExpired()
      throw error
    }

    config.retriedAfterRefresh = true
    return client.request(config)
  },
)

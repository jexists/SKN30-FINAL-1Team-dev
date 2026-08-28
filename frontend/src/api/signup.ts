import { client } from './client'

/**
 * 계정을 받고 싶다는 요청을 남깁니다.
 *
 * 백엔드는 이 요청을 저장하지 않고 팀 Discord 채널로 넘깁니다. 그래서
 * 성공 응답은 "알림이 실제로 도착했다"는 뜻입니다. 실패하면 화면이 알립니다.
 */
export async function requestAccount(email: string): Promise<void> {
  await client.post('/signup/request', { email })
}

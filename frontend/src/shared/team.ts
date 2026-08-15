// 팀 명부 도메인. 명부 시드는 mocks/ 에서 받습니다.
import { TEAM } from '@/mocks'
import type { TeamMember } from '@/types'

export { TEAM }

export function findMemberById(id: string): TeamMember | undefined {
  return TEAM.find((member) => member.id === id)
}

export function findMemberByName(name: string): TeamMember | undefined {
  return TEAM.find((member) => member.name === name)
}

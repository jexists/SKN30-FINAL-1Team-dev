import type { TeamMember } from '@/types'

export const TEAM: TeamMember[] = []

export function findMemberById(id: string): TeamMember | undefined {
  return TEAM.find((member) => member.id === id)
}

export function findMemberByName(name: string): TeamMember | undefined {
  return TEAM.find((member) => member.name === name)
}

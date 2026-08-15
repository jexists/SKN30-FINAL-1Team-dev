// 지금 로그인한 데모 프로필에 맞춰 시드를 골라 내보냅니다. shared/ 는 여기만 봅니다.
//
// 프로필은 모듈이 처음 로드될 때 한 번 확정됩니다. 시드에서 파생되는 값들(SUPPLIERS,
// agendaByDate 등)이 전부 모듈 최상위에서 계산되기 때문에, 로그인 중에 데이터셋을
// 갈아끼울 수는 없습니다. 그래서 로그인 화면이 프로필을 저장하고 통째로 새로고침합니다.
import { agendaSeed as allAgenda } from './agenda'
import { contractSeed as allContracts } from './contracts'
import {
  csRequests as allCs,
  followUps as allFollowUps,
  renewals as allRenewals,
  salesGoal as teamGoal,
} from './counters'
import { customerSeed as allCustomers } from './customers'
import { documentSeed as allDocuments } from './documents'
import { meetingReportSeed as allMeetings } from './meetings'
import { directives as allDirectives, notices as allNotices } from './notices'
import { purchaseOrderSeed as allOrders } from './orders'
import { findProfile, type MockProfile } from './profiles'
import { extraActivitySeed as allExtraActivities, reportSeed as allReports } from './reports'
import { suggestionSeed as allSuggestions } from './suggestions'

const KEY = 'salesluv.profile'

export function readProfileId(): string | null {
  try {
    return sessionStorage.getItem(KEY)
  } catch {
    // 사파리 프라이빗 모드 등에서 접근이 막히면 기본 프로필로 갑니다.
    return null
  }
}

export function writeProfileId(id: string): void {
  try {
    sessionStorage.setItem(KEY, id)
  } catch {
    // 저장에 실패해도 이번 세션 동안은 기본 프로필로 동작합니다.
  }
}

export function clearProfileId(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // 위와 같음
  }
}

export const profile: MockProfile = findProfile(readProfileId())

/** 담당자가 붙은 시드. 첫 세팅이면 비우고, 팀원 프로필이면 자기 것만 남깁니다. */
const pick = <T extends { owner: string }>(seed: T[]): T[] =>
  !profile.seeded ? [] : profile.owner ? seed.filter((s) => s.owner === profile.owner) : seed

/** 담당자가 없는 시드. 첫 세팅인지 여부로만 갈립니다. */
const only = <T>(seed: T[]): T[] => (profile.seeded ? seed : [])

// 담당자가 붙은 것들. 이 시드를 쓰는 화면에는 스코프 필터가 없어 여기서 겁니다.
export const agendaSeed = pick(allAgenda)
export const suggestionSeed = pick(allSuggestions)
export const meetingReportSeed = pick(allMeetings)
export const reportSeed = pick(allReports)
export const followUps = pick(allFollowUps)
export const csRequests = pick(allCs)
export const renewals = pick(allRenewals)

// 공지는 팀 전체가 함께 보는 글이라 담당자로 나누지 않습니다.
export const notices = only(allNotices)
export const directives = only(allDirectives)

// 첫 세팅에서는 실적이 0 입니다. 목표는 조직이 정해 둔 값이라 남깁니다.
export const salesGoal = profile.seeded ? teamGoal : { ...teamGoal, achieved: 0 }

// 담당자를 화면에서 useOwnerScope 로 이미 거르는 것들. 첫 세팅인지만 여기서 봅니다.
export const customerSeed = only(allCustomers)
export const contractSeed = only(allContracts)
export const documentSeed = only(allDocuments)
export const purchaseOrderSeed = only(allOrders)

/** 보고서 초안에 딸려 오는 활동. 첫 세팅에는 주워 올 활동이 없습니다. */
export const extraActivitySeed = profile.seeded ? allExtraActivities : {}

// 팀 명부·지역·목표·보고 양식은 계정이 만들어질 때 이미 있는 설정값이라 늘 그대로입니다.
export { meetingTemplate } from './meetings'
export { regionByOrg } from './regions'
export { APPROVERS, dailyTemplate, monthlyTemplate, weeklyTemplate } from './reports'
export { monthlyTargetByOrg } from './salesTargets'
export { TEAM } from './team'

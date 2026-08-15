// 고객 한 명에게 걸리는 것들을 기존 content 모듈에서 모읍니다.
// 새 데이터를 만들지 않고 지금 있는 것만 이어 붙입니다.
//
// id 로 잇는 관계가 데이터에 없어 전부 한글 이름 문자열로 맞춥니다.
// 회사는 org/hospital 이 그대로 같고(orders.findOrderFor 도 같은 방식),
// 사람은 표기가 달라 아래 규칙이 필요합니다.
//
// 그래서 시드에 사람을 새로 적을 때 표기를 지켜야 합니다. 어긋나면 오류 없이
// 조용히 빠집니다. agenda.contact 는 '{이름} {직함}',
// counters 의 who 는 '{부서} · {이름} {직함}' 입니다.
//
// 백엔드를 붙이면 이 파일의 이름 맞추기를 customerId 비교로 갈아탑니다.
// 바깥은 아래 함수 이름만 알고 있어 그때 고칠 곳은 여기뿐입니다.
import { agendaSnapshot } from '@/shared/agenda'
import { contracts } from '@/shared/contracts'
import { csSnapshot, followUps, renewals } from '@/shared/counters'
import { activeOrders } from '@/shared/orders'
import type {
  AgendaItem,
  Contract,
  CsRequest,
  Customer,
  FollowUp,
  PurchaseOrder,
  Renewal,
} from '@/types'

// 일정은 화면에서 추가·삭제되므로 모듈 로드 때 한 번 베껴두면 안 됩니다. 부를 때 읽습니다.

/**
 * 자유 문자열로 적힌 담당자가 이 고객인지 봅니다.
 *
 * 일정은 '박서준 교수', 고객 이름은 '박서준' 뿐이라 앞부분만 맞춰 봅니다.
 * 직함이 서로 달라도(교수/과장) 같은 사람으로 잡힙니다. 다만 이름만으로는
 * 동명이인이 섞이므로 부르는 쪽에서 회사까지 함께 봐야 합니다.
 */
function isSamePerson(label: string, name: string): boolean {
  return label === name || label.startsWith(`${name} `)
}

/** 후속업무·C/S·갱신의 who 는 '순환기내과 · 박서준 교수' 처럼 부서가 앞에 붙습니다. */
function personPart(who: string): string {
  const parts = who.split(' · ')
  return parts[parts.length - 1] ?? who
}

function matchesWho(entry: { org: string; who: string }, c: Customer): boolean {
  return entry.org === c.org && isSamePerson(personPart(entry.who), c.name)
}

/** 이 고객이 담당자로 잡힌 일정. 최근 것이 위로 옵니다. */
export function meetingsOf(c: Customer): AgendaItem[] {
  return agendaSnapshot()
    .filter((it) => it.hospital === c.org && isSamePerson(it.contact, c.name))
    .sort((a, b) => b.date.localeCompare(a.date) || b.time.localeCompare(a.time))
}

/** 마감이 가까운 것부터 */
export function followUpsOf(c: Customer): FollowUp[] {
  return followUps.filter((f) => matchesWho(f, c)).sort((a, b) => a.dueOff - b.dueOff)
}

/** 접수가 최근인 것부터. C/S 도 화면에서 등록되므로 부를 때 읽습니다. */
export function csRequestsOf(c: Customer): CsRequest[] {
  return csSnapshot()
    .filter((r) => matchesWho(r, c))
    .sort((a, b) => b.agoOff - a.agoOff)
}

/** 만료가 가까운 것부터 */
export function renewalsOf(c: Customer): Renewal[] {
  return renewals.filter((r) => matchesWho(r, c)).sort((a, b) => a.expireOff - b.expireOff)
}

/** 회사 단위입니다. contracts 는 이미 계약일 내림차순이라 그대로 거릅니다. */
export function contractsOf(c: Customer): Contract[] {
  return contracts.filter((ct) => ct.org === c.org)
}

/** 회사 단위입니다. 취소 건은 activeOrders 가 이미 뺍니다. */
export function ordersOf(c: Customer): PurchaseOrder[] {
  return activeOrders()
    .filter((o) => o.hospital === c.org)
    .sort((a, b) => a.expectOff - b.expectOff)
}

/**
 * 같은 회사의 다른 담당자.
 *
 * 목록을 인자로 받습니다. 시드를 직접 읽으면 방금 등록하거나 지운 고객이
 * 표와 어긋납니다.
 */
export function colleaguesOf(c: Customer, all: Customer[]): Customer[] {
  return all.filter((other) => other.org === c.org && other.id !== c.id)
}

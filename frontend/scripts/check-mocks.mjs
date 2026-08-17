// 프로필 4종의 데이터셋을 실제 모듈 그래프로 만들어 확인합니다.
// vite 의 ssrLoadModule 을 쓰므로 @/ alias 와 tsconfig 가 앱과 똑같이 적용됩니다.
import assert from 'node:assert'
import { createServer } from 'vite'

const root = new URL('..', import.meta.url).pathname

async function load(profileId) {
  const store = new Map(profileId ? [['salesluv.profile', profileId]] : [])
  globalThis.sessionStorage = {
    getItem: (k) => store.get(k) ?? null,
    setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k),
  }
  // 모듈 캐시를 비워야 프로필마다 mocks/index.ts 가 다시 평가됩니다.
  const server = await createServer({ root, server: { middlewareMode: true }, appType: 'custom' })
  const [mocks, agenda, customers, contracts, orders, docs, reports, meetings, notices, sugg] =
    await Promise.all([
      server.ssrLoadModule('/src/mocks/index.ts'),
      server.ssrLoadModule('/src/shared/agenda.ts'),
      server.ssrLoadModule('/src/shared/customers.ts'),
      server.ssrLoadModule('/src/shared/contracts.ts'),
      server.ssrLoadModule('/src/shared/orders.ts'),
      server.ssrLoadModule('/src/shared/documents.ts'),
      server.ssrLoadModule('/src/shared/reports.ts'),
      server.ssrLoadModule('/src/shared/meetings.ts'),
      server.ssrLoadModule('/src/shared/notices.ts'),
      server.ssrLoadModule('/src/shared/suggestions.ts'),
    ])
  const out = {
    프로필: mocks.profile.id,
    이름: mocks.profile.name,
    일정: agenda.agendaSnapshot().length,
    고객: customers.customers.length,
    계약: contracts.contracts.length,
    발주: orders.orders.length,
    문서: docs.documents.length,
    업무보고: reports.reportHistory.length,
    미팅보고: meetings.meetingReportHistory.length,
    공지: notices.notices.length + notices.directives.length,
    추천: sugg.aiSuggestions.length,
    후속: mocks.followUps.length,
    CS: mocks.csRequests.length,
    갱신: mocks.renewals.length,
    매출실적: mocks.salesGoal.achieved,
    팀명부: mocks.TEAM.length,
  }
  await server.close()
  return out
}

const rows = []
for (const id of ['sample-manager', 'sample-member', 'empty-manager', 'empty-member']) {
  rows.push(await load(id))
}
console.table(rows)

const [mgr, mem, emptyMgr, emptyMem] = rows

// 샘플 팀장은 전체를 본다
assert(mgr.일정 === 12 && mgr.고객 === 32 && mgr.계약 === 111, '샘플 팀장이 전체 시드를 못 받음')

// 샘플 팀원은 자기 것만 — 스코프가 닿지 않는 시드가 실제로 줄어야 한다
assert(mem.일정 < mgr.일정 && mem.일정 > 0, `팀원 일정이 안 걸러짐: ${mem.일정}`)
assert(mem.추천 < mgr.추천 && mem.후속 < mgr.후속, '팀원 추천·후속이 안 걸러짐')
assert(mem.공지 === mgr.공지, '공지는 팀 공유물이라 같아야 함')

// 첫 세팅은 영업 데이터가 비고, 조직 설정값은 남는다
for (const [name, row] of [
  ['팀장', emptyMgr],
  ['팀원', emptyMem],
]) {
  for (const k of [
    '일정',
    '고객',
    '계약',
    '발주',
    '문서',
    '업무보고',
    '미팅보고',
    '공지',
    '추천',
    '후속',
    'CS',
    '갱신',
  ]) {
    assert(row[k] === 0, `첫 세팅 ${name} 의 ${k} 가 ${row[k]} (0 이어야 함)`)
  }
  assert(row.매출실적 === 0, `첫 세팅 ${name} 의 매출 실적이 ${row.매출실적}`)
  assert(row.팀명부 === 2, `첫 세팅 ${name} 의 팀 명부가 ${row.팀명부} (2 이어야 함)`)
}

// 프로필이 없으면 샘플 팀장으로 떨어진다
assert((await load(null)).프로필 === 'sample-manager', '기본 프로필이 샘플 팀장이 아님')

console.log('\n통과: 프로필 4종 + 기본값')

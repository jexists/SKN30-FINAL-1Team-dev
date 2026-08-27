// 자체 검사. 저장소에 프론트 테스트 러너가 없어 실행할 수 있는 파일 하나로 둡니다.
//
//     cd frontend && npx tsx src/utils/date.check.ts
//
// 달을 더하는 계산은 말일과 해 넘김에서 틀리기 쉬워 그 두 가지를 짚습니다.
import { addMonthsKeepingDay, iso, parseISO, wholeMonthsBetween } from './date'

// console.assert 는 실패해도 그냥 지나가 마지막 줄이 거짓말을 합니다. 세어 둡니다.
let failed = 0
function check(ok: boolean, label: string) {
  if (ok) return
  failed += 1
  console.error('실패:', label)
}

const plus = (from: string, months: number) => iso(addMonthsKeepingDay(parseISO(from), months))

// 날짜를 지킵니다.
check(plus('2026-08-26', 1) === '2026-09-26', '8/26 + 1개월')
check(plus('2026-08-26', 6) === '2027-02-26', '8/26 + 6개월')

// 해를 넘깁니다.
check(plus('2026-12-26', 1) === '2027-01-26', '12/26 + 1개월')

// 없는 날짜가 되면 그 달 말일로 깎습니다. addMonths 를 그대로 썼다면 1일이 나옵니다.
check(plus('2026-01-31', 1) === '2026-02-28', '1/31 + 1개월')
check(plus('2028-01-31', 1) === '2028-02-29', '1/31 + 1개월 (윤년)')
check(plus('2026-03-31', 1) === '2026-04-30', '3/31 + 1개월')

// 되짚기. 딱 떨어지지 않으면 null 이라 폼이 직접 입력으로 엽니다.
const back = (from: string, to: string) => wholeMonthsBetween(parseISO(from), parseISO(to))
check(back('2026-08-26', '2026-09-26') === 1, '되짚기 1개월')
check(back('2026-01-31', '2026-02-28') === 1, '되짚기 말일 보정')
check(back('2026-08-26', '2026-09-25') === null, '하루 모자라면 null')
check(back('2026-08-26', '2026-08-26') === null, '같은 날은 null')

// throw 로 끝냅니다. process 는 브라우저 tsconfig 에 타입이 없고, 이 한 줄 때문에
// @types/node 를 들이는 것은 과합니다. tsx 는 예외로도 0 이 아닌 코드를 냅니다.
if (failed > 0) throw new Error(`date 자체 검사 ${failed}건 실패`)
console.log('date 자체 검사 통과')

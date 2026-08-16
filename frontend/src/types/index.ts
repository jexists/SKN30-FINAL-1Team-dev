// 도메인 타입입니다. 값은 하나도 없고 타입만 둡니다.
//
// 파일은 mocks/ · shared/ 와 같은 이름으로 나눠 두었습니다. 고객 타입을 고치려면
// types/customers.ts, mocks/customers.ts, shared/customers.ts 세 곳만 보면 됩니다.
//
// 여기는 모아서 내보내기만 합니다. 쓰는 쪽은 `import type { Customer } from '@/types'`
// 한 줄로 충분하고, 어느 파일에 있는지 외우지 않아도 됩니다.
//
// 시연 데이터의 날짜는 전부 오늘 기준 offset(일) 으로 두어 시연이 낡지 않게 합니다.
// 화면에서 쓸 실제 날짜는 shared/ 의 각 모듈이 TODAY 를 기준으로 만들어 냅니다.

export type * from './agenda'
export type * from './contracts'
export type * from './counters'
export type * from './customers'
export type * from './documents'
export type * from './meetings'
export type * from './notices'
export type * from './notifications'
export type * from './orders'
export type * from './quotes'
export type * from './reports'
export type * from './stage'
export type * from './suggestions'
export type * from './team'

// 고객사별 월 매출 목표. 시연용 합성 데이터입니다.
// 합계는 mocks/counters.ts 의 salesGoal.target(팀 월 목표 3억)과 같습니다.

export const monthlyTargetByOrg: Record<string, number> = {
  한빛대학교병원: 90_000_000,
  서림메디컬센터: 70_000_000,
  새봄정형외과: 45_000_000,
  정우병원: 40_000_000,
  도담재활병원: 30_000_000,
  미래아동병원: 25_000_000,
}

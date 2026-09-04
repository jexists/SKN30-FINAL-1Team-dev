// 자리표시자가 잡는 높이. 실제 화면의 값들이라, 자리표시자를 걷어도 줄이 밀리지 않습니다.
export const CONTROL_H = 36 // --control-h
export const HEAD_H = 40 // 표 머리글
export const ROW_H = 44 // 표 한 줄

/** 머리글 한 줄과 본문 rows 줄이 차지하는 높이 */
export const tableHeight = (rows: number) => HEAD_H + ROW_H * rows

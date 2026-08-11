// src/styles/_variables.scss 의 $bp-md 와 반드시 같이 유지할 것.
//
// 레이아웃 분기는 SCSS 쪽 breakpoint 로 처리합니다. 여기 있는 값은 CSS 로는
// 표현할 수 없는 동작(창을 넓히면 열려 있던 모바일 드로어를 닫기) 하나에만 씁니다.
// matchMedia 는 숫자를 받아야 해서 SCSS 변수를 그대로 쓸 수 없습니다.

/** 사이드바가 드로어에서 고정 사이드바로 바뀌는 폭 ($bp-md + 1px) */
export const BP_DESKTOP = 821

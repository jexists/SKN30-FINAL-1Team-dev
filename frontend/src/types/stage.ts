// 단계의 어휘입니다. 영업·견적·계약·발주 네 화면이 저마다 단계 집합을 갖되
// 색과 모양은 하나로 씁니다. 여기 있는 것은 화면에 보이는 것뿐이고,
// 그 단계에 놓였을 때 무슨 뜻인지(계약의 outcome 같은)는 각 화면이 얹습니다.

export type ColumnTone = 'gray' | 'blue' | 'purple' | 'orange' | 'green' | 'red'

export interface Stage {
  id: string
  name: string
  tone: ColumnTone
}

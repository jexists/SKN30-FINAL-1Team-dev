// 업무보고 목록으로 나가는 길. 미팅·업무보고 흐름의 화면들이 모두 이것 하나를 씁니다.
//
// 모양·문구·아이콘을 여기서 다 정합니다. 호출부가 정하는 것은 어느 탭으로 갈지와,
// 머리말 안에서 어디에 설지(className), 그리고 화살표가 어느 쪽을 보는지(back)뿐이라
// 화면마다 이름이 갈라질 자리가 없습니다.
import { Link } from 'react-router'

import { buttonClass } from '@/components/Button'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'

import { dailyListPath, type Period } from '../../periods'

import styles from './DailyListLink.module.scss'

interface Props {
  /** 목록에서 열어 둘 탭. 주지 않으면 '전체' 입니다. */
  tab?: Period
  /** 자리 잡는 여백만. 화면마다 주변과 떨어지는 정도가 달라 호출부가 정합니다. */
  className?: string
  /** 본문 위 왼쪽에 서서 되돌아가는 길로 읽힐 때. 화살표가 글자 앞으로 갑니다. */
  back?: boolean
}

export default function DailyListLink({ tab, className, back = false }: Props) {
  const own = back ? `${styles.root} ${styles.back}` : styles.root

  return (
    <Link
      className={buttonClass({ variant: 'outline' }, className ? `${own} ${className}` : own)}
      to={dailyListPath(tab)}
    >
      {back && <ChevronLeftIcon width={15} height={15} />}
      업무보고
      {!back && <ChevronRightIcon width={15} height={15} />}
    </Link>
  )
}

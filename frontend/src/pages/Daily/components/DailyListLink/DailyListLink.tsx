// 업무보고 목록으로 나가는 길. 미팅·업무보고 흐름의 화면들이 모두 이것 하나를 씁니다.
//
// 모양·문구·아이콘을 여기서 다 정합니다. 호출부가 정하는 것은 어느 탭으로 갈지와,
// 머리말 안에서 어디에 설지(className)뿐이라 화면마다 이름이 갈라질 자리가 없습니다.
import { Link } from 'react-router'

import { buttonClass } from '@/components/Button'
import { ChevronRightIcon } from '@/components/icons'

import { dailyListPath, type Period } from '../../periods'

import styles from './DailyListLink.module.scss'

interface Props {
  /** 목록에서 열어 둘 탭. 주지 않으면 '전체' 입니다. */
  tab?: Period
  /** 자리 잡는 여백만. 머리말마다 오른쪽 끝으로 미는 방법이 달라 호출부가 정합니다. */
  className?: string
}

export default function DailyListLink({ tab, className }: Props) {
  return (
    <Link
      className={buttonClass(
        { variant: 'outline', size: 'sm' },
        className ? `${styles.root} ${className}` : styles.root,
      )}
      to={dailyListPath(tab)}
    >
      업무보고
      <ChevronRightIcon width={15} height={15} />
    </Link>
  )
}

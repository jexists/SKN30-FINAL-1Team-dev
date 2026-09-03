// "고객 등록" 버튼에 붙는 드롭다운입니다.
//
// 고객을 넣는 길이 넷이 되었습니다. 낱개 버튼으로 늘어놓으면 줄 끝이 비슷한 버튼 넷이
// 되어 어디가 주된 길인지 사라지므로, 진입점은 버튼 하나로 두고 무엇으로 넣을지는
// 여기서 고릅니다. 결과는 넷 다 같은 일(고객 한 줄)이라 한자리에 모입니다.
import { useRef, useState, type KeyboardEvent } from 'react'

import Button from '@/components/Button'
import {
  CardIcon,
  ChevronDownIcon,
  ContractIcon,
  EditIcon,
  PlusIcon,
  SheetIcon,
} from '@/components/icons'
import Popover from '@/components/Popover'
import { BP_PHONE } from '@/constants/breakpoints'
import useMediaQuery from '@/hooks/useMediaQuery'

import styles from './AddCustomerMenu.module.scss'

/** 고객을 넣는 네 갈래. Customers 의 OpenDialog 값과 같은 말을 씁니다. */
export type AddCustomerWay = 'card' | 'import' | 'create' | 'license'

interface Option {
  way: AddCustomerWay
  Icon: typeof CardIcon
  title: string
  desc: string
}

const OPTIONS: Option[] = [
  { way: 'card', Icon: CardIcon, title: '명함으로 등록', desc: '명함 이미지를 업로드합니다.' },
  {
    way: 'license',
    Icon: ContractIcon,
    title: '사업자 등록증 등록',
    desc: '사업자등록증 PDF를 업로드합니다.',
  },
  { way: 'import', Icon: SheetIcon, title: '엑셀로 등록', desc: '여러 고객을 한 번에 등록합니다.' },
  { way: 'create', Icon: EditIcon, title: '직접 등록', desc: '고객 정보를 직접 입력합니다.' },
]

interface Props {
  onSelect: (way: AddCustomerWay) => void
}

export default function AddCustomerMenu({ onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])
  // 이 버튼은 줄 맨 오른쪽이라 판을 오른쪽 끝에 맞춥니다. 폰에서는 줄이 접혀 버튼이
  // 왼쪽으로 오므로 그대로 두면 판이 화면 밖으로 나갑니다.
  const isPhone = useMediaQuery(`(max-width: ${BP_PHONE}px)`)

  // 위아래 화살표로 항목을 옮겨 다닙니다. 여닫기와 Escape 는 Popover 가 봅니다.
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    const delta = event.key === 'ArrowDown' ? 1 : -1
    itemRefs.current[(index + delta + OPTIONS.length) % OPTIONS.length]?.focus()
  }

  return (
    <Popover
      open={open}
      onClose={() => setOpen(false)}
      align={isPhone ? 'start' : 'end'}
      compact
      label="고객 등록 방식"
      trigger={
        <Button
          type="button"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <PlusIcon width={16} height={16} />
          고객 등록
          <ChevronDownIcon width={15} height={15} />
        </Button>
      }
    >
      <div className={styles.menu} role="menu" aria-label="고객 등록 방식">
        {OPTIONS.map(({ way, Icon, title, desc }, index) => (
          <button
            key={way}
            ref={(node) => {
              itemRefs.current[index] = node
            }}
            type="button"
            role="menuitem"
            className={styles.item}
            // 열자마자 화살표로 이어 고를 수 있게 포커스를 옮깁니다.
            autoFocus={index === 0}
            onKeyDown={(event) => onKeyDown(event, index)}
            onClick={() => {
              setOpen(false)
              onSelect(way)
            }}
          >
            <Icon className={styles.icon} width={17} height={17} />
            <strong className={styles.title}>{title}</strong>
            <span className={styles.desc}>{desc}</span>
          </button>
        ))}
      </div>
    </Popover>
  )
}

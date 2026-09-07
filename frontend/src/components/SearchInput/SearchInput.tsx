// 목록 화면의 검색창. 열한 화면이 같은 것을 씁니다.
//
// 타이핑 중에는 아무것도 부르지 않습니다. 입력 중인 글자는 이 컴포넌트 안에만 있고,
// 검색 버튼이나 Enter 로 확정할 때만 onSearch 로 위에 올립니다. 그래야 한 글자마다
// 화면 전체가 다시 그려지거나 목록 API 가 나가지 않습니다.
//
// 폭은 화면마다 달라 className 으로 받습니다. 높이·모서리·포커스 링은 여기서 정합니다.
import { useEffect, useState } from 'react'

import Button from '@/components/Button'
import { SearchIcon } from '@/components/icons'

import styles from './SearchInput.module.scss'

interface Props {
  /** 확정된 검색어. 목록을 부를 때 쓰는 값입니다. */
  value: string
  /** 검색 버튼·Enter·지우기로 검색어가 확정될 때만 부릅니다. */
  onSearch: (value: string) => void
  placeholder: string
  /** 화면 낭독기가 읽을 이름. 화면마다 '견적 검색'·'고객 검색' 처럼 다릅니다. */
  label: string
  className?: string
}

export default function SearchInput({ value, onSearch, placeholder, label, className }: Props) {
  const [draft, setDraft] = useState(value)

  // 화면이 검색어를 바깥에서 지우거나 바꾸는 일이 있습니다(등록 후 목록 새로고침,
  // 필터 전체 해제, 뒤로 가기). 그때는 입력창도 따라가야 합니다.
  useEffect(() => {
    setDraft(value)
  }, [value])

  return (
    <form
      className={[styles.form, className].filter(Boolean).join(' ')}
      role="search"
      onSubmit={(event) => {
        event.preventDefault()
        onSearch(draft)
      }}
    >
      <label className={styles.root}>
        <SearchIcon width={16} height={16} />
        <input
          type="search"
          value={draft}
          placeholder={placeholder}
          aria-label={label}
          onChange={(event) => {
            const next = event.target.value
            setDraft(next)
            // 입력창의 X 나 Esc 로 비운 것은 '검색 해제' 로 봅니다. 눌렀는데 목록이
            // 그대로면 고장으로 보입니다. 그 외에는 타이핑 중 아무것도 부르지 않습니다.
            if (next === '' && value !== '') onSearch('')
          }}
        />
      </label>

      <Button type="submit" variant="outline">
        검색
      </Button>
    </form>
  )
}

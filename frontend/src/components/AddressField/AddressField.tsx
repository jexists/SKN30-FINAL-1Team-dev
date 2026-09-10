// 다음(카카오) 우편번호 서비스로 주소를 골라 넣는 입력입니다.
//
// 우편번호와 주소는 직접 치지 않습니다. 오타 난 주소는 지도에서 찾을 수 없어, 고른 값만
// 그대로 담고 층·호수만 사람이 적습니다. 명함·사업자등록증에서 읽어 온 주소도 한 줄로
// 오므로, 칸도 한 줄입니다. 주소 부분을 누르면 우편번호 창이 열리고, 줄 끝에 이어서 치면
// 그게 상세주소가 됩니다. 한 줄을 만들고 되읽는 규칙은 addressLine 에 있습니다.
import { useState } from 'react'

import { loadDaumPostcode, pickAddress } from '@/utils/daumPostcode'

import styles from './AddressField.module.scss'
import { type AddressValue, caretPicksAddress, formatAddress, readAddressLine } from './addressLine'

export type { AddressValue }

interface Props {
  value: AddressValue
  onChange: (next: AddressValue) => void
  /** 폼을 보내는 중처럼 잠깐 잠글 때 */
  disabled?: boolean
  /** 이미 있는 회사의 주소. 보여 주기만 합니다. */
  readOnly?: boolean
}

export default function AddressField({
  value,
  onChange,
  disabled = false,
  readOnly = false,
}: Props) {
  const [loadError, setLoadError] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)

  const shown = formatAddress(value)

  const search = async () => {
    if (opening || disabled || readOnly) return
    setOpening(true)
    setLoadError(null)
    try {
      const Postcode = await loadDaumPostcode()
      new Postcode({
        oncomplete: (result) => {
          onChange({
            postcode: result.zonecode,
            address: pickAddress(result),
            // 주소가 바뀌면 층·호수도 남의 것이 됩니다.
            addressDetail: '',
          })
        },
      }).open()
    } catch {
      setLoadError('주소 검색을 열지 못했습니다. 잠시 뒤 다시 눌러 주세요.')
    } finally {
      setOpening(false)
    }
  }

  /** 커서가 주소 부분에 있을 때만 다시 고릅니다. 열었으면 true 입니다. */
  const pickHere = (caret: number | null): boolean => {
    if (!caretPicksAddress(value, caret)) return false
    void search()
    return true
  }

  // 이미 있는 회사의 주소는 고칠 데가 아닙니다.
  if (readOnly) {
    return (
      <div className={styles.root}>
        <input
          value={shown}
          placeholder="등록된 주소가 없습니다"
          aria-label="주소"
          readOnly
          disabled={disabled}
        />
      </div>
    )
  }

  return (
    <div className={styles.root}>
      <input
        value={shown}
        placeholder={disabled ? '회사를 먼저 고르세요' : '눌러서 주소를 고르세요'}
        aria-label="주소"
        aria-describedby="address-field-hint"
        maxLength={800}
        disabled={disabled}
        onClick={(event) => pickHere(event.currentTarget.selectionStart)}
        onKeyDown={(event) => {
          // 주소 위에서 누른 Enter 는 다시 고르라는 뜻입니다. 상세주소 쪽이면 폼이 받습니다.
          if (event.key !== 'Enter') return
          if (pickHere(event.currentTarget.selectionStart)) event.preventDefault()
        }}
        onChange={(event) => {
          // 고른 주소가 그대로 남아 있을 때만 뒤에 붙은 만큼을 상세주소로 받습니다.
          // 앞부분을 지웠으면 다시 고르겠다는 뜻이라 값을 망가뜨리지 않고 창을 엽니다.
          const next = readAddressLine(value, event.target.value)
          if (next === null) void search()
          else onChange(next)
        }}
      />

      {loadError !== null && (
        <span className={styles.error} role="alert">
          {loadError}
        </span>
      )}
    </div>
  )
}

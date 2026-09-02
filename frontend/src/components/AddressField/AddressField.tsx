// 다음(카카오) 우편번호 서비스로 주소를 골라 넣는 입력입니다.
//
// 우편번호와 주소는 직접 치지 않습니다. 오타 난 주소는 지도에서 찾을 수 없어, 고른 값만
// 그대로 담고 층·호수만 사람이 적습니다.
import { useState } from 'react'

import Button from '@/components/Button'
import { loadDaumPostcode, pickAddress } from '@/utils/daumPostcode'

import styles from './AddressField.module.scss'

export interface AddressValue {
  postcode: string
  address: string
  addressDetail: string
}

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

  const search = async () => {
    if (opening) return
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

  // 이미 있는 회사의 주소는 고칠 데가 아닙니다. 세 칸을 늘어놓는 대신 한 줄로 읽힙니다.
  if (readOnly) {
    return (
      <div className={styles.root}>
        <input
          value={formatAddress(value)}
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
      <div className={styles.line}>
        <input
          className={styles.postcode}
          value={value.postcode}
          placeholder="우편번호"
          aria-label="우편번호"
          readOnly
          disabled={disabled}
        />
        <Button
          type="button"
          variant="outline"
          disabled={disabled || opening}
          onClick={() => void search()}
        >
          주소 검색
        </Button>
      </div>

      <input
        value={value.address}
        placeholder={disabled ? '회사를 먼저 고르세요' : '주소 검색을 눌러 주소를 고르세요'}
        aria-label="주소"
        readOnly
        disabled={disabled}
      />

      <input
        value={value.addressDetail}
        placeholder="상세주소 (동·층·호수)"
        aria-label="상세주소"
        maxLength={254}
        // 주소를 고르기 전에는 어디의 몇 층인지 말할 데가 없습니다.
        disabled={disabled || value.address === ''}
        onChange={(event) => onChange({ ...value, addressDetail: event.target.value })}
      />

      {loadError !== null && (
        <span className={styles.error} role="alert">
          {loadError}
        </span>
      )}
    </div>
  )
}

/** 읽기 전용으로 보여 줄 한 줄. 우편번호는 괄호에 넣습니다. */
function formatAddress({ postcode, address, addressDetail }: AddressValue): string {
  if (address === '') return ''
  const head = postcode === '' ? address : `(${postcode}) ${address}`
  return addressDetail === '' ? head : `${head} ${addressDetail}`
}

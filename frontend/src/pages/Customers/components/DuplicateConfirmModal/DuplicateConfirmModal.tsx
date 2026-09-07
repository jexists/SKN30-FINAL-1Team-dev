/*
 * 단건 등록에서 같은 고객을 다시 넣으려 할 때 묻는 자리입니다.
 *
 * 기존 값과 새 값을 나란히 놓고 어디가 달라졌는지 짚어 주는 화면은 만들지 않습니다.
 * 사람이 방금 명함에서 읽었거나 직접 적은 값은 이미 눈앞에 있고, 물어볼 것은
 * "그 값으로 기존 고객을 고칠까요" 하나뿐입니다. 값이 전부 같으면 그것마저 물을 게
 * 없으므로 이미 등록된 고객이라고만 알리고 새로 만들지 않습니다.
 */
import { Fragment } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import type { CustomerDuplicateResponse } from '@/types'

import { isSameCustomer, type DuplicateDraft } from '../../duplicate'

import styles from './DuplicateConfirmModal.module.scss'

interface Props {
  draft: DuplicateDraft
  match: CustomerDuplicateResponse
  /** 기존 고객을 이 값으로 고칩니다. */
  onUpdate: () => void
  onClose: () => void
  updating?: boolean
  error?: string | null
}

export default function DuplicateConfirmModal({
  draft,
  match,
  onUpdate,
  onClose,
  updating = false,
  error = null,
}: Props) {
  const identical = isSameCustomer(draft, match)

  const rows: [string, string][] = [
    ['회사명', draft.companyName],
    ['고객명', draft.name],
    ['부서', draft.department],
    ['직책', draft.jobTitle],
    ['전화번호', draft.phone],
    ['이메일', draft.email],
  ].filter((row): row is [string, string] => row[1].trim() !== '')

  return (
    <Modal
      title={identical ? '이미 등록된 고객입니다' : '기존 고객이 확인되었습니다'}
      onClose={updating ? () => undefined : onClose}
      footer={
        identical ? (
          <Button type="button" onClick={onClose}>
            확인
          </Button>
        ) : (
          <>
            <Button type="button" variant="outline" disabled={updating} onClick={onClose}>
              취소
            </Button>
            <Button type="button" disabled={updating} onClick={onUpdate}>
              {updating ? '수정 중…' : '수정하기'}
            </Button>
          </>
        )
      }
    >
      <p className={styles.intro}>
        {identical
          ? `${match.company_name} · ${match.name} 님과 같은 정보입니다. 새로운 고객으로 등록하지 않습니다.`
          : '현재 등록된 정보를 아래 정보로 수정하시겠습니까? 취소하면 기존 정보를 그대로 둡니다.'}
      </p>

      <dl className={styles.fields}>
        {rows.map(([label, value]) => (
          <Fragment key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </Fragment>
        ))}
      </dl>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </Modal>
  )
}

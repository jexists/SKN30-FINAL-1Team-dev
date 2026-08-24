import { useEffect, useRef, useState, type ReactNode } from 'react'

import { errorMessage } from '@/api/errorMessage'
import Button from '@/components/Button'
import { CloseIcon, UploadIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import type { ProductCategoryCode, ProductCreateRequest } from '@/types'
import { sizeLabel } from '@/utils/attachment'

import { CATEGORIES } from '../catalog'

import styles from '../Products.module.scss'

// 서버(upload_guard._IMAGE_ALLOWED)가 받는 형식과 같게 둡니다.
const IMAGE_ACCEPT = 'image/png,image/jpeg,image/webp'
const IMAGE_MAX_BYTES = 5 * 1024 * 1024

interface Props {
  onClose: () => void
  onSubmit: (payload: ProductCreateRequest, image: File | null) => Promise<void>
}

type Errors = Partial<Record<'name' | 'unitPrice' | 'shelfLife' | 'image', string>>

export default function ProductFormModal({ onClose, onSubmit }: Props) {
  const [name, setName] = useState('')
  const [categoryCode, setCategoryCode] = useState<ProductCategoryCode>('system')
  const [unitPrice, setUnitPrice] = useState('')
  const [shelfLife, setShelfLife] = useState('')
  const [memo, setMemo] = useState('')
  const [image, setImage] = useState<File | null>(null)
  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // 미리보기 주소는 브라우저 메모리를 잡고 있으므로 사진이 바뀌면 놓아 줍니다.
  const [preview, setPreview] = useState<string | null>(null)
  useEffect(() => {
    if (image === null) {
      setPreview(null)
      return
    }
    const objectUrl = URL.createObjectURL(image)
    setPreview(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [image])

  const pickImage = (file: File | undefined) => {
    if (file === undefined) return
    if (file.size > IMAGE_MAX_BYTES) {
      setErrors((previous) => ({ ...previous, image: '사진은 5MB까지 올릴 수 있습니다.' }))
      return
    }
    setImage(file)
    setErrors((previous) => ({ ...previous, image: undefined }))
  }

  const submit = async () => {
    if (submitting) return

    const found: Errors = {}
    if (name.trim() === '') found.name = '제품명을 입력하세요.'
    const price = Number(unitPrice)
    if (unitPrice.trim() === '' || !Number.isInteger(price) || price < 0) {
      found.unitPrice = '0 이상의 정수로 입력하세요.'
    }
    const months = shelfLife.trim() === '' ? null : Number(shelfLife)
    if (months !== null && (!Number.isInteger(months) || months < 1 || months > 1_200)) {
      found.shelfLife = '1~1200 사이의 정수로 입력하세요.'
    }
    setErrors(found)
    if (Object.keys(found).length > 0) return

    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(
        {
          name: name.trim(),
          category_code: categoryCode,
          unit_price: price,
          shelf_life_months: months,
          memo: memo.trim() === '' ? null : memo.trim(),
        },
        image,
      )
    } catch (caught: unknown) {
      setSubmitError(errorMessage(caught, '상품을 등록하지 못했습니다.'))
      setSubmitting(false)
    }
  }

  const close = () => {
    if (!submitting) onClose()
  }

  return (
    <Modal
      title="상품 등록"
      onClose={close}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? '등록 중…' : '상품 등록'}
          </Button>
        </>
      }
    >
      <div className={styles.grid} aria-busy={submitting}>
        <Field label="제품명" required error={errors.name} wide>
          <input
            value={name}
            maxLength={254}
            disabled={submitting}
            placeholder="예: CardioView X7"
            onChange={(event) => {
              setName(event.target.value)
              setErrors((previous) => ({ ...previous, name: undefined }))
            }}
          />
        </Field>

        <Field label="분류" required>
          <select
            value={categoryCode}
            disabled={submitting}
            onChange={(event) => setCategoryCode(event.target.value as ProductCategoryCode)}
          >
            {CATEGORIES.map((category) => (
              <option key={category.code} value={category.code}>
                {category.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="제품단가 (원)" required error={errors.unitPrice}>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            step={1}
            value={unitPrice}
            disabled={submitting}
            placeholder="12000000"
            onChange={(event) => {
              setUnitPrice(event.target.value)
              setErrors((previous) => ({ ...previous, unitPrice: undefined }))
            }}
          />
        </Field>

        <Field label="유효기간 (개월)" error={errors.shelfLife}>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={1200}
            step={1}
            value={shelfLife}
            disabled={submitting}
            placeholder="24"
            onChange={(event) => {
              setShelfLife(event.target.value)
              setErrors((previous) => ({ ...previous, shelfLife: undefined }))
            }}
          />
        </Field>

        <div className={`${styles.field} ${styles.isWide}`}>
          <span className={styles.label}>사진</span>
          <div className={styles.imagePicker}>
            {preview !== null && (
              <img className={styles.preview} src={preview} alt="고른 사진 미리보기" />
            )}
            <div className={styles.imageActions}>
              <Button
                type="button"
                variant="outline"
                disabled={submitting}
                onClick={() => fileRef.current?.click()}
              >
                <UploadIcon width={15} height={15} />
                {image === null ? '사진 고르기' : '다른 사진 고르기'}
              </Button>
              {image !== null && (
                <>
                  <span className={styles.fileName}>
                    {image.name} · {sizeLabel(image.size)}
                  </span>
                  <button
                    type="button"
                    className={styles.removeImage}
                    disabled={submitting}
                    aria-label="고른 사진 빼기"
                    onClick={() => setImage(null)}
                  >
                    <CloseIcon width={14} height={14} />
                  </button>
                </>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              className="sr-only"
              accept={IMAGE_ACCEPT}
              disabled={submitting}
              onChange={(event) => {
                pickImage(event.target.files?.[0])
                // 같은 파일을 다시 골라도 change 가 울리게 비웁니다.
                event.target.value = ''
              }}
            />
          </div>
          <span className={styles.hint}>PNG·JPG·WEBP, 5MB까지. 선택입니다.</span>
          {errors.image && <span className={styles.error}>{errors.image}</span>}
        </div>

        <Field label="메모" wide>
          <textarea
            rows={4}
            value={memo}
            maxLength={5_000}
            disabled={submitting}
            placeholder="사양·재고·주의사항 등을 남겨 주세요"
            onChange={(event) => setMemo(event.target.value)}
          />
        </Field>

        {submitError && (
          <p className={`${styles.error} ${styles.isWide}`} role="alert">
            {submitError}
          </p>
        )}
      </div>
    </Modal>
  )
}

interface FieldProps {
  label: string
  required?: boolean
  error?: string
  wide?: boolean
  children: ReactNode
}

function Field({ label, required, error, wide, children }: FieldProps) {
  return (
    <label className={`${styles.field} ${wide ? styles.isWide : ''}`}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
      </span>
      {children}
      {error && <span className={styles.error}>{error}</span>}
    </label>
  )
}

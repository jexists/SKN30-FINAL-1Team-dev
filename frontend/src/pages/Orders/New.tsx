// 발주 추가 화면입니다. 목록에서 "발주 추가"로 들어옵니다.
//
// 품목 줄이 몇 개까지 늘어날지 모르므로 모달이 아니라 화면 하나를 씁니다.
import { useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import Button from '@/components/Button'
import { ChevronLeftIcon } from '@/components/icons'
import { ROUTES } from '@/constants/routes'

import OrderFields from './components/OrderFields'
import {
  initialState,
  toDraft,
  validate,
  type FormErrors,
  type FormState,
  type ItemState,
} from './orderForm'
import { ORDER_STATUSES } from './pipeline'
import useOrderList from './useOrderList'

import styles from './New.module.scss'

export default function New() {
  const {
    companies,
    contracts,
    products,
    suppliers,
    loading,
    error,
    reload,
    isCreating,
    addOrder,
  } = useOrderList()
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [form, setForm] = useState<FormState>(() => {
    const base = initialState()
    // 목록에서 상태 탭을 고른 채로 들어오면 그 상태로 시작합니다.
    const wanted = params.get('status') ?? ''
    return (ORDER_STATUSES as string[]).includes(wanted) ? { ...base, status: wanted } : base
  })
  const [errors, setErrors] = useState<FormErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const submittingRef = useRef(false)

  const set = (key: Exclude<keyof FormState, 'items'>, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const setItems = (items: ItemState[]) => setForm((prev) => ({ ...prev, items }))

  const submit = async () => {
    if (submittingRef.current) return
    const found = validate(form)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    submittingRef.current = true
    setSubmitError(null)
    try {
      await addOrder(toDraft(form))
      navigate(ROUTES.ORDERS)
    } catch (caught) {
      setSubmitError(caught instanceof Error ? caught.message : '발주를 등록하지 못했습니다.')
    } finally {
      submittingRef.current = false
    }
  }

  return (
    <section>
      <h1 className="sr-only">발주 추가</h1>

      <header className={styles.head}>
        <Link className={styles.back} to={ROUTES.ORDERS}>
          <ChevronLeftIcon />
          발주 관리
        </Link>
      </header>

      <form
        className={styles.panel}
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <div className={styles.panelHead}>
          <h2>새 발주</h2>
          <p>발주번호는 저장할 때 자동으로 매깁니다.</p>
        </div>

        {error ? (
          <div role="alert">
            <p>{error}</p>
            <Button type="button" variant="outline" onClick={reload}>
              다시 시도
            </Button>
          </div>
        ) : (
          <OrderFields
            form={form}
            errors={errors}
            companies={companies}
            contracts={contracts}
            products={products}
            suppliers={suppliers}
            optionsLoading={loading}
            disabled={isCreating}
            onChange={set}
            onItemsChange={setItems}
          />
        )}

        {submitError && <p role="alert">{submitError}</p>}

        <div className={styles.actions}>
          <Button
            type="button"
            variant="outline"
            disabled={isCreating}
            onClick={() => navigate(ROUTES.ORDERS)}
          >
            취소
          </Button>
          <Button
            type="submit"
            disabled={
              isCreating ||
              loading ||
              error !== null ||
              companies.length === 0 ||
              products.length === 0
            }
          >
            {isCreating ? '등록 중…' : '발주 추가'}
          </Button>
        </div>
      </form>
    </section>
  )
}

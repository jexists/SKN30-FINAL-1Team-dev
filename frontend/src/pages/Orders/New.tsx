// 발주 추가 화면입니다. 목록에서 "발주 추가"로 들어옵니다.
//
// 품목 줄이 몇 개까지 늘어날지 모르므로 모달이 아니라 화면 하나를 씁니다.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import Button from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
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
import useOrderList from './useOrderList'

import styles from './New.module.scss'

export default function New() {
  const { statuses, suppliers, loading, error, reload, isCreating, addOrder } = useOrderList()
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [form, setForm] = useState<FormState>(initialState)
  const [errors, setErrors] = useState<FormErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const submittingRef = useRef(false)

  useEffect(() => {
    if (form.stageCode !== '' || statuses.length === 0) return
    const wanted = params.get('status') ?? ''
    const initial = statuses.find(({ code }) => code === wanted) ?? statuses[0]
    setForm((current) => ({ ...current, stageCode: initial.code }))
  }, [form.stageCode, params, statuses])

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

        <ErrorToast message={error} onRetry={reload} />

        <OrderFields
          form={form}
          errors={errors}
          statuses={statuses}
          suppliers={suppliers}
          optionsLoading={loading}
          disabled={isCreating}
          onChange={set}
          onItemsChange={setItems}
        />

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
            disabled={isCreating || loading || error !== null || statuses.length === 0}
          >
            {isCreating ? '등록 중…' : '발주 추가'}
          </Button>
        </div>
      </form>
    </section>
  )
}

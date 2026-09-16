// 목록 드로어의 옆 패널. 줄을 눌러도 화면을 떠나지 않고, 목록 왼쪽에 그 건의 상세를 펼칩니다.
// 여기서는 읽기만 합니다. 상태를 바꾸거나 이력을 적는 일은 '화면에서 열기'로 넘깁니다.
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import { client } from '@/api/client'
import Button from '@/components/Button'
import { CloseIcon } from '@/components/icons'
import { SkeletonDetail } from '@/components/Skeleton'
import { dealDetailPath, supportRequestPath } from '@/constants/routes'
import complaintStyles from '@/pages/Complaints/Complaints.module.scss'
import {
  ResponseList,
  SupportRequestFacts,
} from '@/pages/Complaints/components/SupportRequestDetail'
import { STATUS_LABEL } from '@/pages/Complaints/statuses'
import ProductSummary from '@/pages/Products/components/ProductSummary'
import { SalesDealDetail } from '@/pages/Deals/SalesDealDrawer'
import { toSalesDeal } from '@/pages/Deals/useSalesDeals'
import type { SalesDealResponse, SupportRequestResponse } from '@/types'

import styles from './DetailPanel.module.scss'

function useDetail<T>(path: string) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setData(null)
    setError(false)
    void client
      .get<T>(path, { signal: controller.signal })
      .then(({ data: body }) => {
        if (!controller.signal.aborted) setData(body)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true)
      })
    return () => controller.abort()
  }, [path, reloadKey])

  return { data, error, reload: () => setReloadKey((value) => value + 1) }
}

interface ShellProps {
  title: string
  /** 화면에서 열 주소. 들어갈 화면이 없는 상세(상품)는 넘기지 않습니다. */
  href?: string
  error: boolean
  onRetry: () => void
  onClose: () => void
  children: ReactNode
}

function Shell({ title, href, error, onRetry, onClose, children }: ShellProps) {
  return (
    <section className={styles.panel} aria-label={`${title} 상세`}>
      <header className={styles.head}>
        <h3>{title}</h3>
        {href && (
          <Link to={href} className={styles.open}>
            화면에서 열기
          </Link>
        )}
        <button type="button" className={styles.close} onClick={onClose} aria-label="상세 닫기">
          <CloseIcon />
        </button>
      </header>
      <div className={styles.body}>
        {error ? (
          <div className={styles.state} role="alert">
            <p>상세를 불러오지 못했습니다.</p>
            <Button variant="outline" size="sm" onClick={onRetry}>
              다시 시도
            </Button>
          </div>
        ) : (
          children
        )}
      </div>
    </section>
  )
}

export function SupportRequestPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, error, reload } = useDetail<SupportRequestResponse>(
    `/support-requests/${encodeURIComponent(id)}`,
  )
  return (
    <Shell
      title={data?.title ?? 'C/S 대응요청'}
      href={supportRequestPath(id)}
      error={error}
      onRetry={reload}
      onClose={onClose}
    >
      {data ? (
        <>
          <div className={styles.badges}>
            <i className={`${complaintStyles.badge} ${complaintStyles[data.status_code]}`}>
              {STATUS_LABEL[data.status_code]}
            </i>
            {data.is_urgent && (
              <i className={`${complaintStyles.badge} ${complaintStyles.risk}`}>긴급</i>
            )}
          </div>
          <SupportRequestFacts request={data} />
          <section className={complaintStyles.responses}>
            <h3>진행 이력</h3>
            <ResponseList request={data} />
          </section>
        </>
      ) : (
        <SkeletonDetail label="상세 내용을 불러오는 중입니다." height={320} />
      )}
    </Shell>
  )
}

export function SalesDealPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, error, reload } = useDetail<SalesDealResponse>(
    `/sales-deals/${encodeURIComponent(id)}`,
  )
  const deal = data && toSalesDeal(data)
  return (
    <Shell
      title={deal?.org ?? '영업 딜 상세'}
      href={dealDetailPath(id)}
      error={error}
      onRetry={reload}
      onClose={onClose}
    >
      {deal ? (
        <SalesDealDetail deal={deal} />
      ) : (
        <SkeletonDetail label="영업 딜 상세를 불러오는 중입니다." height={340} />
      )}
    </Shell>
  )
}

/** 상품관리는 팀장만 들어가는 화면이라 '화면에서 열기' 없이 읽기만 합니다. */
export function ProductPanel({
  id,
  name,
  onClose,
}: {
  id: string
  name: string
  onClose: () => void
}) {
  return (
    <Shell title={name} error={false} onRetry={() => {}} onClose={onClose}>
      <ProductSummary picked={{ id, name }} />
    </Shell>
  )
}

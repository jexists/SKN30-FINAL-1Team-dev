import type { ReactNode } from 'react'
import { Link } from 'react-router'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { SkeletonDetail } from '@/components/Skeleton'
import StageChip, { chipOr } from '@/components/StageChip'
import { ROUTES } from '@/constants/routes'
import type { ColumnTone } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'
import { wonFull } from '@/utils/format'

import type { SalesDeal } from './useSalesDeals'

import styles from './SalesDealForm.module.scss'

interface Props {
  deal: SalesDeal | null
  stage?: { name: string; tone: ColumnTone }
  loading: boolean
  error: string | null
  onRetry: () => void
  onEdit?: () => void
  onDelete?: () => void
  /** 견적·계약 칸의 수정 단추. 주지 않으면 읽기만 합니다. */
  onEditQuote?: () => void
  onEditContract?: () => void
  onClose: () => void
}

const dash = (value: string | null) => value ?? '-'
const day = (value: string | null) => (value === null ? '-' : fmtDot(parseISO(value)))
const money = (value: number | null) => (value === null ? '-' : wonFull(value))

export default function SalesDealDrawer({
  deal,
  stage,
  loading,
  error,
  onRetry,
  onEdit,
  onDelete,
  onEditQuote,
  onEditContract,
  onClose,
}: Props) {
  const readOnly = deal?.pipelineStatus === 'archived'
  const facts = deal
    ? [
        ['파이프라인', deal.pipelineName],
        ['제품', deal.product],
        ['금액', wonFull(deal.amount)],
        ['담당 영업', deal.owner],
        ['고객 담당자', deal.contactName ?? '미지정'],
        ['지역', deal.region],
        ['영업 시작일', fmtDot(parseISO(deal.date))],
        [
          '미팅 대상자',
          deal.participants.length === 0
            ? '미지정'
            : deal.participants.map((one) => one.customer_contact_name).join(', '),
        ],
      ]
    : []

  return (
    <Drawer
      title={deal?.org ?? '영업 딜 상세'}
      sub={deal ? `${deal.no} · ${deal.title}` : undefined}
      meta={
        deal && (
          <>
            {stage && <StageChip tone={stage.tone}>{stage.name}</StageChip>}
            <span>{deal.kind}</span>
          </>
        )
      }
      footer={
        deal && !loading && !error && !readOnly && onEdit && onDelete ? (
          <>
            <Button variant="outline" onClick={onEdit}>
              수정
            </Button>
            <Button variant="outline" onClick={onDelete}>
              삭제
            </Button>
          </>
        ) : undefined
      }
      onClose={onClose}
    >
      {error ? (
        <div className={styles.drawerState} role="alert">
          <p>{error}</p>
          <Button variant="outline" onClick={onRetry}>
            다시 시도
          </Button>
        </div>
      ) : loading ? (
        <SkeletonDetail label="영업 딜 상세를 불러오는 중입니다." height={340} />
      ) : deal ? (
        <>
          {readOnly && <p className={styles.memoEmpty}>보관된 파이프라인 · 읽기 전용</p>}
          <dl className={styles.drawerFacts}>
            {facts.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd className={label === '금액' || label === '영업 시작일' ? 'tnum' : undefined}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          {deal.memo ? (
            <p className={styles.memo}>{deal.memo}</p>
          ) : (
            <p className={styles.memoEmpty}>메모가 없습니다.</p>
          )}

          {/* 견적 → 계약 → 발주. 세 값이 모두 같은 행에 남아 있어 여기서 한눈에 봅니다. */}
          <DocumentSection
            title="견적"
            tone={deal.quoteStatusTone}
            status={deal.quoteStatusName}
            emptyText="아직 견적을 작성하지 않았습니다."
            onEdit={readOnly ? undefined : onEditQuote}
            facts={[
              ['견적번호', dash(deal.quoteNo)],
              ['견적일', day(deal.quoteIssuedOn)],
              ['유효기한', day(deal.quoteValidUntil)],
              ['견적금액', money(deal.quoteAmount)],
              ['납품예상일자', dash(deal.quoteDeliveryTerms)],
            ]}
          >
            {deal.items.length > 0 && (
              <ul className={styles.drawerItems}>
                {deal.items.map((item) => (
                  <li key={item.id}>
                    <span>{item.product_name}</span>
                    <span className="tnum">
                      {item.quantity}개 × {wonFull(item.unit_price)}
                    </span>
                    <span className="tnum">{wonFull(item.quantity * item.unit_price)}</span>
                  </li>
                ))}
              </ul>
            )}
          </DocumentSection>

          <DocumentSection
            title="계약"
            tone={deal.contractStatusTone}
            status={deal.contractStatusName}
            emptyText="아직 계약을 작성하지 않았습니다."
            onEdit={readOnly ? undefined : onEditContract}
            facts={[
              ['계약번호', dash(deal.contractNo)],
              ['계약일', day(deal.contractSignedOn)],
              ['계약 종료일', day(deal.contractEndsOn)],
              ['계약금액', money(deal.contractAmount)],
              ['보증 조건', dash(deal.warrantyTerms)],
            ]}
          />

          <DocumentSection
            title="발주"
            tone={deal.orderStatusTone}
            status={deal.orderStatusName}
            emptyText="아직 발주가 없습니다."
            facts={[]}
          >
            {deal.orderStatusName !== null && (
              // 발주는 딜 하나에 여러 건일 수 있어 값을 펼치지 않고 목록으로 보냅니다.
              <Link className={styles.drawerLink} to={`${ROUTES.ORDERS}?q=${deal.no}`}>
                이 딜의 발주 보기
              </Link>
            )}
          </DocumentSection>
        </>
      ) : (
        <p className={styles.drawerState}>영업 딜 상세 정보가 없습니다.</p>
      )}
    </Drawer>
  )
}

interface SectionProps {
  title: string
  tone: ColumnTone | null
  status: string | null
  emptyText: string
  facts: [string, string][]
  onEdit?: () => void
  children?: ReactNode
}

/** 딜 하나가 지나는 서류 한 칸. 상태가 없으면 아직 그 단계가 아니라는 뜻입니다. */
function DocumentSection({
  title,
  tone,
  status,
  emptyText,
  facts,
  onEdit,
  children,
}: SectionProps) {
  return (
    <section className={styles.drawerSection}>
      <header className={styles.drawerSectionHead}>
        <h3>{title}</h3>
        {chipOr(tone, status)}
        {onEdit && (
          <Button variant="ghost" onClick={onEdit}>
            {status === null ? '작성' : '수정'}
          </Button>
        )}
      </header>

      {status === null ? (
        <p className={styles.memoEmpty}>{emptyText}</p>
      ) : (
        <>
          {facts.length > 0 && (
            <dl className={styles.drawerFacts}>
              {facts.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          )}
          {children}
        </>
      )}
    </section>
  )
}

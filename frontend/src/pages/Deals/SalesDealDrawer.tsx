import type { ReactNode } from 'react'
import { Link } from 'react-router'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import Select from '@/components/Select'
import { SkeletonDetail } from '@/components/Skeleton'
import StageChip, { chipOr } from '@/components/StageChip'
import stageTone from '@/components/StageChip/StageChip.module.scss'
import { ROUTES } from '@/constants/routes'
import type { ColumnTone } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'
import { wonFull } from '@/utils/format'

import type { SalesDeal, SalesDealColumn } from './useSalesDeals'

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
  /** 발주 칸의 등록 단추. 발주는 여러 건이라 언제나 새로 담습니다. */
  onAddOrder?: () => void
  /**
   * 단계 고르개. 보드와 같은 단계 목록을 그대로 받습니다. 둘 다 주지 않으면
   * 지금까지처럼 단계를 읽기만 합니다.
   */
  stages?: SalesDealColumn[]
  onStageSelect?: (stage: SalesDealColumn) => void
  stagePending?: boolean
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
  onAddOrder,
  stages,
  onStageSelect,
  stagePending = false,
  onClose,
}: Props) {
  const readOnly = deal?.pipelineStatus === 'archived'
  // 서류는 견적 → 계약 → 발주 순서로 갑니다. 앞 서류가 없으면 뒤 칸은 보이지 않습니다.
  const hasQuote =
    deal !== null &&
    (deal.quoteStatusName !== null || deal.quoteAmount !== null || deal.quoteMemo !== null)
  const hasContract =
    deal !== null &&
    (deal.contractStatusName !== null || deal.contractAmount !== null || deal.contractMemo !== null)
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
        deal &&
        stage &&
        // 단계는 여기서 바로 바꿉니다. 배지와 같은 톤 색을 고르개에 그대로 씁니다.
        (stages && onStageSelect && !readOnly ? (
          <Select
            label="현재 단계"
            className={[styles.stageSelect, stageTone[stage.tone]].filter(Boolean).join(' ')}
            size="sm"
            value={deal.stageId}
            options={stages.map((one) => ({ value: one.id, label: one.name }))}
            disabled={stagePending}
            onChange={(next) => {
              const picked = stages.find((one) => one.id === next)
              if (picked && picked.id !== deal.stageId) onStageSelect(picked)
            }}
          />
        ) : (
          <StageChip tone={stage.tone}>{stage.name}</StageChip>
        ))
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
            hasValue={hasQuote}
            facts={[
              ['견적번호', dash(deal.quoteNo)],
              ['견적일', day(deal.quoteIssuedOn)],
              ['유효기한', day(deal.quoteValidUntil)],
              ['견적금액', money(deal.quoteAmount)],
              ['납품예상일자', dash(deal.quoteDeliveryTerms)],
              ['메모', dash(deal.quoteMemo)],
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

          {hasQuote && (
            <DocumentSection
              title="계약"
              tone={deal.contractStatusTone}
              status={deal.contractStatusName}
              emptyText="아직 계약을 작성하지 않았습니다."
              onEdit={readOnly ? undefined : onEditContract}
              hasValue={hasContract}
              facts={[
                ['계약번호', dash(deal.contractNo)],
                ['계약일', day(deal.contractSignedOn)],
                ['계약 종료일', day(deal.contractEndsOn)],
                ['계약금액', money(deal.contractAmount)],
                ['보증 조건', dash(deal.warrantyTerms)],
                ['메모', dash(deal.contractMemo)],
              ]}
            />
          )}

          {hasContract && (
            <DocumentSection
              title="발주"
              tone={deal.orderStatusTone}
              status={deal.orderStatusName}
              emptyText="아직 발주가 없습니다."
              onEdit={readOnly ? undefined : onAddOrder}
              editLabel="등록"
              hasValue={deal.orderMemo !== null}
              facts={deal.orderMemo === null ? [] : [['메모', deal.orderMemo]]}
            >
              {deal.orderStatusName !== null && (
                // 발주는 딜 하나에 여러 건일 수 있어 값을 펼치지 않고 목록으로 보냅니다.
                <Link className={styles.drawerLink} to={`${ROUTES.ORDERS}?q=${deal.no}`}>
                  이 딜의 발주 보기
                </Link>
              )}
            </DocumentSection>
          )}
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
  /** 상태는 아직 없지만 단계를 옮기며 적어 둔 값이 있는지. 있으면 그것을 보입니다. */
  hasValue?: boolean
  onEdit?: () => void
  editLabel?: string
  children?: ReactNode
}

/** 딜 하나가 지나는 서류 한 칸. 상태가 없으면 아직 그 단계가 아니라는 뜻입니다. */
function DocumentSection({
  title,
  tone,
  status,
  emptyText,
  facts,
  hasValue = false,
  onEdit,
  editLabel,
  children,
}: SectionProps) {
  return (
    <section className={styles.drawerSection}>
      <header className={styles.drawerSectionHead}>
        <h3>{title}</h3>
        {chipOr(tone, status)}
        {onEdit && (
          <Button variant="ghost" onClick={onEdit}>
            {editLabel ?? (status === null ? '작성' : '수정')}
          </Button>
        )}
      </header>

      {status === null && !hasValue ? (
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

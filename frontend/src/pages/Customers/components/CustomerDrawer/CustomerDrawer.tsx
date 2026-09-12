import { useState, type ReactNode } from 'react'

import Drawer from '@/components/Drawer'
import { DocumentsIcon, EditIcon, MoreIcon, TrashIcon } from '@/components/icons'
import ImageLightbox from '@/components/ImageLightbox'
import Popover from '@/components/Popover'
import useCompanyDeals from '@/hooks/useCompanyDeals'
import useCustomerAttachments from '@/pages/Customers/useCustomerAttachments'
import useCustomerCompany from '@/pages/Customers/useCustomerCompany'
import { regionLabel } from '@/shared/regionCodes'
import type { Customer, CustomerAttachment, CustomerCompanyResponse } from '@/types'
import { sizeLabel } from '@/utils/attachment'
import { fmtDay, parseISO } from '@/utils/date'
import { formatBusinessNo, formatPhone } from '@/utils/format'

import CustomerDeals from './CustomerDeals'
import styles from './CustomerDrawer.module.scss'

interface Props {
  customer: Customer
  /** 삭제는 팀장만 합니다. 아니면 메뉴에서 아예 빼고, 막는 일은 백엔드가 다시 합니다. */
  canDelete: boolean
  onEdit: () => void
  onDelete: () => void
  onClose: () => void
}

interface BlockProps {
  title: string
  children: ReactNode
}

function Block({ title, children }: BlockProps) {
  return (
    <section className={styles.block}>
      <h3>{title}</h3>
      {children}
    </section>
  )
}

const shown = (value: string | null | undefined): string => value || '—'

/** 회사 주소 한 줄. 등록 폼에서 보던 것과 같은 모양입니다. */
function companyAddress(company: CustomerCompanyResponse | null): string {
  if (company === null || !company.address) return '—'
  const head = company.postcode ? `(${company.postcode}) ${company.address}` : company.address
  return company.address_detail ? `${head} ${company.address_detail}` : head
}

const KIND_LABEL: Record<CustomerAttachment['kind'], string> = {
  business_card: '명함',
  business_license: '사업자등록증',
}

/**
 * 등록에 쓴 원본 한 건. 사진은 어느 명함인지 알아볼 만큼만 줄여 놓고, 크게 볼 일은
 * 눌러서 전체보기로 엽니다. PDF 는 미리 보여 줄 수 없어 같은 크기의 자리에 받는 길만 둡니다.
 * 둘을 같은 타일로 맞춰 두면 첨부가 늘어도 세로로 길어지지 않고 옆으로 늡니다.
 *
 * 사진이어도 href 는 그대로 둡니다. 가운데 클릭이나 주소 복사로 원본을 따로 여는 길이
 * 남고, 자바스크립트가 늦게 붙어도 링크로는 열립니다.
 */
function Attachment({ attachment }: { attachment: CustomerAttachment }) {
  const [zoom, setZoom] = useState(false)
  const label = KIND_LABEL[attachment.kind]
  const image = attachment.media_type?.startsWith('image/') === true

  return (
    <figure className={styles.shot}>
      <a
        className={styles.tile}
        href={attachment.url}
        target="_blank"
        rel="noopener noreferrer"
        title={image ? `${label} 크게 보기` : `${label} 원본 받기`}
        onClick={
          image
            ? (event) => {
                event.preventDefault()
                setZoom(true)
              }
            : undefined
        }
      >
        {image ? (
          <img src={attachment.url} alt={`${label} 원본`} />
        ) : (
          <span className={styles.doc}>
            <DocumentsIcon width={20} height={20} />
            원본 받기
          </span>
        )}
      </a>
      <figcaption className={styles.shotNote}>
        {label} · {sizeLabel(attachment.byte_size)}
      </figcaption>
      {zoom && (
        <ImageLightbox
          src={attachment.url}
          alt={`${label} 원본`}
          caption={`${label} · ${sizeLabel(attachment.byte_size)}`}
          onClose={() => setZoom(false)}
        />
      )}
    </figure>
  )
}

export default function CustomerDrawer({ customer, canDelete, onEdit, onDelete, onClose }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  // 딜은 사람이 아니라 회사에 걸립니다. 고객을 바꾸면 companyId 가 바뀌어 다시 받아 옵니다.
  const { deals, loading, error, reload } = useCompanyDeals(customer.companyId)
  // 명함은 이 사람의 것이고, 사업자등록증은 이 회사의 것입니다. 서버가 함께 줍니다.
  const attachments = useCustomerAttachments(customer.id)
  // 사업자 등록번호와 주소는 회사에 붙어 있습니다. 고객 응답에는 들어 있지 않습니다.
  const company = useCustomerCompany(customer.companyId)

  // 담당자가 여럿이면 상세에서는 전부 보여 줍니다. 좁은 표와 달리 자리가 있습니다.
  const ownerNames =
    customer.owners !== undefined && customer.owners.length > 0
      ? customer.owners.map((owner) => owner.name)
      : [customer.owner]

  const facts: [string, string][] = [
    ['부서', shown(customer.dept)],
    ['직함', shown(customer.title)],
    ['담당자', ownerNames.join(', ')],
    ['상태', customer.status],
    ['유입 경로', customer.source],
    ['방문', customer.visited ? '방문' : '미방문'],
    ['등록일', fmtDay(parseISO(customer.created))],
  ]

  return (
    <Drawer
      wide
      title={customer.name}
      sub={[customer.org, customer.dept, customer.title].filter(Boolean).join(' · ')}
      resetKey={customer.id}
      onClose={onClose}
      actions={
        <Popover
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
          align="end"
          compact
          label="고객 메뉴"
          trigger={
            <button
              type="button"
              className={styles.menuBtn}
              aria-label="고객 메뉴"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((value) => !value)}
            >
              <MoreIcon width={18} height={18} />
            </button>
          }
        >
          <div className={styles.menu}>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false)
                onEdit()
              }}
            >
              <EditIcon width={15} height={15} />
              수정
            </button>
            {canDelete && (
              <button
                type="button"
                className={styles.danger}
                onClick={() => {
                  setMenuOpen(false)
                  onDelete()
                }}
              >
                <TrashIcon width={15} height={15} />
                삭제
              </button>
            )}
          </div>
        </Popover>
      }
      meta={
        <>
          <i
            className={`${styles.pill} ${
              customer.status === '계약'
                ? styles.good
                : customer.status === '보류'
                  ? styles.hold
                  : ''
            }`}
          >
            {customer.status}
          </i>
          <i className={styles.pill}>유입 {customer.source}</i>
          <span className={styles.when}>담당 {customer.owner}</span>
        </>
      }
    >
      <div className={styles.grid}>
        <div className={styles.col}>
          <Block title="연락처">
            <dl className={styles.facts}>
              <div>
                <dt>전화</dt>
                <dd>
                  <a className={`${styles.mail} tnum`} href={`tel:${customer.phone}`}>
                    {formatPhone(customer.phone)}
                  </a>
                </dd>
              </div>
              <div>
                <dt>휴대폰</dt>
                <dd>
                  {customer.telephone ? (
                    <a className={`${styles.mail} tnum`} href={`tel:${customer.telephone}`}>
                      {formatPhone(customer.telephone)}
                    </a>
                  ) : (
                    <span className={styles.muted}>—</span>
                  )}
                </dd>
              </div>
              {/* 팩스는 거는 번호가 아니라 링크로 두지 않습니다. */}
              <div>
                <dt>팩스</dt>
                <dd className="tnum">
                  {customer.fax ? (
                    formatPhone(customer.fax)
                  ) : (
                    <span className={styles.muted}>—</span>
                  )}
                </dd>
              </div>
              <div>
                <dt>이메일</dt>
                <dd>
                  {customer.email ? (
                    <a className={styles.mail} href={`mailto:${customer.email}`}>
                      {customer.email}
                    </a>
                  ) : (
                    <span className={styles.muted}>등록된 이메일 없음</span>
                  )}
                </dd>
              </div>
            </dl>
          </Block>

          <Block title="회사 정보">
            <dl className={styles.facts}>
              <div>
                <dt>회사</dt>
                <dd>{customer.org}</dd>
              </div>
              <div>
                <dt>사업자번호</dt>
                <dd className="tnum">{shown(formatBusinessNo(company?.business_no))}</dd>
              </div>
              <div>
                <dt>주소</dt>
                <dd>{companyAddress(company)}</dd>
              </div>
              <div>
                <dt>지역</dt>
                {/* 화면에 보이는 건 코드가 아니라 "서울"입니다. */}
                <dd>{regionLabel(customer.regionCode ?? null)}</dd>
              </div>
            </dl>
          </Block>
        </div>

        <div className={styles.col}>
          <Block title="고객 정보">
            <dl className={styles.facts}>
              {facts.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </Block>

          <Block title="메모">
            <p className={`${styles.note} ${customer.memo ? '' : styles.muted}`}>
              {customer.memo || '등록된 메모가 없습니다.'}
            </p>
          </Block>
        </div>
      </div>

      <section className={styles.deals}>
        <h3>
          영업 현황
          {deals.length > 0 && <span className={styles.blockNote}>{deals.length}건</span>}
        </h3>
        <CustomerDeals
          deals={deals}
          loading={loading}
          error={error}
          onRetry={reload}
          contactId={customer.id}
        />
      </section>

      {/* 직접 등록한 고객에는 원본이 없습니다. 빈 자리를 남기지 않고 통째로 뺍니다. */}
      {attachments.length > 0 && (
        <section className={styles.attach}>
          <h3>
            첨부 자료
            <span className={styles.blockNote}>{attachments.length}건</span>
          </h3>
          <div className={styles.shots}>
            {attachments.map((attachment) => (
              <Attachment key={attachment.file_id} attachment={attachment} />
            ))}
          </div>
        </section>
      )}
    </Drawer>
  )
}

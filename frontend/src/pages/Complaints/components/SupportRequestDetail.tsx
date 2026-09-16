// CS 대응 상세의 읽기 부분. CS 대응 화면의 드로어와 대시보드 목록의 옆 패널이 함께 씁니다.
import type { SupportRequestResponse } from '@/types'

import styles from '../Complaints.module.scss'

const dateOf = (value: string) => new Date(value)

const dateTime = new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

export function SupportRequestFacts({ request }: { request: SupportRequestResponse }) {
  return (
    <dl className={styles.rows}>
      <div>
        <dt>회사</dt>
        <dd>{request.customer_company_name}</dd>
      </div>
      <div>
        <dt>딜선택</dt>
        <dd>
          <span className="tnum">{request.contract_no ?? request.deal_no}</span> ·{' '}
          {request.deal_title}
        </dd>
      </div>
      <div>
        <dt>제품</dt>
        <dd>{request.product_name ?? '미지정'}</dd>
      </div>
      <div>
        <dt>워런티</dt>
        <dd>{request.warranty_terms ?? '없음'}</dd>
      </div>
      <div>
        <dt>등록한 사람</dt>
        <dd>{request.assignee_display_name}</dd>
      </div>
      <div>
        <dt>발생일시</dt>
        <dd>{dateTime.format(dateOf(request.occurred_at))}</dd>
      </div>
      <div>
        <dt>등록일시</dt>
        <dd>{dateTime.format(dateOf(request.registered_at))}</dd>
      </div>
      {/* 한 번도 고치지 않았으면 서지 않습니다. 고친 적이 있다는 사실만 보이고,
          고치기 전 값은 서버에 백업으로만 남습니다. */}
      {request.updated_at !== null && (
        <div>
          <dt>수정일시</dt>
          <dd>{dateTime.format(dateOf(request.updated_at))}</dd>
        </div>
      )}
      <div>
        <dt>내용</dt>
        <dd>{request.body}</dd>
      </div>
    </dl>
  )
}

export function ResponseList({ request }: { request: SupportRequestResponse }) {
  return request.responses.length === 0 ? (
    <p className={styles.noResponses}>등록된 진행 이력이 없습니다.</p>
  ) : (
    <ol>
      {request.responses.map((response) => (
        <li key={response.id}>
          <div>
            <strong>{response.responder_display_name}</strong>
            <time dateTime={response.responded_at}>
              {dateTime.format(dateOf(response.responded_at))}
            </time>
          </div>
          <p>{response.body}</p>
        </li>
      ))}
    </ol>
  )
}

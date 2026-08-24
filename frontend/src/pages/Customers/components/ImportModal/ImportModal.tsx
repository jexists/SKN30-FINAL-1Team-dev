import { useRef, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import Button from '@/components/Button'
import { UploadIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import type {
  CustomerCompanyCreateRequest,
  CustomerCompanyResponse,
  CustomerContactCreateRequest,
} from '@/types'
import { parseCsv } from '@/utils/csv'
import { businessNoDigits } from '@/utils/format'

import styles from './ImportModal.module.scss'

/** CSV 헤더 ↔ 고객 등록 폼의 칸. 내보내기가 쓰는 이름과 같아 왕복이 됩니다. */
const HEADER_MAP = {
  회사: 'org',
  '사업자 등록번호': 'businessNo',
  이름: 'name',
  전화: 'phone',
  부서: 'dept',
  직함: 'title',
  이메일: 'email',
  방문여부: 'visited',
  메모: 'memo',
} as const

type Header = keyof typeof HEADER_MAP
type Field = (typeof HEADER_MAP)[Header]

const SAMPLE_HEADERS = Object.keys(HEADER_MAP).join(', ')
const REQUIRED: Record<'name' | 'org' | 'phone', string> = {
  name: '이름',
  org: '회사',
  phone: '전화',
}
const PREVIEW_ROWS = 5
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

interface Column {
  field: Field
  header: string
  index: number
}

interface Parsed {
  filename: string
  /** 알아본 헤더의 열 위치 */
  fields: Column[]
  ignored: string[]
  rows: string[][]
}

/** 한 줄을 읽어 본 결과. 보낼 수 없는 줄은 이유를 달고 남습니다. */
interface Row {
  line: number
  values: Record<Field, string>
  problem: string | null
}

interface Failure {
  line: number
  reason: string
}

interface Progress {
  done: number
  total: number
  failures: Failure[]
}

function readRow(cells: string[], at: Map<Field, number>, line: number): Row {
  const pick = (field: Field) => {
    const index = at.get(field)
    return index === undefined ? '' : (cells[index] ?? '').trim()
  }
  const values: Record<Field, string> = {
    org: pick('org'),
    businessNo: pick('businessNo'),
    name: pick('name'),
    phone: pick('phone'),
    dept: pick('dept'),
    title: pick('title'),
    email: pick('email'),
    visited: pick('visited'),
    memo: pick('memo'),
  }

  // 고객 등록 폼과 같은 규칙입니다. 여기서 걸러야 서버 왕복을 헛되이 쓰지 않습니다.
  return { line, values, problem: problemOf(values) }
}

function problemOf(values: Record<Field, string>): string | null {
  if (values.name === '') return '이름이 비어 있습니다.'
  if (values.org === '') return '회사가 비어 있습니다.'
  if (values.phone === '') return '전화가 비어 있습니다.'
  if (values.email !== '' && !EMAIL.test(values.email)) {
    return '이메일 형식이 맞지 않습니다. 예: name@company.com'
  }
  if (values.businessNo !== '' && businessNoDigits(values.businessNo).length !== 10) {
    return '사업자 등록번호는 숫자 10자리입니다. 예: 123-45-67890'
  }
  return null
}

const optional = (value: string): string | null => value || null

interface ImportModalProps {
  onClose: () => void
  /** 한 명이라도 들어왔을 때. 목록을 다시 받습니다. */
  onImported: (added: number) => void
}

export default function ImportModal({ onClose, onImported }: ImportModalProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  // 같은 회사가 여러 줄에 나옵니다. 이름당 한 번만 서버에 묻고 결과를 들고 있습니다.
  const companyIds = useRef(new Map<string, string>())
  const [parsed, setParsed] = useState<Parsed | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [sending, setSending] = useState(false)

  const ready = rows.filter((row) => row.problem === null)
  const skipped = rows.filter((row) => row.problem !== null)

  const readFile = async (file: File) => {
    setError(null)
    setParsed(null)
    setRows([])
    setProgress(null)

    const table = parseCsv(await file.text())
    if (table.length < 2) {
      setError(
        '첫 줄에 열 이름, 그 아래에 고객이 한 줄씩 있어야 합니다. 지금은 데이터 줄이 없습니다.',
      )
      return
    }

    const headers = table[0].map((header) => header.trim())
    const fields = headers
      .map((header, index) => ({ header, index, field: HEADER_MAP[header as Header] }))
      .filter((column): column is Column => column.field !== undefined)

    const missing = Object.keys(REQUIRED).filter(
      (field) => !fields.some((column) => column.field === field),
    ) as (keyof typeof REQUIRED)[]
    if (missing.length > 0) {
      const names = missing.map((field) => REQUIRED[field]).join(', ')
      setError(`${names} 열을 찾지 못했습니다. 첫 줄의 열 이름을 확인하세요.`)
      return
    }

    const at = new Map(fields.map((column) => [column.field, column.index]))
    const body = table.slice(1)

    companyIds.current.clear()
    setParsed({
      filename: file.name,
      fields,
      ignored: headers.filter(
        (header) => HEADER_MAP[header as Header] === undefined && header !== '',
      ),
      rows: body,
    })
    // 첫 줄이 열 이름이므로 데이터 첫 줄은 파일에서 2번째 줄입니다.
    setRows(body.map((cells, index) => readRow(cells, at, index + 2)))
  }

  const resolveCompanyId = async (name: string, businessNo: string) => {
    const cached = companyIds.current.get(name)
    if (cached !== undefined) return cached

    const payload: CustomerCompanyCreateRequest = {
      name,
      region_code: null,
      business_no: businessNoDigits(businessNo) || null,
    }
    // 이미 있는 이름이면 백엔드가 기존 회사를 그대로 돌려줍니다.
    const { data } = await client.post<CustomerCompanyResponse>('/customer-companies', payload)
    companyIds.current.set(name, data.id)
    return data.id
  }

  const send = async () => {
    if (sending || ready.length === 0) return

    setSending(true)
    setError(null)

    const failures: Failure[] = []
    let done = 0
    setProgress({ done, total: ready.length, failures })

    // 한 줄씩 보냅니다. 한꺼번에 던지면 같은 회사를 여러 번 만들고 서버도 함께 밀립니다.
    for (const row of ready) {
      try {
        const payload: CustomerContactCreateRequest = {
          company_id: await resolveCompanyId(row.values.org, row.values.businessNo),
          name: row.values.name,
          department: optional(row.values.dept),
          job_title: optional(row.values.title),
          email: optional(row.values.email),
          phone: row.values.phone,
          status_code: 'new',
          source_code: null,
          memo: optional(row.values.memo),
          // 방문이라고 적힌 줄만 방문입니다. 비어 있으면 아직 만나기 전입니다.
          visited: row.values.visited === '방문',
        }
        await client.post('/customer-contacts', payload)
        done += 1
      } catch (caught: unknown) {
        failures.push({ line: row.line, reason: errorMessage(caught, '등록하지 못했습니다.') })
      }
      setProgress({ done, total: ready.length, failures: [...failures] })
    }

    setSending(false)
    if (done > 0) onImported(done)
  }

  const close = () => {
    if (!sending) onClose()
  }

  const confirmLabel = () => {
    if (sending) return `${progress?.done ?? 0} / ${ready.length}명 등록 중…`
    if (parsed === null) return '파일을 먼저 선택하세요'
    if (ready.length === 0) return '등록할 줄이 없습니다'
    return `${ready.length}명 등록`
  }

  return (
    <Modal
      title="엑셀로 고객 등록"
      description="Excel 에서 CSV(UTF-8)로 저장한 파일을 넣으면 한 줄이 고객 한 명이 됩니다."
      onClose={close}
      size="lg"
      footer={
        <>
          <Button type="button" variant="outline" disabled={sending} onClick={close}>
            {progress === null ? '취소' : '닫기'}
          </Button>
          <Button type="button" disabled={sending || ready.length === 0} onClick={send}>
            {confirmLabel()}
          </Button>
        </>
      }
    >
      <input
        ref={fileRef}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) void readFile(file)
          // 같은 파일을 고쳐서 다시 고르면 change 가 뜨지 않습니다.
          event.target.value = ''
        }}
      />

      <button
        type="button"
        className={styles.drop}
        disabled={sending}
        onClick={() => fileRef.current?.click()}
      >
        <UploadIcon width={28} height={28} strokeWidth={1.5} />
        <strong>{parsed ? parsed.filename : 'CSV 파일 선택'}</strong>
        <span>열 이름: {SAMPLE_HEADERS}</span>
      </button>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {parsed && (
        <div className={styles.result}>
          <p className={styles.summary}>
            <span className="tnum">{parsed.rows.length}</span>줄을 읽었습니다. 담당자는 등록하는
            사람으로, 상태는 신규로 넣습니다. 방문여부는 방문이라고 적힌 줄만 방문이 됩니다.
            {parsed.ignored.length > 0 && (
              <> 알아보지 못한 열은 건너뜁니다 — {parsed.ignored.join(', ')}</>
            )}
          </p>

          {skipped.length > 0 && (
            <ul className={styles.problems}>
              {skipped.slice(0, PREVIEW_ROWS).map((row) => (
                <li key={row.line}>
                  <b className="tnum">{row.line}번째 줄</b> {row.problem}
                </li>
              ))}
              {skipped.length > PREVIEW_ROWS && (
                <li>
                  보내지 않는 줄이 모두 {skipped.length}개입니다. 위 {PREVIEW_ROWS}개만 보여 줍니다.
                </li>
              )}
            </ul>
          )}

          <div className={styles.previewWrap}>
            <table className={styles.preview}>
              <thead>
                <tr>
                  {parsed.fields.map((column) => (
                    <th key={column.header} scope="col">
                      {column.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {parsed.rows.slice(0, PREVIEW_ROWS).map((cells, index) => (
                  <tr key={index}>
                    {parsed.fields.map((column) => (
                      <td key={column.header}>{cells[column.index] ?? ''}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {parsed.rows.length > PREVIEW_ROWS && (
            <p className={styles.more}>
              위 {PREVIEW_ROWS}줄만 미리 보여 줍니다. 나머지 {parsed.rows.length - PREVIEW_ROWS}
              줄도 함께 보냅니다.
            </p>
          )}
        </div>
      )}

      {progress && (
        <div className={styles.result} role="status">
          <p className={styles.summary}>
            <span className="tnum">{progress.done}</span>명을 등록했습니다.
            {progress.failures.length > 0 && (
              <> 등록하지 못한 줄이 {progress.failures.length}개 있습니다.</>
            )}
          </p>
          {progress.failures.length > 0 && (
            <ul className={styles.problems}>
              {progress.failures.slice(0, PREVIEW_ROWS).map((failure) => (
                <li key={failure.line}>
                  <b className="tnum">{failure.line}번째 줄</b> {failure.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Modal>
  )
}

import { useRef, useState } from 'react'

import Button from '@/components/Button'
import { UploadIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import {
  CUSTOMER_OWNERS,
  CUSTOMER_SOURCES,
  CUSTOMER_STATUSES,
  toCustomer,
} from '@/content/customers'
import type { Customer, CustomerSeed } from '@/content/types'
import { parseCsv } from '@/utils/csv'

import styles from './ImportModal.module.scss'

/** CSV 헤더 ↔ 고객 항목. 내보내기가 쓰는 컬럼 이름과 같아 왕복이 됩니다. */
const HEADER_MAP: Record<string, keyof CustomerSeed> = {
  이름: 'name',
  회사: 'org',
  부서: 'dept',
  직함: 'title',
  이메일: 'email',
  전화: 'phone',
  '담당 영업': 'owner',
  '유입 소스': 'source',
  상태: 'status',
  메모: 'memo',
}

const SAMPLE_HEADERS = Object.keys(HEADER_MAP).join(', ')
const PREVIEW_ROWS = 5

interface Parsed {
  filename: string
  /** 알아본 헤더의 열 위치 */
  fields: { field: keyof CustomerSeed; header: string; index: number }[]
  ignored: string[]
  rows: string[][]
}

interface ImportModalProps {
  onClose: () => void
  onImport: (customers: Customer[]) => void
}

export default function ImportModal({ onClose, onImport }: ImportModalProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [parsed, setParsed] = useState<Parsed | null>(null)
  const [error, setError] = useState<string | null>(null)

  const readFile = async (file: File) => {
    setError(null)
    setParsed(null)

    const table = parseCsv(await file.text())
    if (table.length < 2) {
      setError(
        '첫 줄에 열 이름, 그 아래에 고객이 한 줄씩 있어야 합니다. 지금은 데이터 줄이 없습니다.',
      )
      return
    }

    const headers = table[0].map((h) => h.trim())
    const fields = headers
      .map((header, index) => ({ header, index, field: HEADER_MAP[header] }))
      .filter((h) => h.field !== undefined)

    if (!fields.some((f) => f.field === 'name')) {
      setError(`'이름' 열을 찾지 못했습니다. 첫 줄의 열 이름을 확인하세요.`)
      return
    }

    setParsed({
      filename: file.name,
      fields,
      ignored: headers.filter((h) => HEADER_MAP[h] === undefined && h !== ''),
      rows: table.slice(1),
    })
  }

  const confirm = () => {
    if (!parsed) return

    // 항목 → 열 위치를 한 번만 만들어 두고 모든 줄이 같이 씁니다.
    const at = new Map(parsed.fields.map((f) => [f.field, f.index]))

    const added = parsed.rows.map((cells, i) => {
      const pick = (field: keyof CustomerSeed) => {
        const index = at.get(field)
        return index === undefined ? '' : (cells[index] ?? '').trim()
      }

      const status = pick('status')
      const source = pick('source')
      const owner = pick('owner')

      return toCustomer({
        id: `FM-CU-IMP-${Date.now()}-${i}`,
        name: pick('name'),
        org: pick('org'),
        dept: pick('dept'),
        title: pick('title'),
        email: pick('email'),
        phone: pick('phone'),
        // 모르는 값이 들어오면 목록의 필터가 깨지므로 기본값으로 받습니다.
        owner: CUSTOMER_OWNERS.includes(owner) ? owner : CUSTOMER_OWNERS[0],
        source: CUSTOMER_SOURCES.find((s) => s === source) ?? '소개',
        status: CUSTOMER_STATUSES.find((s) => s === status) ?? '신규',
        lastOff: 0,
        nextOff: null,
        createdOff: 0,
        memo: pick('memo'),
      })
    })

    onImport(added.filter((c) => c.name !== ''))
  }

  return (
    <Modal
      title="엑셀 가져오기"
      description="Excel 에서 CSV(UTF-8)로 저장한 파일을 넣으면 목록에 추가합니다."
      onClose={onClose}
      size="lg"
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="button" disabled={parsed === null} onClick={confirm}>
            {parsed ? `${parsed.rows.length}명 추가` : '파일을 먼저 선택하세요'}
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
        }}
      />

      <button type="button" className={styles.drop} onClick={() => fileRef.current?.click()}>
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
            <span className="tnum">{parsed.rows.length}</span>줄을 읽었습니다. 날짜 열은 가져오지
            않고, 최근 접촉과 등록일은 오늘로 둡니다.
            {parsed.ignored.length > 0 && (
              <> 알아보지 못한 열은 건너뜁니다 — {parsed.ignored.join(', ')}</>
            )}
          </p>

          <div className={styles.previewWrap}>
            <table className={styles.preview}>
              <thead>
                <tr>
                  {parsed.fields.map((f) => (
                    <th key={f.header} scope="col">
                      {f.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {parsed.rows.slice(0, PREVIEW_ROWS).map((cells, index) => (
                  <tr key={index}>
                    {parsed.fields.map((f) => (
                      <td key={f.header}>{cells[f.index] ?? ''}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {parsed.rows.length > PREVIEW_ROWS && (
            <p className={styles.more}>
              위 {PREVIEW_ROWS}줄만 미리 보여 줍니다. 나머지 {parsed.rows.length - PREVIEW_ROWS}
              줄도 함께 추가됩니다.
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}

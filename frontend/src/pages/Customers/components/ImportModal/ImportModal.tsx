import { useRef, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { UploadIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import type { CustomerContactBulkItem, CustomerContactBulkResult } from '@/types'
import { downloadCsv, parseCsv, toCsv } from '@/utils/csv'
import { TODAY_ISO } from '@/utils/date'

import {
  HEADER_MAP,
  HEADERS,
  MAX_ROWS,
  REQUIRED,
  toBulkItem,
  type Field,
  type Header,
} from '../../importCustomers'
import styles from './ImportModal.module.scss'
import RecognitionLoading from '../RecognitionLoading'

/** 빈 템플릿을 내려받습니다. 내보내기와 같은 CSV(UTF-8) 규칙을 씁니다. */
function downloadTemplate() {
  downloadCsv(`고객등록_템플릿_${TODAY_ISO}.csv`, toCsv(HEADERS, []))
}

interface Column {
  field: Field
  header: string
  index: number
}

/** 알아본 열에서 한 줄의 값을 뽑습니다. 없는 열은 빈 값입니다. */
function readValues(cells: string[], at: Map<Field, number>): Record<Field, string> {
  const pick = (field: Field) => {
    const index = at.get(field)
    return index === undefined ? '' : (cells[index] ?? '').trim()
  }
  return {
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
}

/*
 * 등록하지 못한 몫. 줄마다 무엇이 문제인지 늘어놓아도 사용자가 여기서 고칠 수는 없고,
 * 몇 명이 왜 빠졌는지만 알면 파일을 고쳐 다시 올립니다. 그래서 한 갈래에 한 줄로 셉니다.
 */
function skipped(result: CustomerContactBulkResult): string[] {
  const notes: string[] = []
  if (result.duplicate > 0) notes.push(`${result.duplicate}명은 이미 등록된 고객입니다.`)
  if (result.invalid > 0) notes.push(`${result.invalid}명은 입력한 내용에 오류가 있습니다.`)
  if (result.failed > 0) notes.push(`${result.failed}명은 등록하지 못했습니다.`)
  return notes
}

interface ImportModalProps {
  onClose: () => void
  /** 한 명이라도 들어왔을 때. 목록을 다시 받습니다. */
  onImported: (result: CustomerContactBulkResult) => void
}

export default function ImportModal({ onClose, onImported }: ImportModalProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [filename, setFilename] = useState<string | null>(null)
  const [count, setCount] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<CustomerContactBulkResult | null>(null)
  const [parsing, setParsing] = useState(false)
  const [sending, setSending] = useState(false)

  /*
   * 읽은 줄을 전부 한 번에 보냅니다. 어떤 줄을 등록할지는 줄마다 서버가 봅니다.
   * 파일 안에서 같은 사람이 여러 번 나오는 경우도 한 요청 안에서 봐야 걸러집니다.
   */
  const send = async (items: CustomerContactBulkItem[]) => {
    setSending(true)
    try {
      const { data } = await client.post<CustomerContactBulkResult>('/customer-contacts/bulk', {
        items,
      })
      setResult(data)
      onImported(data)
    } catch (caught: unknown) {
      setError(errorMessage(caught, '고객을 등록하지 못했습니다.'))
    } finally {
      setSending(false)
    }
  }

  /*
   * 파일을 고르면 그대로 보냅니다. 보내기 전에 한 번 더 보여 줘도 사용자가 손볼 것은
   * 없고, 몇 명이 왜 빠졌는지는 등록한 뒤 결과에 남습니다.
   * 여기서 막는 것은 아예 보낼 수 없는 파일뿐입니다.
   */
  const readFile = async (file: File) => {
    if (parsing || sending) return

    setParsing(true)
    setError(null)
    setFilename(file.name)
    setCount(0)
    setResult(null)

    try {
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

      const body = table.slice(1)
      if (body.length > MAX_ROWS) {
        setError(
          `한 번에 ${MAX_ROWS.toLocaleString()}명까지 등록할 수 있습니다. 파일을 나눠서 올려 주세요.`,
        )
        return
      }

      const at = new Map(fields.map((column) => [column.field, column.index]))
      // 첫 줄이 열 이름이므로 데이터 첫 줄은 파일에서 2번째 줄입니다.
      const items = body.map((cells, index) => toBulkItem(index + 2, readValues(cells, at)))
      setCount(items.length)
      setParsing(false)
      await send(items)
    } catch {
      setError('엑셀 파일을 읽지 못했습니다. CSV(UTF-8) 파일인지 확인해 주세요.')
    } finally {
      setParsing(false)
    }
  }

  const close = () => {
    if (!parsing && !sending) onClose()
  }

  const notes = result ? skipped(result) : []
  /*
   * 제목은 등록이 어떻게 끝났는지만 말하고, 몇 명이 어떻게 되었는지는 본문이 셉니다.
   * 한 명도 못 들어왔는데 "완료"라고 하면 목록을 열어 보고 나서야 알게 됩니다.
   */
  const heading =
    result === null
      ? '엑셀로 고객 등록'
      : result.success === 0
        ? '등록 실패'
        : notes.length > 0
          ? '일부 등록 완료'
          : '등록 완료'

  return (
    <Modal title={heading} description="" onClose={close} size={result === null ? 'lg' : 'md'}>
      {/*
        고르는 자리는 고를 때만 둡니다. 읽는 중에는 누를 수 없고 등록이 끝나면 같은 파일을
        다시 올릴 일이 없어, 남겨 두면 아직 할 일이 있는 것처럼 읽힙니다.
      */}
      {result === null && !parsing && !sending && (
        <>
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
          <button type="button" className={styles.drop} onClick={() => fileRef.current?.click()}>
            <UploadIcon width={22} height={22} strokeWidth={1.5} />
            <strong>{filename ?? 'CSV 파일 선택'}</strong>
          </button>
          <button type="button" className={styles.template} onClick={downloadTemplate}>
            엑셀 템플릿 다운로드
          </button>
        </>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {(parsing || sending) && (
        <RecognitionLoading
          description={
            parsing
              ? '엑셀 파일에서 고객 정보를 확인하고 있습니다.'
              : `${count}명 고객을 등록하고 있습니다.`
          }
        />
      )}

      {result && (
        <div className={styles.result} role="status">
          <p className={styles.lead}>
            {result.success > 0 ? `${result.success}명 등록했습니다.` : '등록한 고객이 없습니다.'}
          </p>
          {notes.map((note) => (
            <p key={note} className={styles.note}>
              {note}
            </p>
          ))}
        </div>
      )}
    </Modal>
  )
}

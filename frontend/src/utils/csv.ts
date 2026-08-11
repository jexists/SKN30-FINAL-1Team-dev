// CSV 읽기·쓰기. 라이브러리 없이 RFC 4180 의 필요한 부분만 다룹니다.

// Excel 은 BOM 이 없으면 CSV 를 시스템 기본 인코딩으로 읽어 한글을 깨뜨립니다.
const BOM = '﻿'

function escapeCell(value: string): string {
  // 쉼표·따옴표·줄바꿈이 있으면 감싸고, 안쪽 따옴표는 두 번 씁니다.
  if (/[",\r\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`
  return value
}

/** 헤더 한 줄 + 데이터 줄들. 줄바꿈은 Excel 호환을 위해 CRLF 입니다. */
export function toCsv(headers: string[], rows: string[][]): string {
  const lines = [headers, ...rows].map((cells) => cells.map(escapeCell).join(','))
  return BOM + lines.join('\r\n')
}

/** 브라우저에서 파일로 내려받습니다. */
export function downloadCsv(filename: string, csv: string) {
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  // 붙잡고 있으면 파일 내용이 메모리에 계속 남습니다.
  URL.revokeObjectURL(url)
}

/**
 * CSV 텍스트를 행 배열로 만듭니다.
 * 따옴표 안의 쉼표·줄바꿈을 보존해야 해서 split 대신 한 글자씩 훑습니다.
 */
export function parseCsv(text: string): string[][] {
  const source = text.startsWith(BOM) ? text.slice(1) : text
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false

  for (let i = 0; i < source.length; i += 1) {
    const ch = source[i]

    if (quoted) {
      if (ch !== '"') {
        cell += ch
      } else if (source[i + 1] === '"') {
        cell += '"'
        i += 1
      } else {
        quoted = false
      }
      continue
    }

    if (ch === '"') {
      quoted = true
    } else if (ch === ',') {
      row.push(cell)
      cell = ''
    } else if (ch === '\n' || ch === '\r') {
      // CRLF 는 두 글자이므로 \n 을 건너뜁니다.
      if (ch === '\r' && source[i + 1] === '\n') i += 1
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else {
      cell += ch
    }
  }

  if (cell !== '' || row.length > 0) {
    row.push(cell)
    rows.push(row)
  }

  // 끝의 빈 줄은 데이터가 아닙니다.
  return rows.filter((r) => r.some((c) => c.trim() !== ''))
}

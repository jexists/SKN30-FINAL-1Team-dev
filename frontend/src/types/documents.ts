/** 자료실 문서의 분류. 탭과 정렬 순서는 Documents/catalog.ts 가 정합니다. */
export type DocumentCategory = '계약서' | '발주서' | '상품설명서' | '견적서' | '기타'

/** 파일 종류. 확장자를 이만큼으로 뭉쳐 배지 하나로 보여 줍니다. */
export type DocumentFileKind = 'pdf' | 'doc' | 'sheet' | 'slide' | 'image' | 'etc'

/**
 * 문서가 붙어 있는 대상. 아무 데도 붙지 않은 문서는 kind 가 'none' 입니다.
 *
 * 새로 고를 수 있는 것은 '상품' 과 '딜' 뿐입니다. '고객사' 와 '발주' 는 예전에 붙인
 * 자료가 목록에서 연결을 잃지 않도록 읽기 쪽에만 남겨 둡니다.
 */
export interface DocumentLink {
  kind: 'none' | '상품' | '딜' | '고객사' | '발주'
  /** 연결 대상의 id. 고르는 순간 손에 들어옵니다. kind 가 'none' 이면 빈 문자열입니다. */
  id: string
  /** '초음파 진단기' 또는 'SL-DL-2026-0038'. kind 가 'none' 이면 빈 문자열입니다. */
  label: string
}

/** 한 번의 업로드. 최신 것이 목록에 보이고 나머지는 드로어 이력에 남습니다. */
export interface DocumentVersionSeed {
  version: number
  fileName: string
  /** 바이트. 화면에 찍을 때 sizeLabel() 로 바꿉니다. */
  bytes: number
  owner: string
  /** 오늘로부터 며칠. 지난 일이므로 0 이하입니다. */
  uploadedOff: number
  /** 이 버전에서 무엇이 바뀌었는지 한 줄 */
  note: string
}

export interface DocumentVersion extends Omit<DocumentVersionSeed, 'uploadedOff'> {
  id?: string
  documentId?: string
  /** YYYY-MM-DD */
  uploaded: string
  /** 이 세션에서 올린 파일만 갖습니다. 시드에는 없어 내려받을 수 없습니다. */
  blob?: File
  processingStatus?: DocumentProcessingStatus
  processingError?: string | null
}

export interface SalesDocumentSeed {
  id: string
  title: string
  category: DocumentCategory
  kind: DocumentFileKind
  link: DocumentLink
  /** 화면의 '메모'. 목록에서 이 자료가 무엇인지 알아볼 한 줄입니다. */
  description: string
  /** 오래된 것부터. 마지막이 현재 버전입니다. */
  versions: DocumentVersionSeed[]
}

/** 실제 날짜가 붙은 자료실 문서 */
export interface SalesDocument extends Omit<SalesDocumentSeed, 'versions'> {
  documentNo?: string
  versions: DocumentVersion[]
}

export type DocumentProcessingStatus = 'uploaded' | 'processing' | 'completed' | 'failed'

export interface DocumentFileResponse {
  id: string
  version_no: number
  file_name: string
  media_type: string | null
  byte_size: number
  processing_status: DocumentProcessingStatus
  processing_error?: string | null
  uploaded_by_member_id: string
  uploaded_by_display_name: string
  note: string | null
  uploaded_at: string
}

export interface DocumentSummaryResponse {
  file_id: string
  file_name: string
  processing_status: DocumentProcessingStatus
  processing_error: string | null
  extracted_text: string | null
  extracted_markdown: string | null
  extracted_payload: Record<string, unknown> | null
  summary_markdown: string | null
  summary_payload: Record<string, unknown> | null
  processed_at: string | null
}

export interface DocumentResponse {
  id: string
  document_no: string
  category_code: string
  title: string
  description: string | null
  customer_company_id: string | null
  customer_company_name: string | null
  sales_deal_id: string | null
  sales_deal_no: string | null
  purchase_order_id: string | null
  product_id: string | null
  product_name: string | null
  created_by_member_id: string
  created_by_display_name: string
  created_at: string
  files: DocumentFileResponse[]
  latest_version_no: number | null
}

export interface DownloadResponse {
  url: string
  expires_in: number
  file_name: string
  media_type: string | null
  byte_size: number
}

/** 자료실 문서의 분류. 탭과 정렬 순서는 Documents/catalog.ts 가 정합니다. */
export type DocumentCategory = '계약서' | '발주서' | '상품설명서' | '견적서' | '기타'

/** 파일 종류. 확장자를 이만큼으로 뭉쳐 배지 하나로 보여 줍니다. */
export type DocumentFileKind = 'pdf' | 'doc' | 'sheet' | 'slide' | 'image' | 'etc'

/** 문서가 붙어 있는 대상. 아무 데도 붙지 않은 문서는 kind 가 'none' 입니다. */
export interface DocumentLink {
  kind: 'none' | '고객사' | '계약' | '발주'
  /** '한빛대학교병원' 또는 'FM-CT-2026-0038'. kind 가 'none' 이면 빈 문자열입니다. */
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
}

export interface SalesDocumentSeed {
  id: string
  title: string
  category: DocumentCategory
  kind: DocumentFileKind
  link: DocumentLink
  description: string
  tags: string[]
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
  uploaded_by_member_id: string
  uploaded_by_display_name: string
  note: string | null
  uploaded_at: string
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
  purchase_order_id: string | null
  tags: string[]
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

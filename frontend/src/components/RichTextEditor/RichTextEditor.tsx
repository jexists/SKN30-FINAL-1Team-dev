// 본문 한 덩어리를 그대로 쓰는 편집기. TinyMCE 는 자체 호스팅(GPL) 으로 씁니다.
//
// 미팅보고서(pages/Meetings/components/ReportDocument)와 같은 라이브러리를 쓰지만 목적이
// 다릅니다. 저쪽은 항목 제목이 잠긴 문서를 고치고 결과를 항목별 값으로 쪼갭니다. 여기는
// HTML 한 덩어리를 그대로 주고받습니다. 두 화면을 한 컴포넌트로 묶으면 서로의 회귀 원인이
// 되므로 나눠 둡니다.
//
// 허용 태그(valid_elements)는 서버 app/services/html_sanitize.py 의 허용목록과 한 쌍입니다.
// 한쪽만 넓히면 화면에서 넣은 것이 저장할 때 조용히 사라집니다.
import { useRef, useState } from 'react'
import { Editor } from '@tinymce/tinymce-react'

import 'tinymce/tinymce'
import 'tinymce/models/dom/model'
import 'tinymce/themes/silver'
import 'tinymce/icons/default'
import 'tinymce/plugins/lists'
import 'tinymce/plugins/link'
import 'tinymce/plugins/image'
import 'tinymce/plugins/autolink'
// 스킨 CSS 는 번들에 담습니다. 주소로 받아 오게 두면 빌드 결과에서 경로가 어긋납니다.
import 'tinymce/skins/ui/oxide/skin.min.css'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { NoticeImageResponse } from '@/types'

import styles from './RichTextEditor.module.scss'

// 서버(upload_guard._IMAGE_ALLOWED, notices.NOTICE_IMAGE_MAX_BYTES)와 같게 둡니다.
const IMAGE_MAX_BYTES = 5 * 1024 * 1024

interface Props {
  value: string
  onChange: (html: string) => void
  disabled?: boolean
  /**
   * 본문을 통째로 다시 세워야 할 때만 올립니다. 편집 중에는 절대 바뀌면 안 됩니다.
   * ReportDocument 와 같은 이유입니다. 글자를 칠 때마다 initialValue 를 새로 넘기면
   * 편집기가 본문을 갈아 끼워 커서가 앞으로 돌아가고 한글 조합이 끊깁니다.
   */
  docKey?: number
  height?: number
  label?: string
}

export default function RichTextEditor({
  value,
  onChange,
  disabled = false,
  docKey = 0,
  height = 320,
  label = '본문',
}: Props) {
  const [uploadError, setUploadError] = useState<string | null>(null)

  const doc = useRef<{ key: number; html: string } | null>(null)
  if (doc.current === null || doc.current.key !== docKey) {
    doc.current = { key: docKey, html: value }
  }

  return (
    <div className={styles.root}>
      <Editor
        key={docKey}
        initialValue={doc.current.html}
        disabled={disabled}
        // 자체 호스팅 GPL 이용임을 밝힙니다. 없으면 편집기가 경고를 띄웁니다.
        licenseKey="gpl"
        onEditorChange={onChange}
        init={{
          // 보고서와 달리 iframe 을 씁니다. 인쇄할 일이 없고, 본문 CSS 가 관리 화면
          // 스타일과 섞이지 않아야 합니다.
          inline: false,
          height,
          skin: false,
          promotion: false,
          branding: false,
          menubar: false,
          statusbar: false,
          plugins: 'lists link image autolink',
          toolbar:
            'bold italic underline | bullist numlist | blockquote | link image | removeformat',
          // 서버 html_sanitize._TAGS/_ATTRIBUTES 와 같은 목록입니다.
          // rel 은 두지 않습니다. 서버가 link_rel 로 noopener 를 직접 붙입니다.
          valid_elements:
            'p,br,strong/b,em/i,u,s,ul,ol,li,blockquote,h2,h3,h4,' +
            'a[href|title|target],img[src|alt|title|width|height]',
          // 워드·한글에서 붙여 넣는 서식 쓰레기를 걸러 냅니다.
          paste_data_images: true,
          // 사진은 고르는 즉시 저장소로 올리고 본문에는 내부 참조만 남깁니다.
          automatic_uploads: true,
          images_file_types: 'png,jpg,jpeg,webp',
          images_upload_handler: async (blobInfo) => {
            const blob = blobInfo.blob()
            if (blob.size > IMAGE_MAX_BYTES) {
              throw new Error('사진은 5MB까지 올릴 수 있습니다.')
            }
            const form = new FormData()
            form.append('upload', blob, blobInfo.filename())
            try {
              const { data } = await client.post<NoticeImageResponse>('/notices/images', form)
              setUploadError(null)
              // 저장소 주소가 아니라 우리 내부 참조입니다. 볼 수 있는 주소는 서버가
              // 본문을 내보낼 때마다 새로 발급합니다.
              return data.url
            } catch (caught: unknown) {
              const message = errorMessage(caught, '사진을 올리지 못했습니다.')
              setUploadError(message)
              throw new Error(message)
            }
          },
          link_default_target: '_blank',
          link_default_protocol: 'https',
          a11y_advanced_options: true,
          content_style:
            'body{font-family:inherit;font-size:14px;line-height:1.7}img{max-width:100%;height:auto}',
        }}
      />
      <span className="sr-only">{label}</span>
      {uploadError !== null && (
        <p className={styles.error} role="alert">
          {uploadError}
        </p>
      )}
    </div>
  )
}

// 최종 보고서 본문. 항목별 입력칸이 아니라 문서 한 편을 통째로 고칩니다.
//
// 저장되는 모양은 그대로 항목별 값입니다. 여기서는 보기 좋게 이어 붙여 보여 주고,
// 고칠 때마다 다시 항목으로 쪼개 위로 올립니다. 변환은 reportDocument.ts 가 맡습니다.
//
// TinyMCE 는 자체 호스팅(GPL) 으로 씁니다. 클라우드 CDN 과 API 키를 쓰지 않습니다.
import { useRef, useState } from 'react'
import { Editor } from '@tinymce/tinymce-react'

import 'tinymce/tinymce'
import 'tinymce/models/dom/model'
import 'tinymce/themes/silver'
import 'tinymce/icons/default'
import 'tinymce/plugins/lists'
// 스킨 CSS 는 번들에 담습니다. TinyMCE 가 주소로 받아 오게 두면 base_url 을 따로
// 맞춰야 하고, 빌드 결과에서 경로가 어긋납니다.
import 'tinymce/skins/ui/oxide/skin.min.css'

import type { ReportTemplate } from '@/types'

import type { DocumentHtml } from '../../reportDocument'
import { LOCKED_CLASS, toHtml, toMarkdown, toValues } from '../../reportDocument'

import styles from './ReportDocument.module.scss'

interface Props {
  template: ReportTemplate
  values: Record<string, string>
  /** 문서를 통째로 다시 세워야 할 때 올라갑니다. 편집 중에는 절대 바뀌지 않아야 합니다. */
  docKey: number
  disabled: boolean
  onChange: (values: Record<string, string>, missingSections: string[]) => void
}

export default function ReportDocument({ template, values, docKey, disabled, onChange }: Props) {
  // 툴바를 제자리에 세웁니다. inline 기본값은 본문 위에 떠서 보고서 제목과 첫
  // 항목을 가립니다. 자리를 미리 잡아 두고 그 안에 그리게 합니다.
  const [toolbar, setToolbar] = useState<HTMLDivElement | null>(null)

  /*
   * 편집기에 넣을 내용을 docKey 마다 한 번씩만 만들어 붙들어 둡니다.
   *
   * 글자를 칠 때마다 values 가 새로 오는데, 그때마다 initialValue 를 다시 만들어
   * 넘기면 편집기가 본문을 통째로 갈아 끼웁니다. 그러면 커서가 문단 앞으로
   * 돌아가 글자가 거꾸로 쌓입니다. 그래서 편집 중에는 붙들어 두고,
   * 문서를 통째로 갈아야 할 때(docKey) 만 지금 값으로 다시 만듭니다.
   *
   * 마운트 때 한 번만 만들면 안 됩니다. 아래 Editor 는 key 로 다시 서지만 이
   * 컴포넌트는 그대로 남아, AI 원본 적용·제목 되살리기·다시 쓰기에서 옛 내용이
   * 그대로 다시 들어갑니다(= 새 값이 화면에 나타나지 않습니다).
   */
  const doc = useRef<({ key: number } & DocumentHtml) | null>(null)
  if (doc.current === null || doc.current.key !== docKey) {
    doc.current = { key: docKey, ...toHtml(template, values) }
  }

  return (
    <div className={styles.root}>
      {/* 자리가 먼저 있어야 편집기가 그 안에 툴바를 그립니다. */}
      <div className={styles.toolbar} ref={setToolbar} />

      {toolbar && (
        <Editor
          // key 가 바뀔 때만 새 내용으로 다시 섭니다. 편집 중에 initialValue 를 갈면
          // 커서가 처음으로 돌아가고 한글 조합이 끊깁니다.
          key={docKey}
          initialValue={doc.current.html}
          disabled={disabled}
          // 자체 호스팅 GPL 이용임을 밝힙니다. 없으면 편집기가 경고를 띄웁니다.
          // (init.license_key 가 아니라 래퍼의 prop 으로 넘겨야 합니다)
          licenseKey="gpl"
          onEditorChange={(html) => {
            const parsed = toValues(template, toMarkdown(html), doc.current?.sections)
            onChange(parsed.values, parsed.missingSections)
          }}
          init={{
            // iframe 이 아니라 이 자리에서 바로 고칩니다. 인쇄(= PDF 다운로드)가
            // iframe 안을 담지 못하기 때문이고, 흰 시트 자체가 편집면이 되어야
            // 문서를 고치는 화면으로 읽힙니다.
            inline: true,
            skin: false,
            content_css: false,
            promotion: false,
            branding: false,
            menubar: false,
            statusbar: false,
            plugins: 'lists',
            // 보고서에 필요한 것만 둡니다. 색·글꼴·표·이미지는 넣지 않습니다.
            toolbar: 'bold italic | bullist numlist | removeformat',
            // 항목 제목은 문서의 뼈대입니다. 지우면 아래 글이 어느 항목인지 알 수
            // 없어지므로 아예 손대지 못하게 막습니다.
            noneditable_class: LOCKED_CLASS,
            // 편집기가 스스로 만드는 것 없이, 우리가 준 태그만 씁니다.
            // 워드·한글에서 붙여 넣는 일이 잦습니다. 허용 목록을 좁혀 두면 서식 쓰레기가
            // 값에 섞여 들어오지 않습니다.
            valid_elements: 'p,br,strong/b,em/i,ul,ol,li,h2[class]',
            fixed_toolbar_container_target: toolbar,
          }}
        />
      )}
    </div>
  )
}

import { reportBodyHtml } from '@/shared/reportMarkdown'

import styles from './ReportBody.module.scss'

export default function ReportBody({ body, className = '' }: { body: string; className?: string }) {
  return (
    <div
      className={`${styles.root} ${className}`.trim()}
      dangerouslySetInnerHTML={{ __html: reportBodyHtml(body) }}
    />
  )
}

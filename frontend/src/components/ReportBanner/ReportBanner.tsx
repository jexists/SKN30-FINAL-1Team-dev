// 보고서 화면의 머리 띠. 어디에서 왔는지, 어느 기간의 무슨 보고서인지, 지금 어디까지
// 왔는지, 그리고 이 문서로 할 수 있는 일을 한 줄에 함께 답니다.
//
// 작성 화면과 상세 화면이 같은 것을 씁니다. 둘이 다르면 같은 보고서가 쓸 때와 읽을 때
// 다른 문서처럼 보입니다.
import { Fragment, type ReactNode } from 'react'

import styles from './ReportBanner.module.scss'

type Props = {
  /** 이 보고서가 놓인 목록으로 돌아가는 길. */
  crumb?: ReactNode
  /** 기간. 2026.09.15 (화) 또는 9월 3주. */
  title: ReactNode
  /** 종류. 기간에 딸린 말이라 한 단계 작게 섭니다. */
  kind: string
  /** 상태 배지. 아직 상태가 없는 새 보고서에서는 비웁니다. */
  badge?: ReactNode
  /** 아이콘과 값 한 쌍씩. 사이의 구분선은 이 컴포넌트가 넣습니다. */
  meta: ReactNode[]
  /** 머리 띠 오른쪽 끝에 서는 조작부. */
  children?: ReactNode
}

export default function ReportBanner({ crumb, title, kind, badge, meta, children }: Props) {
  return (
    <header className={styles.banner}>
      <div className={styles.heading}>
        {crumb}

        <p className={styles.title}>
          {title}
          <span>{kind}</span>
          {badge}
        </p>

        <p className={styles.meta}>
          {meta.map((item, index) => (
            <Fragment key={index}>
              {/* 좁은 폭에서는 첫 구분선이 줄바꿈 자리가 됩니다. */}
              {index > 0 && (
                <span
                  className={index === 1 ? `${styles.bar} ${styles.breakBar}` : styles.bar}
                  aria-hidden="true"
                />
              )}
              <span className={styles.metaItem}>{item}</span>
            </Fragment>
          ))}
        </p>
      </div>

      <div className={styles.actions}>{children}</div>
    </header>
  )
}

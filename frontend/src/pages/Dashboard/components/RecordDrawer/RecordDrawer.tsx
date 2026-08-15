// demo/layout_v3.html 의 #recordDrawer 입니다.
// 일정 하나에 대해 알아야 할 것을 한 장에 모읍니다. 세부 정보는 왼쪽,
// 지난 접촉은 오른쪽이고 브리핑은 아래에 한 줄로 넓게 깝니다.
//
// 보고서 작성 폼은 여기 넣지 않습니다. 미팅 기록은 첨부와 AI 구조화가 붙어
// 드로어 한 장에 담기지 않으므로 하단 버튼으로 작성 화면으로 넘깁니다.
import { Link } from 'react-router'

import Drawer from '@/components/Drawer'
import { CheckIcon } from '@/components/icons'
import { statusScope } from '@/content/agenda'
import type { AgendaItem } from '@/content/types'
import { meetingComposePath, meetingReportPath } from '@/constants/routes'
import useMeetingReports from '@/pages/Meetings/useMeetingReports'
import { fmtDay, parseISO } from '@/utils/date'

import styles from './RecordDrawer.module.scss'

interface Props {
  item: AgendaItem
  done: boolean
  onToggleDone: (id: string) => void
  onClose: () => void
}

export default function RecordDrawer({ item, done, onToggleDone, onClose }: Props) {
  const { findByAgenda } = useMeetingReports()
  // 이 자리에서 쓴 기록이 있으면 새로 쓰지 않고 그것을 엽니다.
  const saved = findByAgenda(item.id)

  const facts: [string, string][] = [
    ['부서', item.dept],
    ['담당자', item.contact],
    ['제품', item.product],
    ['장소', item.place],
  ]

  return (
    <Drawer
      wide
      title={item.hospital}
      sub={
        <>
          {item.title}
          <span className={styles.when}>
            · {fmtDay(parseISO(item.date))} {item.time}
          </span>
        </>
      }
      onClose={onClose}
      meta={
        <>
          {/* 배지는 DayAgenda 목록과 종류·순서·색이 모두 같아야 합니다.
              목록에서 본 줄을 그대로 펼친 것으로 읽혀야 하기 때문입니다. */}
          <i
            className={`${styles.pill} ${statusScope(item.stage) === '외부' ? styles.scopeExternal : ''}`}
          >
            {item.stage}
          </i>
          {done && <i className={`${styles.pill} ${styles.doneTag}`}>완료</i>}
          {done && !saved && (
            <i className={`${styles.pill} ${styles.needsReport}`}>보고서 미작성</i>
          )}
        </>
      }
      footer={
        <>
          {/* 일정을 끝냈는지는 목록을 훑다가가 아니라 상세를 열어 확인한 뒤
              정합니다. 드로어를 닫기 전 마지막으로 누르는 자리에 둡니다. */}
          <button
            type="button"
            className={styles.doneBtn}
            aria-pressed={done}
            aria-label={done ? '완료 취소' : '이 일정을 완료로 표시'}
            onClick={() => onToggleDone(item.id)}
          >
            {done && <CheckIcon width={14} height={14} />}
            {done ? '완료' : '완료 확인'}
          </button>

          <Link
            className={styles.cta}
            to={saved ? meetingReportPath(saved.id) : meetingComposePath(item.id)}
          >
            {saved ? '미팅보고서 열기' : '미팅보고서 작성'}
          </Link>
        </>
      }
    >
      <div className={styles.grid}>
        <section className={styles.block}>
          <h3>세부 정보</h3>
          <dl className={styles.facts}>
            {facts.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className={styles.block}>
          <h3>고객 히스토리</h3>
          {item.history.map((h) => (
            <div key={`${h.when}-${h.what}`} className={styles.history}>
              <time>{h.when}</time>
              <p>{h.what}</p>
            </div>
          ))}
        </section>

        {/* 브리핑은 문장이 길어 두 열을 가로질러 한 줄로 깝니다. */}
        <section className={`${styles.block} ${styles.full}`}>
          <h3>AI 미팅 브리핑</h3>
          <p className={styles.note}>{item.brief}</p>
        </section>
      </div>
    </Drawer>
  )
}

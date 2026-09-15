// 브리핑이 도는 동안 세우는 한 줄. 보고서 진행 화면과 같은 것을 씁니다 — 같은 종류의
// 기다림이 자리에 따라 다른 모양으로 나오면 사람이 두 번 배워야 합니다.
import ActivityList from '@/pages/Meetings/components/GenerationProgress/ActivityList'
import useLiveDetail from '@/pages/Meetings/components/GenerationProgress/useLiveDetail'

/*
 * 돌려 보여 줄 문구.
 *
 * 서버는 브리핑 실행의 단계를 내려주지 않습니다(queued·running·completed 뿐). 그래서 지나온
 * 단계를 완료로 쌓지 않고 살아 있는 줄 하나만 세웁니다. 문구는 에이전트가 실제로 하는 일
 * 안에서만 씁니다(backend/app/agents/contract_management.py 의 generate_briefing —
 * 딜·일정 스냅샷, read_recent_reports, search_historical_reports, 본문 작성).
 */
const PHRASES = [
  '고객사의 딜과 일정을 모으는 중',
  '최근 보고서를 읽는 중',
  '과거 보고서를 검색하는 중',
  '브리핑을 쓰는 중',
]

/** @param runKey 지금 도는 실행을 가리키는 값. 바뀌면 초를 처음부터 다시 셉니다. */
export default function BriefingProgress({ runKey }: { runKey: string }) {
  const live = useLiveDetail(runKey, PHRASES)
  return (
    <ActivityList
      label="AI 브리핑 진행"
      rows={[
        {
          key: 'briefing',
          label: live.phrase ?? 'AI 브리핑 준비 중',
          state: 'live',
          // 갓 시작한 줄에 '0초' 를 달지 않습니다. 기다림이 느껴질 때부터 셉니다.
          detail: live.seconds >= 3 ? `${live.seconds}초` : undefined,
        },
      ]}
    />
  )
}

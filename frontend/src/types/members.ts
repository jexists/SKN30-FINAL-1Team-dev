/** 담당자 선택 같은 화면 목록이 쓰는 팀원 한 명. `GET /team-members` 응답입니다. */
export interface TeamMemberOption {
  id: string
  display_name: string
  /** 부서는 팀 단위 값이라 팀원마다 같습니다. 구분에는 직함을 씁니다. */
  job_title: string | null
  role_code: 'member' | 'manager'
}

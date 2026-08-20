import type { ReportTemplate } from '@/types'

export const meetingTemplate: ReportTemplate = {
  id: 'builtin-meeting',
  name: '기본 미팅 기록 양식',
  owner: '',
  updated: '',
  fields: [
    {
      id: 'attendees',
      label: '참석자',
      type: 'text',
      required: true,
      aiFilled: true,
      placeholder: '참석자를 입력하세요.',
    },
    {
      id: 'reaction',
      label: '고객 반응',
      type: 'textarea',
      required: true,
      aiFilled: true,
      placeholder: '제품·조건에 대한 반응을 입력하세요.',
    },
    {
      id: 'decision',
      label: '결정사항',
      type: 'textarea',
      required: true,
      aiFilled: true,
      placeholder: '합의한 내용을 입력하세요.',
    },
    {
      id: 'next',
      label: '다음 행동 · 기한',
      type: 'textarea',
      required: true,
      aiFilled: true,
      placeholder: '누가 언제까지 무엇을 하는지 입력하세요.',
    },
    {
      id: 'note',
      label: '특이사항',
      type: 'text',
      required: false,
      aiFilled: false,
      placeholder: '직접 확인한 내용만 입력하세요.',
    },
  ],
}

import type { ReportTemplate } from '@/types'

export const meetingFreeformTemplate: ReportTemplate = {
  id: 'builtin-meeting-freeform',
  name: '미팅 보고서',
  owner: '',
  updated: '',
  fields: [
    {
      id: 'body',
      label: '보고서 본문',
      type: 'textarea',
      required: true,
      aiFilled: true,
      placeholder: '미팅에서 논의한 내용을 입력하세요.',
    },
  ],
}

// 약관·개인정보처리방침·법적고지가 함께 쓰는 값입니다. 본문 여러 곳에 흩어지면
// 서비스명 하나 바꾸는 데도 문서 세 벌을 뒤져야 해서 여기 모아 둡니다.
//
// 회사명, 사업자 정보, 개인정보 보호책임자, 수탁업체는 가상의 값입니다.
// 실서비스 전에 실제 값으로 바꾸고 법무 검토를 거쳐야 합니다.
export const LEGAL = {
  service: 'SalesLuv',
  company: '셀럽(SalesLove)',
  effectiveDate: '2026년 8월 6일',
  business: {
    name: '주식회사 셀럽',
    ceo: '이도현',
    registration: '123-45-67890',
    mailOrder: '제2026-서울강남-01234호',
    address: '서울특별시 강남구 테헤란로 123, 8층',
    support: 'support@salesluv.co.kr · 평일 09:00~18:00',
  },
  officer: {
    name: '김서준',
    title: '서비스운영팀장',
    email: 'privacy@salesluv.co.kr',
    phone: '02-1234-5678',
  },
  processors: [
    { name: '(주)클라우드베이스', work: '서비스 서버 및 데이터베이스 운영' },
    { name: '(주)페이링크', work: '요금 청구 및 결제 처리' },
  ],
} as const

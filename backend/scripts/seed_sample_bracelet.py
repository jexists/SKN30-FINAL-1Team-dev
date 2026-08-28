"""브레이스 영업1팀(테스트1)에 3개월치 샘플 업무 데이터를 반복 가능하게 넣는다.

기존 4개 계정(bt1·bt2·bt3·jungia21)이 2026-06-01 부터 2026-08-25 까지 CRM 을 실제로
써 온 것처럼 고객 → 딜(영업·견적·계약) → 활동 → 보고서 → 발주 → 매출이 이어지는 데이터를
만든다. 실제 고객 데이터가 아니며 이메일과 전화번호도 통신 불가능한 값이다.

담당자는 이메일로 조회해 실제 member.id 를 쓴다. 새 계정을 만들지 않는다.
새로 넣는 행의 id 는 모두 uuid5(팀 id, "sample2026q3:...") 라 다시 실행해도 같은 행을
갱신할 뿐 늘어나지 않고, 이번 샘플분만 골라낼 수 있다.

    uv run python -m scripts.seed_sample_bracelet [--dry-run]
"""

import argparse
import asyncio
from datetime import date, datetime, time, timedelta
from typing import Any, NamedTuple
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.models.configuration import (
    ActivityActionTag,
    ActivityCategory,
    CustomerContactStatus,
    PurchaseOrderStatus,
    SalesDealType,
)
from app.models.content import Report, ReportActivity
from app.models.crm import (
    Activity,
    CustomerCompany,
    CustomerContact,
    CustomerContactAssignee,
    SupportRequest,
    SupportResponse,
)
from app.models.sales import (
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesDeal,
    SalesPipeline,
    SalesPipelineStage,
    SalesTarget,
)
from app.models.workspace import Member, Notice, NoticeTarget, Team
from scripts.seed_demo_auth import seed_team_configuration

SEED_TAG = "sample2026q3"
TEAM_NAME = "테스트1"
SEOUL = ZoneInfo("Asia/Seoul")
TODAY = date(2026, 8, 25)

# 담당자는 이메일로 찾는다. 표시 이름은 확인용이며 다르면 중단한다.
OWNER_EMAILS = {
    "김팀원": "bt1@naver.com",
    "박팀투": "bt2@naver.com",
    "이팀삼": "bt3@naver.com",
    "정주애": "jungia21@naver.com",
}
MANAGER = "정주애"

# data/sample/Sales_DB.xlsx 의 품목리스트 시트. 제품군을 스키마의 category_code 로 옮긴다.
PRODUCTS = (
    ("LR1000", "system", 4_500_000, None, "보급형 레이저 시스템"),
    ("LR2000", "system", 5_200_000, None, "주력 레이저 시스템"),
    ("LR-PRO", "system", 6_000_000, None, "상급종합 대상 상위 모델"),
    ("LP1000", "probe", 130_000, 24, "표준 프로브"),
    ("LP1500", "probe", 145_000, 24, "중형 프로브"),
    ("LP2000", "probe", 175_000, 24, "대형 프로브"),
    ("LR-CORE1", "consumable", 4_200_000, None, "코어 액세서리 1형"),
    ("LR-CORE2", "consumable", 4_800_000, None, "코어 액세서리 2형"),
    ("LR-CORE3", "consumable", 60_000, 12, "소모성 액세서리"),
    ("LP100", "consumable", 180_000, 18, "교체 부품 100"),
    ("LP200", "consumable", 240_000, 18, "교체 부품 200"),
)


class CompanySeed(NamedTuple):
    name: str
    region: str
    business_no: str


# data/sample/Sales_DB.xlsx 의 영업현황 시트에서 가져온 병원명. 지역 코드는 화면이 한글로
# 풀어 주는 네 가지(seoul·gyeonggi·incheon·chungnam)만 쓴다.
COMPANIES = (
    CompanySeed("한빛메디병원", "seoul", "1018212345"),
    CompanySeed("새봄메디병원", "incheon", "1218223456"),
    CompanySeed("온누리메디병원", "gyeonggi", "1358234567"),
    CompanySeed("라온메디병원", "chungnam", "3128245678"),
    CompanySeed("늘봄메디병원", "gyeonggi", "1298256789"),
    CompanySeed("더원메디병원", "seoul", "2118267890"),
    CompanySeed("다온메디병원", "chungnam", "3078278901"),
    CompanySeed("새론메디병원", "gyeonggi", "1428289012"),
    CompanySeed("하나메디병원", "incheon", "1318290123"),
    CompanySeed("미래메디병원", "seoul", "2208201234"),
    CompanySeed("서울메디병원", "seoul", "1078312345"),
    CompanySeed("강남메디병원", "seoul", "2158323456"),
    CompanySeed("부산메디병원", "gyeonggi", "1348334567"),
    CompanySeed("대전메디병원", "chungnam", "3148345678"),
    CompanySeed("광주메디병원", "gyeonggi", "1268356789"),
    CompanySeed("인천메디병원", "incheon", "1398367890"),
    CompanySeed("대구메디병원", "gyeonggi", "1248378901"),
    CompanySeed("세종메디병원", "chungnam", "3018389012"),
    CompanySeed("제주메디병원", "seoul", "2178390123"),
    CompanySeed("경기메디병원", "gyeonggi", "1288401234"),
    CompanySeed("라이트메디병원", "incheon", "1338412345"),
    CompanySeed("루미나메디병원", "gyeonggi", "1408423456"),
    CompanySeed("케어메디병원", "seoul", "2138434567"),
    CompanySeed("바이오메디병원", "chungnam", "3098445678"),
)


def _d(month: int, day: int) -> date:
    return date(2026, month, day)


class ContactSeed(NamedTuple):
    key: str
    name: str
    company: str
    department: str
    job_title: str
    email: str
    phone: str
    owner: str
    source: str
    status: str
    memo: str
    registered_on: date
    visited: bool


# source_code 는 Sales_DB.xlsx 가이드라인 시트의 유입경로 다섯 가지를 옮긴 값이다.
CONTACTS = (
    ContactSeed(
        "C01",
        "김가민",
        "한빛메디병원",
        "의공팀",
        "팀장",
        "gamin.kim@demo.test",
        "010-0000-2000",
        "김팀원",
        "news",
        "contracted",
        "LR2000 도입 후 프로브 추가 검토",
        _d(6, 2),
        True,
    ),
    ContactSeed(
        "C02",
        "박가윤",
        "새봄메디병원",
        "원무팀",
        "과장",
        "gayun.park@demo.test",
        "010-0000-2001",
        "김팀원",
        "news",
        "negotiation",
        "제품 교육자료 요청",
        _d(6, 3),
        True,
    ),
    ContactSeed(
        "C03",
        "이가현",
        "온누리메디병원",
        "정형외과",
        "대표원장",
        "gahyeon.lee@demo.test",
        "010-0000-2002",
        "박팀투",
        "referral",
        "contracted",
        "샘플 프로브 요청 후 계약",
        _d(6, 4),
        True,
    ),
    ContactSeed(
        "C04",
        "최가우",
        "라온메디병원",
        "재활의학과",
        "진료부장",
        "gawoo.choi@demo.test",
        "010-0000-2003",
        "이팀삼",
        "news",
        "proposal",
        "간호사 별도 교육 요청",
        _d(6, 5),
        True,
    ),
    ContactSeed(
        "C05",
        "정가진",
        "늘봄메디병원",
        "구매팀",
        "차장",
        "gajin.jeong@demo.test",
        "010-0000-2004",
        "이팀삼",
        "news",
        "contracted",
        "최종 계약 진행, 분할 발주 요청",
        _d(6, 8),
        True,
    ),
    ContactSeed(
        "C06",
        "한가서",
        "더원메디병원",
        "의공팀",
        "주임",
        "gaseo.han@demo.test",
        "010-0000-2005",
        "김팀원",
        "conference",
        "contracted",
        "계약서 초안 검토 완료",
        _d(6, 9),
        True,
    ),
    ContactSeed(
        "C07",
        "오가영",
        "다온메디병원",
        "영상의학과",
        "교수",
        "gayoung.oh@demo.test",
        "010-0000-2006",
        "김팀원",
        "conference",
        "negotiation",
        "견적서 초안 발송함",
        _d(6, 10),
        True,
    ),
    ContactSeed(
        "C08",
        "윤가호",
        "새론메디병원",
        "간호부",
        "수간호사",
        "gaho.yoon@demo.test",
        "010-0000-2007",
        "박팀투",
        "news",
        "negotiation",
        "데모장비 설치 협의 중",
        _d(6, 11),
        True,
    ),
    ContactSeed(
        "C09",
        "강가준",
        "하나메디병원",
        "구매팀",
        "대리",
        "gajun.kang@demo.test",
        "010-0000-2008",
        "정주애",
        "news",
        "on_hold",
        "제품 관심 낮음, 내년 예산 후 재접촉",
        _d(6, 12),
        True,
    ),
    ContactSeed(
        "C10",
        "서가아",
        "미래메디병원",
        "원무팀",
        "팀장",
        "gaa.seo@demo.test",
        "010-0000-2009",
        "김팀원",
        "search",
        "contracted",
        "제품설명회 후 계약 확정",
        _d(6, 15),
        True,
    ),
    ContactSeed(
        "C11",
        "문가수",
        "서울메디병원",
        "심장혈관센터",
        "교수",
        "gasu.moon@demo.test",
        "010-0000-2010",
        "박팀투",
        "referral",
        "contracted",
        "연간 소모품 공급 계약",
        _d(6, 16),
        True,
    ),
    ContactSeed(
        "C12",
        "배가빈",
        "강남메디병원",
        "정보전략팀",
        "책임",
        "gabin.bae@demo.test",
        "010-0000-2011",
        "박팀투",
        "referral",
        "negotiation",
        "계약서 초안 발송, 법무 검토 중",
        _d(6, 17),
        True,
    ),
    ContactSeed(
        "C13",
        "조가재",
        "부산메디병원",
        "의공팀",
        "과장",
        "gajae.jo@demo.test",
        "010-0000-2012",
        "김팀원",
        "conference",
        "proposal",
        "견적서 초안 발송",
        _d(6, 18),
        False,
    ),
    ContactSeed(
        "C14",
        "임가림",
        "대전메디병원",
        "재활의학과",
        "실장",
        "garim.lim@demo.test",
        "010-0000-2013",
        "이팀삼",
        "referral",
        "negotiation",
        "데모장비 2주 대여 요청",
        _d(6, 19),
        True,
    ),
    ContactSeed(
        "C15",
        "신가원",
        "광주메디병원",
        "구매팀",
        "팀장",
        "gawon.shin@demo.test",
        "010-0000-2014",
        "이팀삼",
        "news",
        "contracted",
        "1개월 내 계약 가능",
        _d(6, 22),
        True,
    ),
    ContactSeed(
        "C16",
        "장가희",
        "인천메디병원",
        "영상의학과",
        "전문의",
        "gahee.jang@demo.test",
        "010-0000-2015",
        "이팀삼",
        "sns",
        "proposal",
        "제품설명회 일정 확정 필요",
        _d(6, 23),
        True,
    ),
    ContactSeed(
        "C17",
        "권가경",
        "대구메디병원",
        "간호부",
        "수간호사",
        "gagyeong.kwon@demo.test",
        "010-0000-2016",
        "박팀투",
        "referral",
        "negotiation",
        "최종 계약 진행 중",
        _d(6, 24),
        True,
    ),
    ContactSeed(
        "C18",
        "김나민",
        "세종메디병원",
        "원무팀",
        "주임",
        "namin.kim@demo.test",
        "010-0000-2017",
        "이팀삼",
        "search",
        "contracted",
        "계약서 초안 발송 후 체결",
        _d(6, 25),
        True,
    ),
    ContactSeed(
        "C19",
        "박나윤",
        "제주메디병원",
        "의공팀",
        "차장",
        "nayun.park@demo.test",
        "010-0000-2018",
        "정주애",
        "conference",
        "negotiation",
        "견적서 초안 발송",
        _d(6, 26),
        True,
    ),
    ContactSeed(
        "C20",
        "이나현",
        "경기메디병원",
        "구매팀",
        "과장",
        "nahyeon.lee@demo.test",
        "010-0000-2019",
        "이팀삼",
        "sns",
        "proposal",
        "데모장비 설치 대기",
        _d(6, 29),
        True,
    ),
    ContactSeed(
        "C21",
        "최나우",
        "라이트메디병원",
        "정형외과",
        "대표원장",
        "nawoo.choi@demo.test",
        "010-0000-2020",
        "정주애",
        "news",
        "contracted",
        "제품시연 후 계약",
        _d(6, 30),
        True,
    ),
    ContactSeed(
        "C22",
        "정나진",
        "루미나메디병원",
        "구매팀",
        "대리",
        "najin.jeong@demo.test",
        "010-0000-2021",
        "김팀원",
        "search",
        "negotiation",
        "제품설명회 일정 확정",
        _d(7, 1),
        True,
    ),
    ContactSeed(
        "C23",
        "한나서",
        "케어메디병원",
        "재활의학과",
        "실장",
        "naseo.han@demo.test",
        "010-0000-2022",
        "박팀투",
        "news",
        "proposal",
        "계약서 초안 발송 예정",
        _d(7, 2),
        True,
    ),
    ContactSeed(
        "C24",
        "오나영",
        "바이오메디병원",
        "간호부",
        "수간호사",
        "nayoung.oh@demo.test",
        "010-0000-2023",
        "정주애",
        "conference",
        "on_hold",
        "제품 관심 없음으로 정리",
        _d(7, 3),
        False,
    ),
    ContactSeed(
        "C25",
        "윤나호",
        "한빛메디병원",
        "구매팀",
        "과장",
        "naho.yoon@demo.test",
        "010-0000-2024",
        "김팀원",
        "existing",
        "negotiation",
        "소모품 단가 재협의",
        _d(7, 6),
        True,
    ),
    ContactSeed(
        "C26",
        "강나준",
        "온누리메디병원",
        "구매팀",
        "차장",
        "najun.kang@demo.test",
        "010-0000-2025",
        "박팀투",
        "existing",
        "contracted",
        "부품 정기 공급 전환",
        _d(7, 7),
        True,
    ),
    ContactSeed(
        "C27",
        "서나아",
        "늘봄메디병원",
        "의공팀",
        "주임",
        "naa.seo@demo.test",
        "010-0000-2026",
        "이팀삼",
        "existing",
        "contracted",
        "설치 환경 사전 점검 완료",
        _d(7, 8),
        True,
    ),
    ContactSeed(
        "C28",
        "문나수",
        "미래메디병원",
        "구매팀",
        "대리",
        "nasu.moon@demo.test",
        "010-0000-2027",
        "김팀원",
        "existing",
        "negotiation",
        "증설 물량 확인 중",
        _d(7, 9),
        True,
    ),
    ContactSeed(
        "C29",
        "배나빈",
        "서울메디병원",
        "구매팀",
        "팀장",
        "nabin.bae@demo.test",
        "010-0000-2028",
        "박팀투",
        "existing",
        "contracted",
        "2차 발주 일정 조율",
        _d(7, 10),
        True,
    ),
    ContactSeed(
        "C30",
        "조나재",
        "광주메디병원",
        "의공팀",
        "과장",
        "najae.jo@demo.test",
        "010-0000-2029",
        "이팀삼",
        "existing",
        "negotiation",
        "유지보수 범위 문서 전달",
        _d(7, 13),
        True,
    ),
    ContactSeed(
        "C31",
        "임나림",
        "대구메디병원",
        "원무팀",
        "주임",
        "narim.lim@demo.test",
        "010-0000-2030",
        "박팀투",
        "sns",
        "new",
        "첫 통화 완료, 자료 발송",
        _d(8, 3),
        False,
    ),
    ContactSeed(
        "C32",
        "신나원",
        "케어메디병원",
        "구매팀",
        "대리",
        "nawon.shin@demo.test",
        "010-0000-2031",
        "정주애",
        "sns",
        "new",
        "학회 부스에서 명함 교환",
        _d(8, 10),
        False,
    ),
    ContactSeed(
        "C33",
        "장나희",
        "경기메디병원",
        "의공팀",
        "주임",
        "nahee.jang@demo.test",
        "010-0000-2032",
        "김팀원",
        "search",
        "new",
        "제품 자료 이메일 발송",
        _d(8, 17),
        False,
    ),
    ContactSeed(
        "C34",
        "권나경",
        "라이트메디병원",
        "간호부",
        "주임",
        "nagyeong.kwon@demo.test",
        "010-0000-2033",
        "정주애",
        "referral",
        "new",
        "사용 교육 희망 인원 확인 필요",
        _d(8, 20),
        False,
    ),
)


class DealSeed(NamedTuple):
    key: str
    contact: str
    product: str
    qty: int
    deal_type: str
    stage: str
    opened: date
    quote: date | None
    quote_valid: date | None
    contract_no: bool
    signed: date | None
    ends: date | None
    closed: date | None
    memo: str


# 40건. 확정(계약 완료·발주 진행·납품 완료) 12, 진행 25, 취소 3 이다.
# deal_amount 는 수량 x 품목 단가로 계산하므로 둥근 금액과 그렇지 않은 금액이 섞인다.
DEALS = (
    DealSeed(
        "D01",
        "C01",
        "LR2000",
        3,
        "new_installation",
        "order_delivered",
        _d(6, 2),
        _d(6, 12),
        _d(7, 12),
        True,
        _d(6, 29),
        date(2027, 6, 28),
        None,
        "의공팀 사전 점검 후 설치 완료",
    ),
    DealSeed(
        "D09",
        "C03",
        "LR-PRO",
        6,
        "new_installation",
        "contract_completed",
        _d(6, 4),
        _d(6, 18),
        _d(7, 18),
        True,
        _d(6, 26),
        date(2027, 6, 25),
        None,
        "샘플 프로브 평가 후 본계약",
    ),
    DealSeed(
        "D02",
        "C05",
        "LR-PRO",
        5,
        "new_installation",
        "order_in_progress",
        _d(6, 8),
        _d(6, 22),
        _d(7, 22),
        True,
        _d(6, 30),
        date(2027, 6, 29),
        None,
        "예산 집행 일정에 맞춰 2회 분할 발주",
    ),
    DealSeed(
        "D03",
        "C06",
        "LR2000",
        4,
        "new_installation",
        "contract_completed",
        _d(6, 9),
        _d(6, 24),
        _d(7, 24),
        True,
        _d(8, 6),
        date(2027, 8, 5),
        None,
        "계약서 초안 검토가 길어져 8월 체결, 발주 일정 미정",
    ),
    DealSeed(
        "D04",
        "C10",
        "LR1000",
        7,
        "new_installation",
        "order_delivered",
        _d(6, 15),
        _d(6, 26),
        _d(7, 26),
        True,
        _d(7, 10),
        date(2027, 7, 9),
        None,
        "제품설명회 후 전 병동 도입",
    ),
    DealSeed(
        "D05",
        "C11",
        "LP100",
        53,
        "consumables_supply",
        "order_in_progress",
        _d(6, 16),
        _d(6, 30),
        _d(7, 30),
        True,
        _d(7, 17),
        date(2027, 7, 16),
        None,
        "연간 부품 공급 단가 계약",
    ),
    DealSeed(
        "D06",
        "C15",
        "LR-PRO",
        9,
        "new_installation",
        "contract_completed",
        _d(6, 22),
        _d(7, 6),
        _d(8, 6),
        True,
        _d(8, 14),
        date(2027, 8, 13),
        None,
        "구매팀 품의 승인 후 체결",
    ),
    DealSeed(
        "D07",
        "C18",
        "LR2000",
        6,
        "new_installation",
        "order_in_progress",
        _d(6, 25),
        _d(7, 9),
        _d(8, 9),
        True,
        _d(7, 31),
        date(2027, 7, 30),
        None,
        "생산 일정 확인 중",
    ),
    DealSeed(
        "D08",
        "C21",
        "LR1000",
        4,
        "new_installation",
        "order_delivered",
        _d(6, 30),
        _d(7, 13),
        _d(8, 13),
        True,
        _d(7, 28),
        date(2027, 7, 27),
        None,
        "제품시연 직후 계약, 납품·교육 완료",
    ),
    DealSeed(
        "D10",
        "C26",
        "LP200",
        38,
        "consumables_supply",
        "contract_completed",
        _d(7, 7),
        _d(7, 20),
        _d(8, 20),
        True,
        _d(8, 5),
        date(2027, 8, 4),
        None,
        "부품 정기 공급으로 전환",
    ),
    DealSeed(
        "D11",
        "C27",
        "LR-CORE1",
        3,
        "expansion",
        "order_in_progress",
        _d(7, 8),
        _d(7, 22),
        _d(8, 22),
        True,
        _d(8, 7),
        date(2027, 8, 6),
        None,
        "기존 설치 라인 증설",
    ),
    DealSeed(
        "D12",
        "C29",
        "LR2000",
        9,
        "expansion",
        "contract_completed",
        _d(7, 10),
        _d(7, 27),
        _d(8, 27),
        True,
        _d(8, 12),
        date(2027, 8, 11),
        None,
        "2차 발주 일정 조율 중",
    ),
    DealSeed(
        "D41",
        "C19",
        "LR-CORE1",
        2,
        "expansion",
        "contract_completed",
        _d(7, 5),
        _d(7, 24),
        _d(8, 24),
        True,
        _d(8, 18),
        date(2027, 8, 17),
        None,
        "의공팀 검토 회신 후 증설분만 우선 계약",
    ),
    DealSeed(
        "D13",
        "C31",
        "LR1000",
        2,
        "new_installation",
        "needs_validation",
        _d(8, 3),
        None,
        None,
        False,
        None,
        None,
        None,
        "첫 통화 후 자료 발송, 도입 규모 확인 필요",
    ),
    DealSeed(
        "D14",
        "C32",
        "LR2000",
        3,
        "new_installation",
        "needs_validation",
        _d(8, 10),
        None,
        None,
        False,
        None,
        None,
        None,
        "학회 부스 상담 건",
    ),
    DealSeed(
        "D15",
        "C33",
        "LR1000",
        3,
        "new_installation",
        "needs_validation",
        _d(8, 17),
        None,
        None,
        False,
        None,
        None,
        None,
        "홈페이지 문의 유입",
    ),
    DealSeed(
        "D16",
        "C34",
        "LP1000",
        20,
        "consumables_supply",
        "needs_validation",
        _d(8, 20),
        None,
        None,
        False,
        None,
        None,
        None,
        "사용 교육 희망 인원 확인 후 견적",
    ),
    DealSeed(
        "D17",
        "C09",
        "LR1000",
        2,
        "new_installation",
        "needs_validation",
        _d(6, 12),
        None,
        None,
        False,
        None,
        None,
        None,
        "예산 편성 시점이 내년이라 장기 관리",
    ),
    DealSeed(
        "D18",
        "C24",
        "LR2000",
        2,
        "new_installation",
        "needs_validation",
        _d(7, 3),
        None,
        None,
        False,
        None,
        None,
        None,
        "담당자 변경 예정, 후임 확인 필요",
    ),
    DealSeed(
        "D19",
        "C02",
        "LR1000",
        3,
        "new_installation",
        "product_demo",
        _d(6, 3),
        None,
        None,
        False,
        None,
        None,
        None,
        "데모장비 설치 후 원내 평가 중",
    ),
    DealSeed(
        "D20",
        "C04",
        "LR2000",
        4,
        "new_installation",
        "product_demo",
        _d(6, 5),
        None,
        None,
        False,
        None,
        None,
        None,
        "간호사 별도 교육 요청 반영",
    ),
    DealSeed(
        "D21",
        "C16",
        "LR2000",
        3,
        "new_installation",
        "product_demo",
        _d(6, 23),
        None,
        None,
        False,
        None,
        None,
        None,
        "제품설명회 일정 확정 필요",
    ),
    DealSeed(
        "D22",
        "C20",
        "LR1000",
        5,
        "new_installation",
        "product_demo",
        _d(6, 29),
        None,
        None,
        False,
        None,
        None,
        None,
        "데모장비 설치 대기",
    ),
    DealSeed(
        "D23",
        "C23",
        "LR-PRO",
        3,
        "new_installation",
        "product_demo",
        _d(7, 2),
        None,
        None,
        False,
        None,
        None,
        None,
        "시연 결과 리뷰 예정",
    ),
    DealSeed(
        "D24",
        "C28",
        "LR-CORE2",
        2,
        "expansion",
        "product_demo",
        _d(7, 9),
        None,
        None,
        False,
        None,
        None,
        None,
        "증설 물량 확인 중",
    ),
    DealSeed(
        "D25",
        "C07",
        "LR-PRO",
        7,
        "new_installation",
        "quote_sent",
        _d(6, 10),
        _d(6, 25),
        _d(7, 25),
        False,
        None,
        None,
        None,
        "견적 회신 대기, 유효기간 연장 요청 받음",
    ),
    DealSeed(
        "D26",
        "C08",
        "LR1000",
        6,
        "new_installation",
        "quote_sent",
        _d(6, 11),
        _d(7, 2),
        _d(8, 2),
        False,
        None,
        None,
        None,
        "데모장비 설치 후 견적 발송",
    ),
    DealSeed(
        "D27",
        "C13",
        "LR2000",
        5,
        "new_installation",
        "quote_sent",
        _d(6, 18),
        _d(7, 8),
        _d(8, 8),
        False,
        None,
        None,
        None,
        "비교 견적 진행 중",
    ),
    DealSeed(
        "D28",
        "C14",
        "LR-CORE1",
        4,
        "expansion",
        "quote_sent",
        _d(6, 19),
        _d(7, 14),
        _d(8, 14),
        False,
        None,
        None,
        None,
        "데모장비 2주 대여 후 견적",
    ),
    DealSeed(
        "D29",
        "C19",
        "LR-PRO",
        4,
        "new_installation",
        "quote_sent",
        _d(6, 26),
        _d(7, 21),
        _d(8, 21),
        False,
        None,
        None,
        None,
        "의공팀 검토 회신 대기",
    ),
    DealSeed(
        "D30",
        "C22",
        "LR2000",
        6,
        "new_installation",
        "quote_sent",
        _d(7, 1),
        _d(7, 29),
        _d(8, 29),
        False,
        None,
        None,
        None,
        "제품설명회 후 견적 발송",
    ),
    DealSeed(
        "D31",
        "C25",
        "LP1500",
        60,
        "consumables_supply",
        "quote_sent",
        _d(7, 6),
        _d(8, 4),
        _d(9, 4),
        False,
        None,
        None,
        None,
        "소모품 단가 재협의 중",
    ),
    DealSeed(
        "D32",
        "C30",
        "LP200",
        45,
        "maintenance",
        "quote_sent",
        _d(7, 13),
        _d(8, 11),
        _d(9, 11),
        False,
        None,
        None,
        None,
        "유지보수 범위 문서 전달 완료",
    ),
    DealSeed(
        "D33",
        "C12",
        "LR-PRO",
        8,
        "new_installation",
        "contract_sent",
        _d(6, 17),
        _d(7, 10),
        _d(8, 10),
        True,
        None,
        None,
        None,
        "계약서 발송, 법무 검토 중",
    ),
    DealSeed(
        "D34",
        "C17",
        "LR2000",
        7,
        "new_installation",
        "contract_sent",
        _d(6, 24),
        _d(7, 23),
        _d(8, 23),
        True,
        None,
        None,
        None,
        "최종 계약 진행 중",
    ),
    DealSeed(
        "D35",
        "C05",
        "LP2000",
        30,
        "consumables_supply",
        "contract_sent",
        _d(7, 15),
        _d(8, 6),
        _d(9, 6),
        True,
        None,
        None,
        None,
        "본계약 이후 소모품 별도 계약",
    ),
    DealSeed(
        "D36",
        "C11",
        "LR-CORE3",
        120,
        "maintenance",
        "contract_review",
        _d(7, 17),
        _d(8, 10),
        _d(9, 10),
        True,
        None,
        None,
        None,
        "결제 조건 조정 요청으로 검토 중",
    ),
    DealSeed(
        "D37",
        "C27",
        "LR1000",
        4,
        "renewal",
        "contract_review",
        _d(7, 20),
        _d(8, 13),
        _d(9, 13),
        True,
        None,
        None,
        None,
        "기존 계약 갱신, 조건 검토 중",
    ),
    DealSeed(
        "D38",
        "C13",
        "LR-CORE2",
        2,
        "expansion",
        "closed_cancelled",
        _d(6, 18),
        _d(7, 1),
        _d(7, 31),
        False,
        None,
        None,
        _d(8, 3),
        "경쟁사 모델로 결정되어 종료",
    ),
    DealSeed(
        "D39",
        "C09",
        "LR2000",
        2,
        "new_installation",
        "closed_cancelled",
        _d(6, 12),
        _d(6, 28),
        _d(7, 28),
        False,
        None,
        None,
        _d(7, 24),
        "예산 보류로 중단",
    ),
    DealSeed(
        "D40",
        "C20",
        "LR-CORE3",
        50,
        "consumables_supply",
        "closed_cancelled",
        _d(7, 6),
        None,
        None,
        False,
        None,
        None,
        _d(8, 10),
        "원내 통합 구매로 전환되어 종료",
    ),
)

WARRANTY = "설치일로부터 12개월 무상 보증, 이후 연간 유지보수 계약 별도"


class Step(NamedTuple):
    """딜 하나가 지나가는 활동 한 단계."""

    category: str
    tag: str
    label: str
    # opened_on 으로부터의 기본 간격(일). 견적·계약 단계는 딜의 실제 날짜로 덮어쓴다.
    offset: int
    hour: int


# 영업 흐름 한 벌. 단계(stage)마다 이 흐름의 앞에서부터 몇 개까지 왔는지가 다르다.
FLOW = (
    Step("call", "first_call", "첫 통화", 0, 10),
    Step("visit", "meeting", "첫 방문 미팅", 5, 14),
    Step("visit", "demo_requested", "데모 요청 협의", 11, 11),
    Step("demo", "demo_in_progress", "제품 시연", 17, 14),
    Step("demo", "demo_completed", "시연 결과 리뷰", 23, 10),
    Step("visit", "quote_completed", "견적서 전달", 29, 15),
    Step("visit", "meeting", "가격·조건 협의", 36, 14),
    Step("visit", "contract_completed", "계약 체결", 45, 11),
    Step("delivery", "delivery_completed", "납품·설치", 59, 10),
    Step("education", "product_training", "사용 교육", 66, 14),
)
QUOTE_STEP = 5
CONTRACT_STEP = 7

# 단계별로 흐름의 앞 몇 개를 실제로 수행했는지.
STAGE_STEPS = {
    "needs_validation": 2,
    "product_demo": 4,
    "quote_sent": 6,
    "contract_sent": 7,
    "contract_review": 7,
    "contract_completed": 8,
    "order_in_progress": 8,
    "order_delivered": 10,
    "closed_cancelled": 6,
}


class OrderSeed(NamedTuple):
    key: str
    deal: str
    supplier: str
    status: str
    qty: int
    ordered: date
    due: date
    receipt: date
    memo: str


# 발주는 확정 딜에만 붙는다. 계약 완료 상태로 두고 발주하지 않은 딜(D03·D06·D09·D10·D12·D41)도
# 남겨 "계약은 됐지만 발주 전" 을 화면에서 볼 수 있게 한다.
# D02·D04 는 분할 발주라 두 건의 수량 합이 계약 수량과 같다.
ORDERS = (
    OrderSeed(
        "O01",
        "D01",
        "레이저메디텍",
        "delivered",
        3,
        _d(7, 2),
        _d(7, 16),
        _d(7, 14),
        "설치 일정 확정 후 발주",
    ),
    OrderSeed(
        "O02",
        "D04",
        "레이저메디텍",
        "delivered",
        4,
        _d(7, 14),
        _d(7, 30),
        _d(7, 28),
        "1차 발주분, 본관 병동",
    ),
    OrderSeed(
        "O03",
        "D04",
        "레이저메디텍",
        "delivered",
        3,
        _d(8, 3),
        _d(8, 19),
        _d(8, 17),
        "2차 발주분, 신관 병동",
    ),
    OrderSeed(
        "O04",
        "D08",
        "루미나레이저",
        "delivered",
        4,
        _d(7, 31),
        _d(8, 14),
        _d(8, 12),
        "제품 교육까지 함께 진행",
    ),
    OrderSeed(
        "O05",
        "D02",
        "프로레이저솔루션",
        "stock_received",
        3,
        _d(7, 9),
        _d(7, 25),
        _d(7, 23),
        "1차 발주분 입고 완료",
    ),
    OrderSeed(
        "O06",
        "D02",
        "프로레이저솔루션",
        "in_production",
        2,
        _d(8, 10),
        _d(8, 30),
        _d(8, 28),
        "2차 발주분 생산 중",
    ),
    OrderSeed(
        "O07",
        "D05",
        "레이저메디텍",
        "dispatch_request_completed",
        53,
        _d(7, 20),
        _d(8, 5),
        _d(8, 3),
        "연간 공급 1회차",
    ),
    OrderSeed(
        "O08",
        "D07",
        "루미나레이저",
        "in_production",
        6,
        _d(8, 4),
        _d(8, 30),
        _d(8, 28),
        "생산 일정 확인 완료",
    ),
    OrderSeed(
        "O09",
        "D11",
        "프로레이저솔루션",
        "order_received",
        3,
        _d(8, 10),
        _d(9, 2),
        _d(8, 31),
        "증설분 발주 접수",
    ),
)


class SupportSeed(NamedTuple):
    key: str
    deal: str
    title: str
    body: str
    status: str
    urgent: bool
    occurred: date
    responses: tuple[tuple[str, date], ...]


SUPPORTS = (
    SupportSeed(
        "S01",
        "D01",
        "설치 후 프로브 인식 불량",
        "설치 다음 날 프로브를 교체하자 장비가 인식하지 못한다는 연락을 받았습니다. "
        "케이블 접점 문제로 보입니다.",
        "completed",
        True,
        _d(7, 20),
        (
            ("현장 방문해 접점 청소 후 정상 인식 확인했습니다.", _d(7, 21)),
            ("동일 증상 재발 없음을 확인하고 종료했습니다.", _d(7, 27)),
        ),
    ),
    SupportSeed(
        "S02",
        "D04",
        "사용 교육 추가 요청",
        "야간 근무 간호사 대상 교육이 빠졌다는 요청을 받았습니다. 2회차 교육 일정이 필요합니다.",
        "in_progress",
        False,
        _d(8, 5),
        (("8월 셋째 주로 2회차 교육 일정을 협의 중입니다.", _d(8, 7)),),
    ),
    SupportSeed(
        "S03",
        "D08",
        "출력 편차 문의",
        "동일 조건에서 출력값이 회차마다 다르게 표시된다는 문의입니다.",
        "diagnosing",
        True,
        _d(8, 17),
        (("로그를 받아 본사 기술팀에 분석 요청했습니다.", _d(8, 18)),),
    ),
    SupportSeed(
        "S04",
        "D05",
        "부품 입고 지연 문의",
        "1회차 공급분 입고가 예정보다 늦어진다는 문의입니다.",
        "completed",
        False,
        _d(8, 4),
        (("공급사 출고 지연 사유를 안내하고 새 입고일을 확정했습니다.", _d(8, 5)),),
    ),
    SupportSeed(
        "S05",
        "D02",
        "2차 발주분 일정 확인",
        "2차 발주분 설치가 9월로 넘어가는지 확인 요청을 받았습니다.",
        "received",
        False,
        _d(8, 21),
        (),
    ),
    SupportSeed(
        "S06",
        "D07",
        "설치 공간 실측 재요청",
        "장비 반입 동선이 좁아 실측을 다시 해 달라는 요청입니다.",
        "in_progress",
        False,
        _d(8, 12),
        (("의공팀과 8월 26일 실측 일정을 잡았습니다.", _d(8, 13)),),
    ),
    SupportSeed(
        "S07",
        "D11",
        "증설분 사양 확인",
        "증설분이 기존 장비와 같은 사양인지 확인 요청입니다.",
        "completed",
        False,
        _d(8, 13),
        (("동일 사양임을 사양서로 회신했습니다.", _d(8, 14)),),
    ),
    SupportSeed(
        "S08",
        "D09",
        "납품 전 전원 사양 문의",
        "설치 예정 구역의 전원 사양이 맞는지 사전 확인 요청입니다.",
        "received",
        False,
        _d(8, 24),
        (),
    ),
)


# (담당자, 월, 고객사, 목표액). 한 담당자의 한 달 목표를 주요 고객사 두 곳으로 나눈다.
# 정주애는 6월 목표를 두지 않아 "목표 미설정" 상태도 화면에서 볼 수 있다.
SALES_TARGETS = (
    ("김팀원", 6, "한빛메디병원", 12_000_000),
    ("김팀원", 6, "더원메디병원", 8_000_000),
    ("김팀원", 7, "미래메디병원", 18_000_000),
    ("김팀원", 7, "다온메디병원", 12_000_000),
    ("김팀원", 8, "더원메디병원", 15_000_000),
    ("김팀원", 8, "루미나메디병원", 10_000_000),
    ("박팀투", 6, "온누리메디병원", 20_000_000),
    ("박팀투", 6, "서울메디병원", 10_000_000),
    ("박팀투", 7, "서울메디병원", 9_000_000),
    ("박팀투", 7, "강남메디병원", 6_000_000),
    ("박팀투", 8, "서울메디병원", 30_000_000),
    ("박팀투", 8, "온누리메디병원", 20_000_000),
    ("이팀삼", 6, "늘봄메디병원", 15_000_000),
    ("이팀삼", 6, "광주메디병원", 10_000_000),
    ("이팀삼", 7, "세종메디병원", 20_000_000),
    ("이팀삼", 7, "대전메디병원", 15_000_000),
    ("이팀삼", 8, "광주메디병원", 40_000_000),
    ("이팀삼", 8, "늘봄메디병원", 20_000_000),
    ("정주애", 7, "라이트메디병원", 12_000_000),
    ("정주애", 7, "제주메디병원", 8_000_000),
    ("정주애", 8, "제주메디병원", 10_000_000),
)


class NoticeSeed(NamedTuple):
    key: str
    type: str
    tag: str | None
    title: str
    body: str
    published_on: date
    display_end: date | None
    due_on: date | None
    due_text: str | None
    targets: tuple[str, ...]
    sort_order: int


NOTICES = (
    NoticeSeed(
        "N01",
        "NOTICE",
        "공지",
        "3분기 영업 목표 공유",
        "<p>3분기 팀 목표는 2억 5천만원입니다. 담당자별 목표는 영업현황 화면의 "
        "월 목표에서 확인해 주세요.</p>",
        _d(7, 1),
        None,
        None,
        None,
        (),
        0,
    ),
    NoticeSeed(
        "N02",
        "NOTICE",
        "안내",
        "하계 휴가 일정 취합",
        "<p>8월 휴가 일정을 8월 7일까지 회신해 주세요. 고객 방문 일정이 겹치지 "
        "않도록 미리 조율 바랍니다.</p>",
        _d(7, 28),
        _d(8, 7),
        None,
        None,
        (),
        1,
    ),
    NoticeSeed(
        "N03",
        "NOTICE",
        "제품",
        "LR-PRO 펌웨어 업데이트 안내",
        "<p>LR-PRO 펌웨어가 2.4 로 올라갔습니다. 기 설치 고객사 방문 시 함께 적용해 주세요.</p>",
        _d(8, 11),
        None,
        None,
        None,
        (),
        2,
    ),
    NoticeSeed(
        "N04",
        "DIRECTIVE",
        "요청",
        "견적 유효기간 만료 건 정리",
        "<p>유효기간이 지난 견적은 재발송 여부를 고객사에 확인하고 결과를 메모에 남겨 주세요.</p>",
        _d(8, 17),
        None,
        _d(8, 26),
        "8월 26일까지",
        ("김팀원", "박팀투"),
        3,
    ),
    NoticeSeed(
        "N05",
        "DIRECTIVE",
        "요청",
        "8월 발주 건 입고일 재확인",
        "<p>생산 중인 발주 두 건의 입고 예정일을 공급사에 다시 확인해 주세요.</p>",
        _d(8, 19),
        None,
        _d(8, 25),
        "8월 25일까지",
        ("이팀삼",),
        4,
    ),
    NoticeSeed(
        "N06",
        "DIRECTIVE",
        "보고",
        "주간보고 작성 요청",
        "<p>이번 주 주간보고를 금요일 오전까지 제출해 주세요.</p>",
        _d(8, 24),
        None,
        _d(8, 28),
        "8월 28일 오전까지",
        ("김팀원", "박팀투", "이팀삼"),
        5,
    ),
)


def _field(
    fid: str, label: str, ftype: str, required: bool, ai: bool, placeholder: str | None = None
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "id": fid,
        "label": label,
        "type": ftype,
        "required": required,
        "aiFilled": ai,
    }
    if placeholder is not None:
        field["placeholder"] = placeholder
    return field


def _template(tid: str, name: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": tid, "name": name, "owner": "", "updated": "", "fields": fields}


# 화면이 쓰는 기본 양식 그대로다. frontend/src/shared/meetings.ts, reports.ts 와 같아야
# 저장된 보고서를 열었을 때 항목이 어긋나지 않는다.
MEETING_TEMPLATE = _template(
    "builtin-meeting",
    "기본 미팅 기록 양식",
    [
        _field("attendees", "참석자", "text", True, True, "참석자를 입력하세요."),
        _field(
            "reaction", "고객 반응", "textarea", True, True, "제품·조건에 대한 반응을 입력하세요."
        ),
        _field("decision", "결정사항", "textarea", True, True, "합의한 내용을 입력하세요."),
        _field(
            "next",
            "다음 행동 · 기한",
            "textarea",
            True,
            True,
            "누가 언제까지 무엇을 하는지 입력하세요.",
        ),
        _field("note", "특이사항", "text", False, False, "직접 확인한 내용만 입력하세요."),
    ],
)
DAILY_TEMPLATE = _template(
    "builtin-daily",
    "기본 일일보고 양식",
    [
        _field("summary", "업무 요약", "textarea", True, True, "오늘 진행한 활동을 요약합니다."),
        _field(
            "issue", "특이사항 · 이슈", "textarea", False, True, "지연, 고객 불만, 예산 보류 등"
        ),
        _field("next", "내일 계획", "textarea", True, True, "내일 처리할 후속 업무"),
        _field(
            "competitor",
            "경쟁사 동향",
            "text",
            False,
            False,
            "직접 확인한 내용이 있으면 입력하세요.",
        ),
    ],
)
WEEKLY_TEMPLATE = _template(
    "builtin-weekly",
    "기본 주간보고 양식",
    [
        _field("result", "주간 성과", "textarea", True, True),
        _field("plan", "다음 주 계획", "textarea", True, True),
        _field("risk", "리스크", "textarea", False, True),
    ],
)
MONTHLY_TEMPLATE = _template(
    "builtin-monthly",
    "기본 월간보고 양식",
    [
        _field("perf", "월간 실적", "textarea", True, True),
        _field("gap", "목표 대비", "textarea", True, False),
        _field("focus", "다음 달 중점", "textarea", False, True),
    ],
)

# 업무보고서 본문. 흐름의 몇 번째 단계였는지로 고른다. {} 는 딜마다 채운다.
MEETING_NOTES = {
    0: (
        "사용 중인 장비가 노후해 교체를 검토 중이라고 했습니다. 예산 시점은 아직 미정입니다.",
        "제품 자료를 이메일로 먼저 보내고 방문 일정을 잡기로 했습니다.",
        "제품 소개 자료 발송 후 방문 일정 확정 (3일 내)",
    ),
    1: (
        "{product} 사양은 요구 조건에 맞는다고 보았습니다. 설치 공간과 전원 사양도 확인했습니다.",
        "원내 평가를 위해 데모 장비를 들여오는 방향으로 이야기했습니다.",
        "데모 장비 일정과 반입 동선 확인 (다음 주까지)",
    ),
    2: (
        "데모 기간은 2주면 충분하다고 했습니다. 사용 인원은 {qty}대 기준으로 잡았습니다.",
        "데모 장비 반입일과 담당 부서를 확정했습니다.",
        "데모 장비 반입 준비 및 사전 교육 자료 전달",
    ),
    3: (
        "실제 사용 중 조작이 직관적이라는 반응이었습니다. 출력 안정성도 문제없다고 했습니다.",
        "데모를 예정대로 진행하고 종료 후 평가 회의를 열기로 했습니다.",
        "데모 종료 후 평가 회의 일정 잡기",
    ),
    4: (
        "평가 결과 도입에 무리가 없다는 의견이었습니다. 경쟁사 대비 사후 지원을 높게 봤습니다.",
        "정식 견적을 요청받았습니다. 수량은 {qty}대 기준입니다.",
        "견적서 작성 후 전달 (이번 주 내)",
    ),
    5: (
        "견적 금액 {amount}은 예산 범위 안이라고 했습니다. 결제 조건은 별도 협의를 원했습니다.",
        "견적서를 전달하고 유효기간 안에 회신받기로 했습니다.",
        "유효기간 만료 전 회신 확인 및 재연락",
    ),
    6: (
        "금액보다 납기와 설치 일정을 더 중요하게 봤습니다. 결제 조건 일부 조정을 요청했습니다.",
        "결제 조건을 조정하고 계약서 초안을 보내기로 했습니다.",
        "계약서 초안 발송 및 법무 검토 요청",
    ),
    7: (
        "계약 조건에 이견이 없어 서명까지 진행했습니다.",
        "계약을 체결했습니다. 납품 일정은 발주 후 확정합니다.",
        "발주 진행 및 납품 일정 공유",
    ),
    8: (
        "설치 후 초기 동작 확인까지 문제없이 끝났습니다.",
        "납품과 설치를 완료했습니다. 사용 교육 일정을 잡기로 했습니다.",
        "사용 교육 일정 확정 및 교육 자료 준비",
    ),
    9: (
        "교육 참석 인원은 예정대로였고 이해도도 높았습니다.",
        "사용 교육을 마쳤습니다. 야간 근무자 대상 2회차는 필요 시 추가합니다.",
        "2회차 교육 필요 여부 확인 (2주 내)",
    ),
}

# 오늘(2026-08-25) 잡혀 있는 일정. 대시보드의 "오늘 일정" 카드가 비지 않게 한다.
TODAY_MEETINGS = (
    ("김팀원", "C25", "D31", "visit", "meeting", "한빛메디병원 소모품 단가 재협의", 10),
    ("이팀삼", "C30", "D32", "visit", "meeting", "광주메디병원 유지보수 범위 협의", 11),
    ("박팀투", "C12", "D33", "visit", "meeting", "강남메디병원 계약서 검토 회의", 14),
    ("정주애", "C19", "D41", "visit", "meeting", "제주메디병원 증설분 설치 협의", 15),
    ("김팀원", "C33", "D15", "call", "first_call", "경기메디병원 후속 통화", 16),
)


# ---------------------------------------------------------------- 헬퍼


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=SEOUL)


def won(amount: int) -> str:
    return f"{amount:,}원"


def month_start(day: date) -> date:
    return day.replace(day=1)


def week_start(day: date) -> date:
    """대시보드와 화면이 모두 일요일 시작을 쓴다."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _spread(start: date, end: date, count: int) -> list[date]:
    """start 와 end 사이에 count 개의 날짜를 고르게 벌린다."""
    if count <= 0:
        return []
    span = max((end - start).days, count + 1)
    return [start + timedelta(days=round(span * (i + 1) / (count + 1))) for i in range(count)]


def step_days(deal: DealSeed, count: int) -> list[date]:
    """딜 하나의 활동 날짜. 견적일·계약일은 딜의 실제 날짜에 고정하고 그 사이를 벌린다."""
    anchors: dict[int, date] = {0: deal.opened}
    if deal.quote is not None and count > QUOTE_STEP:
        anchors[QUOTE_STEP] = deal.quote
    if deal.signed is not None and count > CONTRACT_STEP:
        anchors[CONTRACT_STEP] = deal.signed

    days: list[date] = [deal.opened] * count
    known = sorted(anchors)
    for index in known:
        days[index] = anchors[index]
    for left, right in zip(known, known[1:], strict=False):
        for offset, day in enumerate(_spread(anchors[left], anchors[right], right - left - 1), 1):
            days[left + offset] = day
    for index in range(known[-1] + 1, count):
        days[index] = days[index - 1] + timedelta(days=FLOW[index].offset - FLOW[index - 1].offset)
    return days


async def upsert(session: AsyncSession, model: Any, values: dict[str, Any]) -> None:
    """id 가 같으면 갱신한다. id 는 seed 이름에서 나오므로 다시 실행해도 늘지 않는다."""
    stmt = insert(model).values(**values)
    updates = {key: getattr(stmt.excluded, key) for key in values if key != "id"}
    await session.execute(stmt.on_conflict_do_update(index_elements=[model.id], set_=updates))


async def link(session: AsyncSession, model: Any, values: dict[str, Any]) -> None:
    """복합 기본키를 쓰는 연결 표. 이미 있으면 그대로 둔다."""
    await session.execute(insert(model).values(**values).on_conflict_do_nothing())


async def guard_team(session: AsyncSession, model: Any, ids: list[UUID], team_id: UUID) -> None:
    """같은 id 가 다른 팀 소유로 이미 있으면 덮어쓰지 않고 멈춘다."""
    rows = (await session.execute(select(model.id, model.team_id).where(model.id.in_(ids)))).all()
    if any(row.team_id != team_id for row in rows):
        raise SystemExit(f"{model.__tablename__} 에 다른 팀 소유의 같은 id 가 있습니다.")


# ---------------------------------------------------------------- 시딩


class Seeder:
    def __init__(self, db: AsyncSession, team_id: UUID, members: dict[str, UUID]) -> None:
        self.db = db
        self.team_id = team_id
        self.members = members
        self.counts: dict[str, int] = {}
        self.products: dict[str, tuple[UUID, int]] = {}
        self.companies: dict[str, UUID] = {}
        self.contacts = {seed.key: seed for seed in CONTACTS}
        self.contact_ids: dict[str, UUID] = {}
        self.deals: dict[str, dict[str, Any]] = {}
        self.meetings: list[dict[str, Any]] = []
        # (담당자, 날짜) -> 그날 활동. 일일·주간보고서를 실제 활동에서 만든다.
        self.by_day: dict[tuple[str, date], list[dict[str, Any]]] = {}

    def sid(self, kind: str, key: str) -> UUID:
        return uuid5(self.team_id, f"{SEED_TAG}:{kind}:{key}")

    def bump(self, key: str, amount: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + amount

    async def load_configuration(self) -> None:
        async def codes(model: Any) -> dict[str, UUID]:
            rows = (
                await self.db.execute(
                    select(model.code, model.id).where(
                        model.team_id == self.team_id, model.deleted_at.is_(None)
                    )
                )
            ).all()
            return {row.code: row.id for row in rows}

        self.status = await codes(CustomerContactStatus)
        self.category = await codes(ActivityCategory)
        self.tag = await codes(ActivityActionTag)
        self.deal_type = await codes(SalesDealType)
        self.order_status = await codes(PurchaseOrderStatus)

        pipeline = (
            await self.db.execute(
                select(SalesPipeline.id).where(
                    SalesPipeline.team_id == self.team_id,
                    SalesPipeline.is_default.is_(True),
                    SalesPipeline.status_code == "published",
                )
            )
        ).scalar_one()
        self.pipeline_id = pipeline
        rows = (
            await self.db.execute(
                select(
                    SalesPipelineStage.stage_code,
                    SalesPipelineStage.id,
                    SalesPipelineStage.outcome_code,
                ).where(SalesPipelineStage.sales_pipeline_id == pipeline)
            )
        ).all()
        self.stages = {row.stage_code: (row.id, row.outcome_code) for row in rows}

        missing = [code for code in STAGE_STEPS if code not in self.stages]
        if missing:
            raise SystemExit(f"기본 영업 파이프라인에 없는 단계입니다: {missing}")

    async def seed_products(self) -> None:
        for name, category, price, shelf_life, memo in PRODUCTS:
            product_id = self.sid("product", name)
            self.products[name] = (product_id, price)
            await upsert(
                self.db,
                Product,
                {
                    "id": product_id,
                    "team_id": self.team_id,
                    "name": name,
                    "active": True,
                    "category_code": category,
                    "unit_price": price,
                    "shelf_life_months": shelf_life,
                    "memo": memo,
                    "image_storage_key": None,
                },
            )
            self.bump("product")

    async def seed_companies(self) -> None:
        ids = [self.sid("company", seed.name) for seed in COMPANIES]
        await guard_team(self.db, CustomerCompany, ids, self.team_id)
        for seed in COMPANIES:
            company_id = self.sid("company", seed.name)
            self.companies[seed.name] = company_id
            await upsert(
                self.db,
                CustomerCompany,
                {
                    "id": company_id,
                    "team_id": self.team_id,
                    "name": seed.name,
                    "region_code": seed.region,
                    "business_no": seed.business_no,
                    "created_at": at(_d(6, 1), 9),
                },
            )
            self.bump("company")

    async def seed_contacts(self) -> None:
        for seed in CONTACTS:
            contact_id = self.sid("contact", seed.key)
            self.contact_ids[seed.key] = contact_id
            owner_id = self.members[seed.owner]
            await upsert(
                self.db,
                CustomerContact,
                {
                    "id": contact_id,
                    "company_id": self.companies[seed.company],
                    "owner_member_id": owner_id,
                    "created_by_member_id": owner_id,
                    "name": seed.name,
                    "department": seed.department,
                    "job_title": seed.job_title,
                    "email": seed.email,
                    "phone": seed.phone,
                    "customer_contact_status_id": self.status[seed.status],
                    "source_code": seed.source,
                    "memo": seed.memo,
                    "visited": seed.visited,
                    "registered_at": at(seed.registered_on, 9, 30),
                },
            )
            await link(
                self.db,
                CustomerContactAssignee,
                {
                    "customer_contact_id": contact_id,
                    "member_id": owner_id,
                    "created_at": at(seed.registered_on, 9, 30),
                },
            )
            self.bump("contact")

    async def seed_deals(self) -> None:
        positions: dict[str, int] = {}
        quote_no = 0
        contract_no = 0
        for number, seed in enumerate(DEALS, start=1):
            contact = self.contacts[seed.contact]
            product_id, unit_price = self.products[seed.product]
            amount = unit_price * seed.qty
            stage_id, outcome = self.stages[seed.stage]
            position = positions.get(seed.stage, 0)
            positions[seed.stage] = position + 1

            if seed.quote is not None:
                quote_no += 1
            if seed.contract_no:
                contract_no += 1
            delivered = seed.stage == "order_delivered"

            deal_id = self.sid("deal", seed.key)
            values = {
                "id": deal_id,
                "team_id": self.team_id,
                "deal_no": f"SL-DL-2026-{number:04d}",
                "customer_company_id": self.companies[contact.company],
                "customer_contact_id": self.contact_ids[seed.contact],
                "owner_member_id": self.members[contact.owner],
                "product_id": product_id,
                "sales_pipeline_id": self.pipeline_id,
                "sales_pipeline_stage_id": stage_id,
                "title": f"{contact.company} {seed.product} {seed.qty}대",
                "description": None,
                "sales_deal_type_id": self.deal_type[seed.deal_type],
                "deal_amount": amount,
                "opened_on": seed.opened,
                "closed_on": seed.closed,
                "quote_no": f"SL-QT-2026-{quote_no:04d}" if seed.quote else None,
                "quote_issued_on": seed.quote,
                "quote_valid_until": seed.quote_valid,
                "contract_no": f"SL-CT-2026-{contract_no:04d}" if seed.contract_no else None,
                "contract_signed_on": seed.signed,
                "contract_ends_on": seed.ends,
                "warranty_terms": WARRANTY if seed.signed else None,
                "expected_delivery_at": at(seed.signed + timedelta(days=21), 14)
                if seed.signed and not delivered
                else None,
                "memo": seed.memo,
                "stage_position": position,
                "deleted_at": None,
                "created_at": at(seed.opened, 9),
                "updated_at": at(seed.closed or seed.signed or seed.quote or seed.opened, 18),
            }
            await upsert(self.db, SalesDeal, values)
            self.deals[seed.key] = {
                "seed": seed,
                "id": deal_id,
                "amount": amount,
                "unit_price": unit_price,
                "product_id": product_id,
                "owner": contact.owner,
                "company": contact.company,
                "outcome": outcome,
                **{key: values[key] for key in ("deal_no", "quote_no", "contract_no")},
            }
            self.bump("deal")
            if outcome == "confirmed":
                self.bump("confirmed_deal")

    async def _meeting(
        self,
        key: str,
        owner: str,
        day: date,
        hour: int,
        category: str,
        tag: str,
        title: str,
        contact_key: str,
        deal_key: str,
        minutes: int = 60,
        step: int | None = None,
    ) -> dict[str, Any]:
        contact = self.contacts[contact_key]
        deal = self.deals[deal_key]
        activity_id = self.sid("activity", key)
        starts = at(day, hour)
        ends = starts + timedelta(minutes=minutes)
        await upsert(
            self.db,
            Activity,
            {
                "id": activity_id,
                "team_id": self.team_id,
                "owner_member_id": self.members[owner],
                "customer_contact_id": self.contact_ids[contact_key],
                "end_user_contact_id": None,
                "activity_category_id": self.category[category],
                "title": title,
                "starts_at": starts,
                "ends_at": ends,
                "all_day": False,
                "due_at": None,
                "location": f"{contact.company} {contact.department}",
                "activity_action_tag_id": self.tag[tag],
                # 오늘 잡힌 일정은 아직 끝나지 않은 것으로 둔다.
                "completed_at": ends if day < TODAY else None,
                "note": None,
                "deleted_at": None,
                "created_at": starts - timedelta(days=2),
                "updated_at": ends,
                "product_id": deal["product_id"],
                "sales_deal_id": deal["id"],
                "purchase_order_id": None,
            },
        )
        self.bump("activity")
        record = {
            "id": activity_id,
            "key": key,
            "title": title,
            "day": day,
            "hour": hour,
            "owner": owner,
            "contact": contact_key,
            "deal": deal_key,
            "step": step,
        }
        self.by_day.setdefault((owner, day), []).append(record)
        self.meetings.append(record)
        return record

    async def seed_activities(self) -> None:
        for seed in DEALS:
            contact = self.contacts[seed.contact]
            count = STAGE_STEPS[seed.stage]
            if seed.stage == "closed_cancelled" and seed.quote is None:
                # 견적까지 가지 못하고 끝난 건은 앞 단계만 남는다.
                count = 4
            for index, day in enumerate(step_days(seed, count)):
                if day > TODAY or (seed.closed is not None and day > seed.closed):
                    break
                step = FLOW[index]
                await self._meeting(
                    f"{seed.key}-{index}",
                    contact.owner,
                    day,
                    step.hour,
                    step.category,
                    step.tag,
                    f"{contact.company} {step.label}",
                    seed.contact,
                    seed.key,
                    minutes=90 if step.category in ("demo", "delivery", "education") else 60,
                    step=index,
                )

        for owner, contact_key, deal_key, category, tag, title, hour in TODAY_MEETINGS:
            await self._meeting(
                f"TODAY-{contact_key}-{deal_key}",
                owner,
                TODAY,
                hour,
                category,
                tag,
                title,
                contact_key,
                deal_key,
            )

    # ------------------------------------------------------------ 보고서

    def _review(self, author: str, day: date) -> tuple[str, UUID | None, datetime | None]:
        """제출 시점이 오래된 것부터 확정된다. 팀장이 쓴 보고서는 검토자를 두지 않는다."""
        if author == MANAGER:
            return "approved", None, None
        if day < _d(8, 1):
            return "approved", self.members[MANAGER], at(day + timedelta(days=2), 10)
        if day < _d(8, 18):
            return "submitted", None, None
        return "draft", None, None

    async def _report(
        self,
        key: str,
        author: str,
        kind: str,
        day: date,
        template: dict[str, Any],
        content: dict[str, Any],
        *,
        period: tuple[date, date] | None = None,
        source_activity: UUID | None = None,
        activity_ids: tuple[UUID, ...] = (),
        note: str | None = None,
        transcript: str | None = None,
    ) -> None:
        status, reviewer, reviewed_at = self._review(author, day)
        report_id = self.sid("report", key)
        await upsert(
            self.db,
            Report,
            {
                "id": report_id,
                "team_id": self.team_id,
                "author_member_id": self.members[author],
                "recipient_member_id": None
                if author == MANAGER or kind == "meeting"
                else self.members[MANAGER],
                "template_snapshot": template,
                "source_activity_id": source_activity,
                "report_kind": kind,
                "report_date": day,
                "period_start": period[0] if period else None,
                "period_end": period[1] if period else None,
                "status_code": status,
                "content": content,
                "transcript": transcript,
                "source_snapshot": None,
                "ai_evidence": None,
                "note": note,
                "reviewed_by_member_id": reviewer,
                "reviewed_at": reviewed_at,
                "created_at": at(day, 18),
                "updated_at": reviewed_at or at(day, 18),
            },
        )
        for activity_id in activity_ids:
            await link(
                self.db, ReportActivity, {"report_id": report_id, "activity_id": activity_id}
            )
        self.bump("report")
        self.bump(f"report_{kind}")

    async def seed_meeting_reports(self) -> None:
        """견적 전달·계약 체결·사용 교육 미팅과, 아직 견적 전인 딜의 첫 방문 미팅에 붙인다."""
        for record in self.meetings:
            step = record["step"]
            seed = self.deals[record["deal"]]["seed"]
            if step not in (1, 5, 7, 9):
                continue
            if step == 1 and seed.quote is not None:
                continue

            deal = self.deals[record["deal"]]
            contact = self.contacts[record["contact"]]
            reaction, decision, following = (
                text.format(product=seed.product, qty=seed.qty, amount=won(deal["amount"]))
                for text in MEETING_NOTES[step]
            )
            values = {
                "attendees": f"{contact.name} {contact.job_title}, {record['owner']} 담당",
                "reaction": reaction,
                "decision": decision,
                "next": following,
                "note": "",
            }
            evidence = f"{decision} {following}"
            status, _reviewer, _reviewed = self._review(record["owner"], record["day"])
            # 아직 손대는 중인 초안에는 AI 초안이 아직 없다.
            ai_values = {} if status == "draft" else dict(values)
            await self._report(
                f"MT-{record['key']}",
                record["owner"],
                "meeting",
                record["day"],
                MEETING_TEMPLATE,
                {
                    "time": f"{record['hour']:02d}:00",
                    "hospital": contact.company,
                    "dept": contact.department,
                    "contact": contact.name,
                    "product": seed.product,
                    "place": f"{contact.company} {contact.department}",
                    "title": record["title"],
                    "values": values,
                    "attachments": [],
                    "evidence": evidence,
                    "ai_values": ai_values,
                    "ai_evidence": evidence if ai_values else None,
                    "ai_generated_at": at(record["day"], 18).isoformat() if ai_values else None,
                },
                source_activity=record["id"],
                activity_ids=(record["id"],),
            )

    def _activity_entries(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": str(record["id"]),
                "source": "캘린더",
                "title": record["title"],
                "desc": f"{record['day']:%m월 %d일} {record['hour']:02d}:00",
                "included": True,
                "refId": str(record["id"]),
            }
            for record in records
        ]

    def confirmed_of(self, owner: str, month: date) -> tuple[int, int]:
        """그 달에 계약이 확정된 건수와 금액. 대시보드의 매출 집계와 같은 기준이다."""
        total = 0
        count = 0
        for deal in self.deals.values():
            seed: DealSeed = deal["seed"]
            if deal["outcome"] != "confirmed" or seed.signed is None:
                continue
            if deal["owner"] != owner or month_start(seed.signed) != month:
                continue
            total += deal["amount"]
            count += 1
        return count, total

    def target_of(self, owner: str, month: date) -> int:
        return sum(
            amount
            for name, number, _company, amount in SALES_TARGETS
            if name == owner and _d(number, 1) == month
        )

    async def seed_daily_reports(self) -> None:
        for owner in OWNER_EMAILS:
            days = sorted(
                day
                for (name, day), records in self.by_day.items()
                if name == owner and len(records) >= 2 and day <= TODAY
            )
            for day in days[-10:]:
                records = sorted(self.by_day[(owner, day)], key=lambda item: item["hour"])
                titles = "\n".join(f"- {record['title']}" for record in records)
                held = {self.deals[record["deal"]]["seed"] for record in records}
                stalled = [seed for seed in held if seed.closed is not None]
                issue = (
                    "\n".join(
                        f"- {self.contacts[seed.contact].company}: {seed.memo}" for seed in stalled
                    )
                    if stalled
                    else "특이사항 없습니다."
                )
                nxt = sorted(
                    (
                        item
                        for (name, other), records2 in self.by_day.items()
                        if name == owner and other > day
                        for item in records2
                    ),
                    key=lambda item: (item["day"], item["hour"]),
                )[:3]
                plan = (
                    "\n".join(f"- {item['day']:%m월 %d일} {item['title']}" for item in nxt)
                    if nxt
                    else "- 미회신 견적 팔로업"
                )
                await self._report(
                    f"DR-{owner}-{day:%Y%m%d}",
                    owner,
                    "daily",
                    day,
                    DAILY_TEMPLATE,
                    {
                        "approver": f"{MANAGER} 팀장",
                        "values": {
                            "summary": titles,
                            "issue": issue,
                            "next": plan,
                            "competitor": "",
                        },
                        "activities": self._activity_entries(records),
                        "attachments": [],
                    },
                    note=f"활동 {len(records)}건",
                    activity_ids=tuple(record["id"] for record in records),
                )

    async def seed_weekly_reports(self) -> None:
        current = week_start(TODAY)
        weeks = [current - timedelta(days=7 * step) for step in (3, 2, 1)]
        for owner in OWNER_EMAILS:
            for start in weeks:
                end = start + timedelta(days=6)
                records = sorted(
                    (
                        item
                        for (name, day), items in self.by_day.items()
                        if name == owner and start <= day <= end
                        for item in items
                    ),
                    key=lambda item: (item["day"], item["hour"]),
                )
                if not records:
                    continue
                signed = [
                    deal
                    for deal in self.deals.values()
                    if deal["owner"] == owner
                    and deal["seed"].signed is not None
                    and start <= deal["seed"].signed <= end
                ]
                quoted = [
                    deal
                    for deal in self.deals.values()
                    if deal["owner"] == owner
                    and deal["seed"].quote is not None
                    and start <= deal["seed"].quote <= end
                ]
                result = [f"- 고객 활동 {len(records)}건"]
                if quoted:
                    result.append(
                        "- 견적 발송 "
                        + ", ".join(f"{deal['company']} {won(deal['amount'])}" for deal in quoted)
                    )
                if signed:
                    result.append(
                        "- 계약 체결 "
                        + ", ".join(f"{deal['company']} {won(deal['amount'])}" for deal in signed)
                    )
                open_quotes = [
                    deal
                    for deal in self.deals.values()
                    if deal["owner"] == owner
                    and deal["seed"].quote_valid is not None
                    and deal["seed"].signed is None
                    and deal["seed"].closed is None
                ]
                risk = (
                    "\n".join(
                        f"- {deal['company']} 견적 유효기간 {deal['seed'].quote_valid:%m월 %d일}"
                        for deal in open_quotes[:3]
                    )
                    if open_quotes
                    else "특이 리스크 없습니다."
                )
                await self._report(
                    f"WR-{owner}-{start:%Y%m%d}",
                    owner,
                    "weekly",
                    start,
                    WEEKLY_TEMPLATE,
                    {
                        "approver": f"{MANAGER} 팀장",
                        "values": {
                            "result": "\n".join(result),
                            "plan": "- 미회신 견적 팔로업\n- 진행 중 발주 입고일 확인",
                            "risk": risk,
                        },
                        "activities": self._activity_entries(records),
                        "attachments": [],
                    },
                    period=(start, end),
                    note=f"활동 {len(records)}건",
                    activity_ids=tuple(record["id"] for record in records),
                )

    async def seed_monthly_reports(self) -> None:
        # 8월은 아직 진행 중이라 쓰지 않는다.
        for month in (_d(6, 1), _d(7, 1)):
            end = (month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            for owner in OWNER_EMAILS:
                count, amount = self.confirmed_of(owner, month)
                target = self.target_of(owner, month)
                records = sorted(
                    (
                        item
                        for (name, day), items in self.by_day.items()
                        if name == owner and month <= day <= end
                        for item in items
                    ),
                    key=lambda item: (item["day"], item["hour"]),
                )
                if not records:
                    continue
                rate = f"{amount / target * 100:.1f}%" if target else "목표 미설정"
                await self._report(
                    f"MR-{owner}-{month:%Y%m}",
                    owner,
                    "monthly",
                    month,
                    MONTHLY_TEMPLATE,
                    {
                        "approver": f"{MANAGER} 팀장",
                        "values": {
                            "perf": f"- 계약 {count}건 {won(amount)}\n- 고객 활동 {len(records)}건",
                            "gap": f"- 목표 {won(target)} 대비 달성률 {rate}",
                            "focus": "- 견적 진행 건의 계약 전환\n- 확정 건의 발주·납품 일정 관리",
                        },
                        "activities": self._activity_entries(records),
                        "attachments": [],
                    },
                    period=(month, end),
                    note=f"계약 {count}건 · 활동 {len(records)}건",
                )

    # ------------------------------------------------------------ 발주·불만·목표·공지

    async def seed_orders(self) -> None:
        for number, seed in enumerate(ORDERS, start=1):
            deal = self.deals[seed.deal]
            order_id = self.sid("order", seed.key)
            await upsert(
                self.db,
                PurchaseOrder,
                {
                    "id": order_id,
                    "team_id": self.team_id,
                    "order_no": f"SL-PO-2026-{number:04d}",
                    "sales_deal_id": deal["id"],
                    "supplier_name": seed.supplier,
                    "purchase_order_status_id": self.order_status[seed.status],
                    "ordered_on": seed.ordered,
                    "due_on": seed.due,
                    "expected_receipt_on": seed.receipt,
                    "memo": seed.memo,
                    "deleted_at": None,
                    "created_at": at(seed.ordered, 10),
                    "updated_at": at(min(seed.receipt, TODAY), 17),
                },
            )
            await upsert(
                self.db,
                PurchaseOrderItem,
                {
                    "id": self.sid("order_item", seed.key),
                    "purchase_order_id": order_id,
                    "product_id": deal["product_id"],
                    "quantity": seed.qty,
                    "unit_price": deal["unit_price"],
                    "position": 0,
                },
            )
            self.bump("order")
            self.bump("order_amount", seed.qty * deal["unit_price"])

    async def seed_supports(self) -> None:
        for seed in SUPPORTS:
            deal = self.deals[seed.deal]
            request_id = self.sid("support", seed.key)
            await upsert(
                self.db,
                SupportRequest,
                {
                    "id": request_id,
                    "team_id": self.team_id,
                    "customer_company_id": self.companies[deal["company"]],
                    "sales_deal_id": deal["id"],
                    "assignee_member_id": self.members[deal["owner"]],
                    "title": seed.title,
                    "body": seed.body,
                    "is_urgent": seed.urgent,
                    "status_code": seed.status,
                    "occurred_at": at(seed.occurred, 11),
                    "registered_at": at(seed.occurred, 14),
                },
            )
            self.bump("support")
            for index, (body, day) in enumerate(seed.responses, start=1):
                await upsert(
                    self.db,
                    SupportResponse,
                    {
                        "id": self.sid("support_response", f"{seed.key}-{index}"),
                        "support_request_id": request_id,
                        "responder_member_id": self.members[deal["owner"]],
                        "body": body,
                        "responded_at": at(day, 16),
                    },
                )
                self.bump("support_response")

    async def seed_targets(self) -> None:
        for owner, number, company, amount in SALES_TARGETS:
            await upsert(
                self.db,
                SalesTarget,
                {
                    "id": self.sid("target", f"{owner}-{number}-{company}"),
                    "owner_member_id": self.members[owner],
                    "customer_company_id": self.companies[company],
                    "target_month": _d(number, 1),
                    "target_amount": amount,
                },
            )
            self.bump("sales_target")

    async def seed_notices(self) -> None:
        for seed in NOTICES:
            notice_id = self.sid("notice", seed.key)
            await upsert(
                self.db,
                Notice,
                {
                    "id": notice_id,
                    "team_id": self.team_id,
                    "author_member_id": self.members[MANAGER],
                    "type": seed.type,
                    "tag": seed.tag,
                    "title": seed.title,
                    "body": seed.body,
                    "image_storage_key": None,
                    "image_alt": None,
                    "published_at": at(seed.published_on, 9),
                    "due_at": at(seed.due_on, 18) if seed.due_on else None,
                    "due_text": seed.due_text,
                    "display_start_date": seed.published_on,
                    "display_end_date": seed.display_end,
                    "is_hidden": False,
                    "sort_order": seed.sort_order,
                    "updated_at": at(seed.published_on, 9),
                    "deleted_at": None,
                },
            )
            self.bump("notice")
            for name in seed.targets:
                await link(
                    self.db,
                    NoticeTarget,
                    {
                        "notice_id": notice_id,
                        "member_id": self.members[name],
                        "created_at": at(seed.published_on, 9),
                    },
                )

    async def run(self) -> None:
        await self.load_configuration()
        await self.seed_products()
        await self.seed_companies()
        await self.seed_contacts()
        await self.seed_deals()
        await self.seed_activities()
        await self.seed_meeting_reports()
        await self.seed_daily_reports()
        await self.seed_weekly_reports()
        await self.seed_monthly_reports()
        await self.seed_orders()
        await self.seed_supports()
        await self.seed_targets()
        await self.seed_notices()


# ---------------------------------------------------------------- 실행


async def resolve_team(db: AsyncSession) -> tuple[UUID, dict[str, UUID]]:
    """4개 계정을 이메일로 찾고 그 팀을 작업 대상으로 삼는다."""
    rows = (
        await db.execute(
            select(Member.id, Member.team_id, Member.display_name, Member.email).where(
                Member.email.in_(OWNER_EMAILS.values())
            )
        )
    ).all()
    by_email = {row.email: row for row in rows}
    missing = [email for email in OWNER_EMAILS.values() if email not in by_email]
    if missing:
        raise SystemExit(f"다음 계정을 찾지 못했습니다: {missing}")

    team_ids = {row.team_id for row in rows}
    if len(team_ids) != 1:
        raise SystemExit("네 계정이 서로 다른 팀에 있습니다. 팀을 먼저 정리하세요.")
    team_id = team_ids.pop()

    team_name = (await db.execute(select(Team.name).where(Team.id == team_id))).scalar_one_or_none()
    if team_name != TEAM_NAME:
        raise SystemExit(f"대상 팀 이름이 '{TEAM_NAME}' 이 아닙니다: {team_name}")

    members: dict[str, UUID] = {}
    for name, email in OWNER_EMAILS.items():
        row = by_email[email]
        if row.display_name != name:
            raise SystemExit(f"{email} 의 이름이 '{name}' 이 아닙니다: {row.display_name}")
        members[name] = row.id
    return team_id, members


class _DryRun(Exception):
    """dry-run 에서 트랜잭션을 되돌리기 위한 내부 신호."""


async def seed(*, dry_run: bool = False) -> None:
    try:
        async with get_sessionmaker()() as session, session.begin():
            team_id, members = await resolve_team(session)
            print(f"팀 {TEAM_NAME} ({team_id})")
            for name, member_id in members.items():
                print(f"  {name} <- {member_id}")

            # 이 팀에는 lookup 과 파이프라인이 아직 없다. 프로젝트 기본값을 그대로 넣는다.
            await seed_team_configuration(session, team_id)
            await session.flush()

            seeder = Seeder(session, team_id, members)
            await seeder.run()

            print("\n넣은 행 수")
            for key in sorted(seeder.counts):
                value = seeder.counts[key]
                print(f"  {key}: {value:,}" if key.endswith("amount") else f"  {key}: {value}")

            if dry_run:
                raise _DryRun
    except _DryRun:
        print("\n--dry-run 이므로 아무것도 저장하지 않았습니다.")
        return
    print("\n샘플 데이터를 저장했습니다.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="브레이스 영업1팀에 2026-06-01~08-25 샘플 업무 데이터를 넣습니다."
    )
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 봅니다.")
    args = parser.parse_args(argv)
    asyncio.run(seed(dry_run=args.dry_run))


if __name__ == "__main__":
    main()

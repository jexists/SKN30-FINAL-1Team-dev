"""데모 데이터셋의 고정 상수.

여기에는 값만 둔다. DB 접근과 날짜 계산은 seed_demo_dataset 이 한다.
실제 고객 데이터가 아니며 이메일·전화번호·사업자번호도 통신 불가능한 값이다.

자료실 본문을 실행 시점에 LLM 으로 만들지 않고 여기에 고정해 둔 이유는, 매번 문구가
달라지면 시더가 멱등하지 않고 검증도 성립하지 않기 때문이다. 실행 시점에 하는 일은
이 상수를 .docx 로 렌더해 올리는 것뿐이다.
"""

from typing import NamedTuple

TEAM_NAME = "SalesLuv 데모영업팀"
SEED_TAG = "demo2026"


# ---------------------------------------------------------------- 구성원


class MemberSeed(NamedTuple):
    key: str
    email: str
    display_name: str
    role_code: str
    job_title: str


# example.com 은 RFC 2606 예약 도메인이라 실제로 메일이 나가지 않는다.
# 팀장은 member_one_manager_per_team_uq 때문에 한 명뿐이다.
MEMBERS = (
    MemberSeed("한지현", "demo.manager@example.com", "한지현", "manager", "영업팀장"),
    MemberSeed("서민우", "demo.sales1@example.com", "서민우", "member", "영업 담당"),
    MemberSeed("오재훈", "demo.sales2@example.com", "오재훈", "member", "영업 담당"),
    MemberSeed("배수연", "demo.sales3@example.com", "배수연", "member", "영업 담당"),
    MemberSeed("노가람", "demo.sales4@example.com", "노가람", "member", "영업 담당"),
)
MANAGER = "한지현"
SALES = tuple(m.key for m in MEMBERS if m.role_code == "member")


# ---------------------------------------------------------------- 제품


class ProductSeed(NamedTuple):
    name: str
    category_code: str  # system | probe | consumable (CHECK 로 이 셋만 허용)
    unit_price: int
    shelf_life_months: int | None
    memo: str


# data/sample/Sales_DB.xlsx 품목리스트의 LR/LP 명명체계와 가격대를 그대로 이었다.
# 앞의 11개가 원본에 있는 모델이고 나머지는 같은 체계로 늘린 것이다.
PRODUCTS = (
    # --- system 12
    ProductSeed("LR1000", "system", 4_500_000, None, "보급형 레이저 시스템"),
    ProductSeed("LR2000", "system", 5_200_000, None, "표준형 레이저 시스템"),
    ProductSeed("LR-PRO", "system", 6_000_000, None, "고출력 레이저 시스템"),
    ProductSeed("LR-CORE1", "system", 4_200_000, None, "코어 모듈 1형"),
    ProductSeed("LR-CORE2", "system", 4_800_000, None, "코어 모듈 2형"),
    ProductSeed("LR-CORE3", "system", 5_400_000, None, "코어 모듈 3형"),
    ProductSeed("LR1500", "system", 4_850_000, None, "보급형 상위 모델"),
    ProductSeed("LR2500", "system", 5_700_000, None, "표준형 상위 모델"),
    ProductSeed("LR-PRO2", "system", 7_200_000, None, "고출력 2세대"),
    ProductSeed("LR-PRO-X", "system", 9_800_000, None, "최상위 모델, 듀얼 채널"),
    ProductSeed("LR-MINI", "system", 3_300_000, None, "이동형 소형 시스템"),
    ProductSeed("LR-DUO", "system", 8_100_000, None, "2채널 동시 조사형"),
    # --- probe 14
    ProductSeed("LP1000", "probe", 130_000, 24, "표준 프로브"),
    ProductSeed("LP1500", "probe", 145_000, 24, "표준 프로브 중형"),
    ProductSeed("LP2000", "probe", 175_000, 24, "표준 프로브 대형"),
    ProductSeed("LP100", "probe", 180_000, 36, "정밀 프로브 소형"),
    ProductSeed("LP200", "probe", 240_000, 36, "정밀 프로브 중형"),
    ProductSeed("LP-S1", "probe", 210_000, 24, "표면 조사용 프로브"),
    ProductSeed("LP-S2", "probe", 265_000, 24, "표면 조사용 광폭 프로브"),
    ProductSeed("LP-D1", "probe", 320_000, 36, "심부 조사용 프로브"),
    ProductSeed("LP-D2", "probe", 385_000, 36, "심부 조사용 고출력 프로브"),
    ProductSeed("LP-N1", "probe", 155_000, 24, "협부위 전용 프로브"),
    ProductSeed("LP-N2", "probe", 168_000, 24, "협부위 전용 연장형"),
    ProductSeed("LP-FLEX", "probe", 295_000, 30, "가변 각도 프로브"),
    ProductSeed("LP-ULTRA", "probe", 430_000, 36, "초정밀 프로브"),
    ProductSeed("LP-ULTRA2", "probe", 480_000, 36, "초정밀 프로브 2세대"),
    # --- consumable 24
    ProductSeed("LC-GEL-250", "consumable", 18_000, 18, "조사용 젤 250ml"),
    ProductSeed("LC-GEL-500", "consumable", 31_000, 18, "조사용 젤 500ml"),
    ProductSeed("LC-GEL-1L", "consumable", 54_000, 18, "조사용 젤 1L"),
    ProductSeed("LC-TIP-S", "consumable", 24_000, 24, "일회용 팁 소형 50개입"),
    ProductSeed("LC-TIP-M", "consumable", 29_000, 24, "일회용 팁 중형 50개입"),
    ProductSeed("LC-TIP-L", "consumable", 35_000, 24, "일회용 팁 대형 50개입"),
    ProductSeed("LC-FILTER-A", "consumable", 62_000, 12, "광학 필터 A형"),
    ProductSeed("LC-FILTER-B", "consumable", 74_000, 12, "광학 필터 B형"),
    ProductSeed("LC-FILTER-C", "consumable", 88_000, 12, "광학 필터 C형"),
    ProductSeed("LC-COVER-50", "consumable", 21_000, 24, "프로브 커버 50매"),
    ProductSeed("LC-COVER-200", "consumable", 68_000, 24, "프로브 커버 200매"),
    ProductSeed("LC-PAD-S", "consumable", 19_000, 12, "쿨링 패드 소형"),
    ProductSeed("LC-PAD-L", "consumable", 27_000, 12, "쿨링 패드 대형"),
    ProductSeed("LC-CABLE-2M", "consumable", 96_000, None, "프로브 연결 케이블 2m"),
    ProductSeed("LC-CABLE-4M", "consumable", 128_000, None, "프로브 연결 케이블 4m"),
    ProductSeed("LC-FUSE-SET", "consumable", 42_000, None, "퓨즈 교체 세트"),
    ProductSeed("LC-LENS-A", "consumable", 155_000, 24, "집속 렌즈 A형"),
    ProductSeed("LC-LENS-B", "consumable", 182_000, 24, "집속 렌즈 B형"),
    ProductSeed("LC-CLEAN-KIT", "consumable", 47_000, 12, "광학부 세정 키트"),
    ProductSeed("LC-CALIB-KIT", "consumable", 210_000, 12, "출력 교정 키트"),
    ProductSeed("LC-ARM-STD", "consumable", 174_000, None, "거치 암 표준형"),
    ProductSeed("LC-ARM-EXT", "consumable", 226_000, None, "거치 암 연장형"),
    ProductSeed("LC-CART", "consumable", 240_000, None, "이동형 카트"),
    ProductSeed("LC-FOOTSW", "consumable", 88_000, None, "풋 스위치"),
)


# ---------------------------------------------------------------- 고객 담당자

# 고객사 담당자 이름 풀. 성과 이름을 조합해 쓴다. 실존 인물과 무관하다.
CONTACT_SURNAMES = (
    "김",
    "이",
    "박",
    "최",
    "정",
    "강",
    "조",
    "윤",
    "장",
    "임",
    "한",
    "오",
    "서",
    "신",
    "권",
    "황",
)
CONTACT_GIVEN = (
    "도윤",
    "서준",
    "하은",
    "지우",
    "예린",
    "민재",
    "수아",
    "지호",
    "다현",
    "현우",
    "채원",
    "은우",
    "가온",
    "리아",
    "태오",
    "소율",
    "준서",
    "나윤",
    "시우",
    "유진",
)
CONTACT_DEPARTMENTS = (
    "구매팀",
    "총무팀",
    "진료협력팀",
    "재활치료실",
    "물리치료실",
    "원무팀",
    "시설관리팀",
    "간호부",
    "행정지원팀",
    "기획실",
)
CONTACT_TITLES = ("팀장", "과장", "대리", "주임", "실장", "부장", "차장")

# 담당자 이메일의 로컬 파트. 순서를 맞춘 병렬 튜플로 두면 한쪽만 고쳤을 때 조용히 다른
# 사람 이름이 붙으므로 dict 로 둔다. 도메인은 MEMBERS 와 같은 example.com 이다.
CONTACT_SURNAME_ROMAN = {
    "김": "kim",
    "이": "lee",
    "박": "park",
    "최": "choi",
    "정": "jung",
    "강": "kang",
    "조": "cho",
    "윤": "yoon",
    "장": "jang",
    "임": "lim",
    "한": "han",
    "오": "oh",
    "서": "seo",
    "신": "shin",
    "권": "kwon",
    "황": "hwang",
}
CONTACT_GIVEN_ROMAN = {
    "도윤": "doyun",
    "서준": "seojun",
    "하은": "haeun",
    "지우": "jiwoo",
    "예린": "yerin",
    "민재": "minjae",
    "수아": "sua",
    "지호": "jiho",
    "다현": "dahyun",
    "현우": "hyunwoo",
    "채원": "chaewon",
    "은우": "eunwoo",
    "가온": "gaon",
    "리아": "ria",
    "태오": "taeo",
    "소율": "soyul",
    "준서": "junseo",
    "나윤": "nayun",
    "시우": "siwoo",
    "유진": "yujin",
}

# 담당자 메모. 딜이 있는 담당자 일부에만 붙는다. 전부 메모가 있으면 그것대로 가짜다.
CONTACT_MEMOS = (
    "구매 결정은 원장 승인 필요.",
    "예산 편성 시기는 매년 11월.",
    "오전 진료가 끝나는 13시 이후에 통화 가능.",
    "기존 장비 리스 만료 시점을 함께 봐야 함.",
    "시연은 휴진일에만 가능하다고 함.",
    "경쟁사 견적을 이미 받아 둔 상태.",
    "소모품 단가에 민감. 연간 물량 기준 협의 선호.",
    "분원 확장 계획이 있어 추가 도입 여지 있음.",
)


# ---------------------------------------------------------------- 공지 · 지시


class NoticeSeed(NamedTuple):
    key: str
    type: str  # NOTICE | DIRECTIVE (CHECK)
    tag: str
    title: str
    body: str  # HTML. 저장 전 sanitize 되므로 단순 태그만 쓴다.
    start_offset: int  # base_date 기준 게시 시작일
    end_offset: int | None  # 게시 종료일. None 이면 무기한
    due_offset: int | None  # 처리 기한. DIRECTIVE 만 쓴다
    targets: tuple[str, ...]  # DIRECTIVE 수신자. NOTICE 는 빈 튜플
    sort_order: int


NOTICES = (
    NoticeSeed(
        "N01",
        "NOTICE",
        "공지",
        "4분기 영업 목표와 배분 기준 안내",
        "<p>4분기 팀 목표는 3억 2천만원입니다. "
        "담당자별 목표는 영업현황 화면의 월 목표에서 확인해 주세요.</p>"
        "<p>배분 기준은 3분기 실적 60%, 담당 고객사 수 40% 입니다.</p>",
        -45,
        None,
        None,
        (),
        0,
    ),
    NoticeSeed(
        "N02",
        "NOTICE",
        "정책",
        "견적서 유효기간 30일 원칙 재공지",
        "<p>견적 유효기간은 발행일로부터 30일이 원칙입니다. "
        "연장이 필요하면 팀장 승인 후 재발행해 주세요.</p>"
        "<p>유효기간이 지난 견적으로 계약을 진행한 사례가 있어 다시 안내합니다.</p>",
        -38,
        None,
        None,
        (),
        1,
    ),
    NoticeSeed(
        "N03",
        "NOTICE",
        "제품",
        "LR-PRO2 출시 및 기존 모델 단가 조정",
        "<p>LR-PRO2 가 출시되었습니다. 기존 LR-PRO 대비 출력이 20% 높고 듀얼 채널을 지원합니다.</p>"
        "<ul><li>LR-PRO2 판매단가 "
        "7,200,000원</li><li>LR-PRO 단가 동결, 재고 소진 시까지 판매</li></ul>",
        -30,
        None,
        None,
        (),
        2,
    ),
    NoticeSeed(
        "N04",
        "NOTICE",
        "교육",
        "신규 입사자 제품 교육 일정",
        "<p>노가람 담당자의 제품 교육을 다음 주 화·목 "
        "오후에 진행합니다. 참관을 원하는 분은 회신해 주세요.</p>",
        -24,
        -10,
        None,
        (),
        3,
    ),
    NoticeSeed(
        "N05",
        "NOTICE",
        "안내",
        "하반기 휴가 일정 취합",
        "<p>9월~10월 휴가 일정을 회신해 주세요. 고객 "
        "방문 일정이 겹치지 않도록 미리 조율 바랍니다.</p>",
        -20,
        -6,
        None,
        (),
        4,
    ),
    NoticeSeed(
        "N06",
        "NOTICE",
        "제도",
        "의료기기 유통·판매질서 규칙 준수 안내",
        "<p>의료기기 유통 및 판매질서 유지에 관한 규칙에 따라 경제적 이익 제공이 금지됩니다.</p>"
        "<p>고객사 방문 시 제공 가능한 범위는 자료실의 관련 자료를 확인해 주세요.</p>",
        -16,
        None,
        None,
        (),
        5,
    ),
    NoticeSeed(
        "N07",
        "NOTICE",
        "공지",
        "발주 마감 시각 변경",
        "<p>공급사 요청으로 당일 발주 마감이 오후 4시에서 오후 3시로 변경되었습니다.</p>",
        -11,
        None,
        None,
        (),
        6,
    ),
    NoticeSeed(
        "N08",
        "NOTICE",
        "안내",
        "고객불만 접수 후 1영업일 내 1차 응대",
        "<p>C/S 접수 건은 1영업일 안에 1차 응대를 남겨 "
        "주세요. 원인 파악 전이라도 접수 확인은 필요합니다.</p>",
        -7,
        None,
        None,
        (),
        7,
    ),
    NoticeSeed(
        "N09",
        "NOTICE",
        "제품",
        "LC-FILTER-A 일시 품절 안내",
        "<p>LC-FILTER-A 가 공급사 사정으로 3주간 품절입니다. 대체 품목은 LC-FILTER-B 입니다.</p>",
        -2,
        14,
        None,
        (),
        8,
    ),
    NoticeSeed(
        "N10",
        "NOTICE",
        "공지",
        "10월 전사 워크숍 사전 안내",
        "<p>10월 중 1박 2일 워크숍이 예정되어 있습니다. 확정 일정은 추후 공지합니다.</p>",
        3,
        40,
        None,
        (),
        9,
    ),
)

DIRECTIVES = (
    NoticeSeed(
        "D01",
        "DIRECTIVE",
        "요청",
        "유효기간 만료 견적 재확인",
        "<p>유효기간이 지난 견적 건은 고객사에 재발송 "
        "여부를 확인하고 결과를 딜 메모에 남겨 주세요.</p>",
        -34,
        None,
        -28,
        ("서민우", "오재훈"),
        0,
    ),
    NoticeSeed(
        "D02",
        "DIRECTIVE",
        "보고",
        "3분기 마감 실적 정리",
        "<p>3분기 확정 계약 건을 정리해 월간보고서로 제출해 주세요.</p>",
        -27,
        None,
        -22,
        ("서민우", "오재훈", "배수연"),
        1,
    ),
    NoticeSeed(
        "D03",
        "DIRECTIVE",
        "확인",
        "장기 미접촉 고객사 정리",
        "<p>90일 이상 접촉이 없는 담당 고객사를 확인하고 재접촉 계획을 일정으로 등록해 주세요.</p>",
        -21,
        None,
        -15,
        ("서민우", "오재훈", "배수연", "노가람"),
        2,
    ),
    NoticeSeed(
        "D04",
        "DIRECTIVE",
        "요청",
        "발주 지연 건 입고일 재확인",
        "<p>생산 중 상태로 2주 이상 머문 발주의 입고 예정일을 공급사에 다시 확인해 주세요.</p>",
        -13,
        None,
        -8,
        ("배수연",),
        3,
    ),
    NoticeSeed(
        "D05",
        "DIRECTIVE",
        "확인",
        "긴급 C/S 처리 현황 점검",
        "<p>긴급으로 접수된 C/S 중 미완료 건의 진행 상황을 정리해 회신해 주세요.</p>",
        -9,
        None,
        -4,
        ("오재훈", "배수연"),
        4,
    ),
    NoticeSeed(
        "D06",
        "DIRECTIVE",
        "보고",
        "이번 주 주간보고 제출",
        "<p>이번 주 주간보고를 금요일 오전까지 제출해 주세요.</p>",
        -3,
        None,
        0,
        ("서민우", "오재훈", "배수연", "노가람"),
        5,
    ),
    NoticeSeed(
        "D07",
        "DIRECTIVE",
        "요청",
        "LC-FILTER-A 품절 고객 사전 안내",
        "<p>LC-FILTER-A 를 정기 구매하는 고객사에 품절과 대체 품목을 미리 안내해 주세요.</p>",
        -1,
        None,
        0,
        ("서민우", "노가람"),
        6,
    ),
    NoticeSeed(
        "D08",
        "DIRECTIVE",
        "확인",
        "신규 병원 리스트 1차 컨택",
        "<p>새로 배정된 고객사 중 미컨택 건에 첫 통화 일정을 잡아 주세요.</p>",
        1,
        None,
        7,
        ("노가람",),
        7,
    ),
    NoticeSeed(
        "D09",
        "DIRECTIVE",
        "요청",
        "LR-PRO2 데모 대상 선정",
        "<p>LR-PRO2 데모를 진행할 고객사 3곳을 선정해 회신해 주세요.</p>",
        4,
        None,
        12,
        ("서민우", "오재훈"),
        8,
    ),
    NoticeSeed(
        "D10",
        "DIRECTIVE",
        "보고",
        "10월 목표 대비 중간 점검",
        "<p>10월 중순 기준 목표 대비 진행 상황을 정리해 주세요.</p>",
        10,
        None,
        25,
        ("서민우", "오재훈", "배수연", "노가람"),
        9,
    ),
)


# ---------------------------------------------------------------- 고객불만


class SupportSeed(NamedTuple):
    key: str
    title: str
    body: str
    status_code: str  # received | diagnosing | in_progress | completed (CHECK)
    is_urgent: bool
    occurred_offset: int  # base_date 기준. 접수는 이 날 또는 다음 날
    responses: tuple[str, ...]  # 시간 순 응대 내용. 마지막이 처리 결과다.


# support_request 에는 카테고리·우선순위 컬럼이 없다. 있는 축은 is_urgent 와
# status_code 넷뿐이라 다양성은 제목·본문·응대 이력으로 만든다.
# 주제 배분: 제품불량 12 · 사용법 10 · 납기 9 · 소모품 8 · 설치 7 · 정산 6 · 계약 5 · 기타 3
SUPPORTS = (
    # ---- completed 20
    SupportSeed(
        "C01",
        "설치 후 프로브 인식 불량",
        "설치 당일부터 LP2000 프로브를 연결해도 "
        "본체가 인식하지 못합니다. 다른 포트에 꽂아도 같습니다.",
        "completed",
        True,
        -96,
        (
            "접수 확인 후 원격으로 케이블 연결 상태를 점검했습니다.",
            "커넥터 핀 손상이 확인되어 케이블을 교체 발송했습니다.",
            "교체 케이블 적용 후 정상 인식되는 것을 확인했습니다. 종결합니다.",
        ),
    ),
    SupportSeed(
        "C02",
        "출력이 설정값보다 낮게 나옴",
        "동일 설정에서 출력이 이전보다 약하다는 시술자 의견이 있습니다. 점검 요청드립니다.",
        "completed",
        True,
        -88,
        (
            "출력 로그를 받아 확인했습니다. 설정 대비 12% 낮게 측정됩니다.",
            "광학부 오염으로 판단되어 방문 세정과 출력 교정을 진행했습니다.",
            "교정 후 오차 2% 이내로 회복되었습니다. 6개월 주기 세정을 안내드렸습니다.",
        ),
    ),
    SupportSeed(
        "C03",
        "납품 일정이 예정보다 지연됨",
        "계약 시 안내받은 납기보다 2주 늦어진다고 들었습니다. 정확한 일정을 알려주세요.",
        "completed",
        False,
        -84,
        (
            "공급사 생산 일정을 확인했습니다. 10영업일 지연이 맞습니다.",
            "지연 사유와 확정 입고일을 문서로 회신드렸습니다. 종결합니다.",
        ),
    ),
    SupportSeed(
        "C04",
        "소모품 정기 배송 누락",
        "매월 초 오던 LC-GEL-500 이 이번 달에 오지 않았습니다.",
        "completed",
        False,
        -80,
        (
            "정기 배송 목록에서 누락된 것을 확인했습니다.",
            "당일 특송으로 발송했고 정기 목록을 복구했습니다. 종결합니다.",
        ),
    ),
    SupportSeed(
        "C05",
        "사용 교육 추가 요청",
        "신규 간호 인력이 들어와 장비 사용 교육을 한 번 더 받고 싶습니다.",
        "completed",
        False,
        -76,
        (
            "교육 일정을 협의해 방문 교육을 진행했습니다.",
            "교육 자료를 전달드렸습니다. 추가 문의는 언제든 연락 주세요.",
        ),
    ),
    SupportSeed(
        "C06",
        "세금계산서 발행 금액 불일치",
        "발행된 계산서 금액이 계약서 금액과 다릅니다. 확인 부탁드립니다.",
        "completed",
        False,
        -72,
        (
            "계산서와 계약서를 대조했습니다. 부가세 계산 오류가 확인됩니다.",
            "수정 세금계산서를 재발행했습니다. 종결합니다.",
        ),
    ),
    SupportSeed(
        "C07",
        "설치 위치 변경 요청",
        "리모델링으로 장비를 다른 층으로 옮겨야 합니다. 이설 지원이 가능한지요.",
        "completed",
        False,
        -68,
        ("이설 절차와 비용을 안내드렸습니다.", "방문 이설을 완료하고 재교정까지 마쳤습니다."),
    ),
    SupportSeed(
        "C08",
        "풋 스위치 반응 없음",
        "LC-FOOTSW 를 밟아도 반응이 없습니다. 수동 버튼은 정상입니다.",
        "completed",
        False,
        -64,
        ("단선으로 추정되어 교체품을 발송했습니다.", "교체 후 정상 동작 확인했습니다."),
    ),
    SupportSeed(
        "C09",
        "계약 갱신 조건 문의",
        "1년 무상 보증이 끝나갑니다. 유지보수 계약 조건을 알려주세요.",
        "completed",
        False,
        -60,
        (
            "연간 유지보수 계약 조건과 견적을 전달드렸습니다.",
            "고객사에서 갱신을 확정해 신규 딜로 등록했습니다.",
        ),
    ),
    SupportSeed(
        "C10",
        "프로브 커버 규격 불일치",
        "받은 LC-COVER-50 이 저희 프로브에 맞지 않습니다.",
        "completed",
        False,
        -56,
        (
            "보유 프로브 모델을 확인했습니다. 대형 규격이 필요합니다.",
            "LC-COVER-200 대형으로 교환 발송했습니다.",
        ),
    ),
    SupportSeed(
        "C11",
        "장비 소음 증가",
        "최근 가동 중 냉각팬 소음이 눈에 띄게 커졌습니다.",
        "completed",
        True,
        -52,
        (
            "소음 녹음을 받아 확인했습니다. 팬 베어링 마모로 판단됩니다.",
            "방문해 냉각팬을 교체했습니다.",
            "소음이 정상 범위로 돌아온 것을 확인했습니다.",
        ),
    ),
    SupportSeed(
        "C12",
        "젤 유통기한 임박 재고",
        "입고된 LC-GEL-1L 의 유통기한이 3개월밖에 남지 않았습니다.",
        "completed",
        False,
        -48,
        (
            "공급사 재고 회전 문제로 확인되었습니다.",
            "유통기한이 넉넉한 물량으로 전량 교환했습니다.",
        ),
    ),
    SupportSeed(
        "C13",
        "화면 터치 반응 지연",
        "조작 패널 터치가 한 박자 늦게 반응합니다.",
        "completed",
        False,
        -44,
        (
            "펌웨어 버전을 확인했습니다. 구버전에서 알려진 증상입니다.",
            "펌웨어를 최신으로 올려 증상이 해소되었습니다.",
        ),
    ),
    SupportSeed(
        "C14",
        "발주 취소 요청",
        "예산 집행이 미뤄져 진행 중인 발주를 취소하고 싶습니다.",
        "completed",
        False,
        -40,
        (
            "생산 착수 전이라 취소 가능함을 확인했습니다.",
            "발주를 취소 처리하고 확인서를 발송했습니다.",
        ),
    ),
    SupportSeed(
        "C15",
        "사용 중 경고 코드 E-12 발생",
        "시술 중 E-12 경고가 뜨고 동작이 멈춥니다.",
        "completed",
        True,
        -36,
        (
            "E-12 는 과열 보호 코드입니다. 설치 환경을 확인했습니다.",
            "장비 뒤 통풍 공간이 부족해 배치를 조정했습니다.",
            "재발하지 않는 것을 2주간 확인했습니다. 종결합니다.",
        ),
    ),
    SupportSeed(
        "C16",
        "단가 인상 사전 안내 요청",
        "내년 소모품 단가 계획을 미리 알려주시면 예산에 반영하겠습니다.",
        "completed",
        False,
        -32,
        ("확정 전이라 잠정 범위만 안내드렸습니다.", "확정 단가표를 자료실 자료로 전달드렸습니다."),
    ),
    SupportSeed(
        "C17",
        "교정 성적서 발급 요청",
        "인증 심사에 필요해 출력 교정 성적서가 필요합니다.",
        "completed",
        False,
        -28,
        ("최근 교정 이력을 확인했습니다.", "성적서를 발급해 메일로 송부했습니다."),
    ),
    SupportSeed(
        "C18",
        "렌즈 표면 흠집 발견",
        "LC-LENS-B 개봉 시 표면에 흠집이 있었습니다.",
        "completed",
        False,
        -24,
        (
            "사진을 받아 확인했습니다. 출고 전 손상으로 판단됩니다.",
            "무상 교환 발송했고 공급사에 품질 이슈를 전달했습니다.",
        ),
    ),
    SupportSeed(
        "C19",
        "설치 일정 재조정 요청",
        "병원 사정으로 예정된 설치일에 공간이 나지 않습니다.",
        "completed",
        False,
        -20,
        ("가능한 대체 일자를 협의했습니다.", "재조정된 일정으로 설치를 완료했습니다."),
    ),
    SupportSeed(
        "C20",
        "분할 납부 가능 여부 문의",
        "계약 금액을 2회로 나누어 납부할 수 있는지 알고 싶습니다.",
        "completed",
        False,
        -16,
        ("내부 승인 절차를 확인했습니다.", "2회 분할 납부 조건으로 계약서를 수정했습니다."),
    ),
    # ---- in_progress 15
    SupportSeed(
        "C21",
        "출력 편차가 시술마다 다름",
        "같은 설정인데 시술마다 체감 출력이 다르다는 의견이 반복됩니다.",
        "in_progress",
        True,
        -18,
        ("출력 로그 수집을 요청드렸습니다.", "로그상 편차가 확인되어 방문 점검 일정을 잡았습니다."),
    ),
    SupportSeed(
        "C22",
        "2차 발주분 입고 일정 확인",
        "분할 발주한 2차 물량의 입고 예정일을 알려주세요.",
        "in_progress",
        False,
        -15,
        ("공급사에 생산 일정을 확인 요청했습니다.",),
    ),
    SupportSeed(
        "C23",
        "소모품 단가 재협의 요청",
        "사용량이 늘어 소모품 단가를 조정하고 싶습니다.",
        "in_progress",
        False,
        -14,
        ("연간 사용량 자료를 요청드렸습니다.", "볼륨 할인 구간을 검토 중입니다."),
    ),
    SupportSeed(
        "C24",
        "프로브 케이블 피복 손상",
        "LP-D1 케이블 피복이 갈라졌습니다. 사용해도 되는지요.",
        "in_progress",
        True,
        -12,
        ("안전상 사용 중단을 안내드렸습니다.", "교체품을 발송했고 도착 후 회수 예정입니다."),
    ),
    SupportSeed(
        "C25",
        "추가 인력 대상 교육 일정 협의",
        "신규 인력 4명에 대한 교육이 필요합니다.",
        "in_progress",
        False,
        -11,
        ("가능한 일자 세 개를 제안드렸습니다.",),
    ),
    SupportSeed(
        "C26",
        "계약서 특약 문구 수정 요청",
        "보증 범위 문구를 저희 내부 규정에 맞게 조정하고 싶습니다.",
        "in_progress",
        False,
        -10,
        ("요청 문구를 법무 검토에 넘겼습니다.", "수정안을 회신드렸고 고객사 검토 중입니다."),
    ),
    SupportSeed(
        "C27",
        "필터 교체 주기 문의",
        "LC-FILTER-B 를 얼마나 자주 교체해야 하는지 기준이 궁금합니다.",
        "in_progress",
        False,
        -9,
        ("사용 시간 기준 권장 주기를 안내드렸습니다.",),
    ),
    SupportSeed(
        "C28",
        "이동형 카트 바퀴 파손",
        "LC-CART 바퀴 하나가 깨져 이동이 어렵습니다.",
        "in_progress",
        False,
        -8,
        (
            "부품 단위 교체가 가능한지 확인했습니다.",
            "바퀴 세트를 발송했습니다. 수령 확인 대기 중입니다.",
        ),
    ),
    SupportSeed(
        "C29",
        "정산 마감일 변경 요청",
        "병원 회계 일정 변경으로 정산일을 말일로 옮기고 싶습니다.",
        "in_progress",
        False,
        -7,
        ("내부 정산 담당과 협의 중입니다.",),
    ),
    SupportSeed(
        "C30",
        "데모 장비 대여 기간 연장",
        "원내 검토가 길어져 데모 장비를 2주 더 쓰고 싶습니다.",
        "in_progress",
        False,
        -6,
        ("대여 일정표를 확인했습니다. 연장 가능합니다.", "연장 확인서를 발송했습니다."),
    ),
    SupportSeed(
        "C31",
        "표면 조사용 프로브 각도 불편",
        "LP-S2 로 특정 부위 조사가 어렵다는 의견입니다.",
        "in_progress",
        False,
        -5,
        ("사용 부위를 확인하고 LP-FLEX 데모를 제안드렸습니다.",),
    ),
    SupportSeed(
        "C32",
        "장비 재고 확인 요청",
        "추가 1대 도입을 검토 중입니다. 즉시 출고 가능한 재고가 있는지요.",
        "in_progress",
        False,
        -4,
        ("공급사 재고를 조회 중입니다.",),
    ),
    SupportSeed(
        "C33",
        "세정 키트 사용법 문의",
        "LC-CLEAN-KIT 로 광학부를 닦는 순서를 알고 싶습니다.",
        "in_progress",
        False,
        -3,
        ("사용 순서를 정리해 회신드렸습니다.", "영상 자료를 추가로 요청하셔서 준비 중입니다."),
    ),
    SupportSeed(
        "C34",
        "납품 후 검수 서류 미비",
        "검수에 필요한 서류가 일부 빠져 있습니다.",
        "in_progress",
        False,
        -2,
        ("누락 서류 목록을 확인했습니다.",),
    ),
    SupportSeed(
        "C35",
        "듀얼 채널 동시 사용 시 출력 저하",
        "LR-DUO 로 두 채널을 함께 쓰면 각 채널 출력이 떨어집니다.",
        "in_progress",
        True,
        -1,
        (
            "사양상 동시 사용 시 채널당 출력이 분배됩니다.",
            "실사용 조건에 맞는 설정값을 정리해 전달 중입니다.",
        ),
    ),
    # ---- diagnosing 11
    SupportSeed(
        "C36",
        "간헐적 전원 차단",
        "하루 한두 번 장비가 갑자기 꺼집니다. 재현이 일정하지 않습니다.",
        "diagnosing",
        True,
        -13,
        ("발생 시각과 사용 조건 기록을 요청드렸습니다.",),
    ),
    SupportSeed(
        "C37",
        "특정 설정에서만 경고음",
        "고출력 모드에서만 경고음이 납니다.",
        "diagnosing",
        False,
        -10,
        ("해당 모드 로그를 수집 중입니다.",),
    ),
    SupportSeed(
        "C38",
        "젤 점도가 이전과 다름",
        "같은 제품인데 점도가 묽어진 느낌입니다.",
        "diagnosing",
        False,
        -9,
        ("제조번호를 받아 공급사에 확인 요청했습니다.",),
    ),
    SupportSeed(
        "C39",
        "교정 키트 측정값 편차",
        "LC-CALIB-KIT 로 잰 값이 회차마다 다릅니다.",
        "diagnosing",
        False,
        -8,
        ("측정 절차를 함께 점검하기로 했습니다.",),
    ),
    SupportSeed(
        "C40",
        "납기 지연 사유 설명 요청",
        "지연 통보만 받고 사유를 듣지 못했습니다.",
        "diagnosing",
        False,
        -7,
        ("공급사에 지연 사유 공식 회신을 요청했습니다.",),
    ),
    SupportSeed(
        "C41",
        "설치 후 벽면 진동",
        "가동 시 설치 벽면이 미세하게 울립니다.",
        "diagnosing",
        False,
        -6,
        ("설치 구조를 확인하기 위해 현장 사진을 요청했습니다.",),
    ),
    SupportSeed(
        "C42",
        "소모품 사용량이 예상보다 많음",
        "안내받은 것보다 팁 소모가 빠릅니다.",
        "diagnosing",
        False,
        -5,
        ("실제 시술 건수와 사용량을 비교 중입니다.",),
    ),
    SupportSeed(
        "C43",
        "연장 케이블 사용 시 출력 불안정",
        "LC-CABLE-4M 을 쓰면 출력이 흔들립니다.",
        "diagnosing",
        True,
        -4,
        ("2m 케이블과 비교 시험을 요청드렸습니다.",),
    ),
    SupportSeed(
        "C44",
        "계약 종료일 산정 문의",
        "계약 종료일이 저희 계산과 하루 다릅니다.",
        "diagnosing",
        False,
        -3,
        ("계약 기산일 기준을 확인 중입니다.",),
    ),
    SupportSeed(
        "C45",
        "거치 암 고정력 약화",
        "LC-ARM-EXT 가 각도를 유지하지 못하고 처집니다.",
        "diagnosing",
        False,
        -2,
        ("장착 하중과 조임 상태를 확인 중입니다.",),
    ),
    SupportSeed(
        "C46",
        "펌웨어 업데이트 후 설정 초기화",
        "업데이트하고 나니 저장해 둔 프리셋이 사라졌습니다.",
        "diagnosing",
        True,
        -1,
        ("백업 파일 존재 여부를 확인 중입니다.",),
    ),
    # ---- received 14
    SupportSeed(
        "C47",
        "장비 대여 문의",
        "행사에 쓸 장비를 며칠 빌릴 수 있는지 궁금합니다.",
        "received",
        False,
        -6,
        (),
    ),
    SupportSeed(
        "C48",
        "소모품 견적 요청",
        "내년치 소모품 일괄 견적을 받고 싶습니다.",
        "received",
        False,
        -5,
        (),
    ),
    SupportSeed(
        "C49",
        "프로브 추가 구매 문의",
        "LP-D2 를 두 개 더 사려고 합니다.",
        "received",
        False,
        -5,
        (),
    ),
    SupportSeed(
        "C50",
        "정기 점검 일정 문의",
        "올해 정기 점검이 언제인지 알려주세요.",
        "received",
        False,
        -4,
        (),
    ),
    SupportSeed(
        "C51",
        "사용 매뉴얼 재발송 요청",
        "매뉴얼을 분실했습니다. 파일로 받을 수 있을까요.",
        "received",
        False,
        -4,
        (),
    ),
    SupportSeed(
        "C52",
        "타 부서 확대 도입 검토",
        "재활치료실에도 도입을 검토 중입니다. 자료 부탁드립니다.",
        "received",
        False,
        -3,
        (),
    ),
    SupportSeed(
        "C53",
        "결제 조건 변경 문의",
        "카드 결제가 가능한지 알고 싶습니다.",
        "received",
        False,
        -3,
        (),
    ),
    SupportSeed(
        "C54",
        "설치 사전 준비 사항",
        "설치 전에 저희가 준비할 것이 있는지요.",
        "received",
        False,
        -2,
        (),
    ),
    SupportSeed(
        "C55", "보증 범위 확인", "소모품도 보증에 포함되는지 궁금합니다.", "received", False, -2, ()
    ),
    SupportSeed(
        "C56",
        "장비 폐기 절차 문의",
        "노후 장비 폐기를 어떻게 해야 하는지요.",
        "received",
        False,
        -1,
        (),
    ),
    SupportSeed(
        "C57",
        "야간 시술 시 소음 기준",
        "야간 병동 옆에서 쓸 수 있는 수준인지 알고 싶습니다.",
        "received",
        False,
        -1,
        (),
    ),
    SupportSeed(
        "C58",
        "출력 로그 내보내기 방법",
        "로그를 파일로 뽑는 방법을 알려주세요.",
        "received",
        False,
        0,
        (),
    ),
    SupportSeed(
        "C59",
        "긴급 - 시술 중 장비 정지",
        "오늘 오전 시술 중 장비가 멈췄습니다. 급합니다.",
        "received",
        True,
        0,
        (),
    ),
    SupportSeed(
        "C60",
        "긴급 - 프로브 과열",
        "프로브가 뜨거워져 사용을 중단했습니다.",
        "received",
        True,
        0,
        (),
    ),
)


# ---------------------------------------------------------------- 자료실


class DocumentSeed(NamedTuple):
    key: str
    category_code: str  # 프론트가 아는 코드만 쓴다 (useDocuments.ts 의 CATEGORY_CODE)
    title: str
    summary: tuple[str, ...]  # .docx 본문이자 description 의 재료
    source: str  # 발행 기관
    source_url: str  # 원문 주소. 스키마에 컬럼이 없어 tags 와 description 에 보존한다
    published: str  # 발행 시점 표기
    link_product: str | None  # product.name. sales_deal 과 동시 지정은 CHECK 위반
    link_deal: bool  # 진행 중인 딜 하나에 붙인다


# 첨부는 '출처 링크가 달린 우리 팀 요약 메모' 다. 원문을 복제한 파일이 아니다.
DISCLAIMER = "이 문서는 아래 공개자료를 요약한 내부 메모입니다. 원문은 링크를 참고하세요."

DOCUMENTS = (
    DocumentSeed(
        "F01",
        "other",
        "국내 의료기기 시장규모 현황 요약",
        (
            "한국보건산업진흥원이 집계하는 국내 의료기기 시장규모 통계의 갱신본이다.",
            "생산·수출·수입 실적을 연도별로 비교할 수 있어 담당 구역의 목표 설정 근거로 쓴다.",
            "영업 자료로 인용할 때는 집계 기준연도를 함께 밝혀야 한다.",
        ),
        "한국보건산업진흥원",
        "https://www.khidi.or.kr/menu?menuId=MENU03198",
        "상시 갱신",
        None,
        False,
    ),
    DocumentSeed(
        "F02",
        "other",
        "의료기기산업 실태조사 및 시장동향 분석 요약",
        (
            "제1차 의료기기산업 실태조사와 시장동향 분석을 담은 보건산업브리프다.",
            "업체 규모별 분포와 품목군별 성장률이 정리되어 "
            "있어 고객사 유형별 접근 논리를 세울 때 참고한다.",
            "요양병원·한방병원 비중 변화가 우리 구역 구성과 어떻게 다른지 확인할 것.",
        ),
        "한국보건산업진흥원",
        "https://www.khidi.or.kr/board/view?linkId=48913471&menuId=MENU01783",
        "보건산업브리프 Vol. 410",
        None,
        False,
    ),
    DocumentSeed(
        "F03",
        "other",
        "의료기기 생산현황 지표 요약",
        (
            "e-나라지표의 의료기기 생산현황 항목이다. "
            "국가 승인 통계라 대외 제안서에 인용해도 된다.",
            "생산액 추이와 무역수지를 한 화면에서 볼 수 있다.",
            "인용 시 지표 갱신일을 함께 적는다.",
        ),
        "국가지표체계(e-나라지표)",
        "https://www.index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd=2863",
        "상시 갱신",
        None,
        False,
    ),
    DocumentSeed(
        "F04",
        "other",
        "의료기기 허가 동향 요약",
        (
            "식약처의 연간 의약품·의약외품·의료기기 허가 동향 발표를 정리한 것이다.",
            "AI 기반 의료기기 허가가 빠르게 늘고 있어 경쟁 제품 진입 속도를 가늠하는 데 쓴다.",
            "허가 건수는 시장 규모가 아니라 진입 예정 물량임에 유의한다.",
        ),
        "생명공학정책연구센터",
        "https://www.bioin.or.kr/board.do?num=333704&cmd=view&bid=division",
        "연간 발표",
        None,
        False,
    ),
    DocumentSeed(
        "F05",
        "other",
        "의료기기 유통 및 판매질서 유지에 관한 규칙 요약",
        (
            "의료기기 판매 과정에서 금지되는 경제적 이익 제공의 범위를 정한 규칙이다.",
            "고객사 방문 시 제공 가능한 것과 불가능한 것의 기준이 여기에 있다.",
            "판단이 애매한 사안은 임의로 해석하지 말고 팀장에게 확인한다.",
        ),
        "국가법령정보센터",
        "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=138120",
        "법령 원문",
        None,
        False,
    ),
    DocumentSeed(
        "F06",
        "other",
        "의료기기법 시행규칙 발췌 요약",
        (
            "판매업 신고, 품질책임자, 보관 조건 등 영업 활동과 직접 닿는 조항을 발췌했다.",
            "고객사가 판매업 신고 절차를 물을 때 근거로 쓴다.",
            "조문 번호는 개정으로 바뀔 수 있으니 인용 전 원문을 확인한다.",
        ),
        "국가법령정보센터",
        "https://law.go.kr/LSW/lsInfoP.do?lsiSeq=107498",
        "법령 원문",
        None,
        False,
    ),
    DocumentSeed(
        "F07",
        "product_brochure",
        "LR-PRO2 제품 개요와 허가 절차 안내",
        (
            "LR-PRO2 의 주요 사양과 기존 LR-PRO 대비 개선점을 정리했다.",
            "고객사가 도입 전 확인하는 허가·신고 절차는 "
            "식약처 의료기기전자민원시스템의 안내를 따른다.",
            "데모 요청 시 이 자료를 먼저 보내고 방문 일정을 잡는다.",
        ),
        "식약처 의료기기전자민원시스템",
        "https://emedi.mfds.go.kr/msismext/emd/bif/prmProcssView.do",
        "상시 갱신",
        "LR-PRO2",
        False,
    ),
    DocumentSeed(
        "F08",
        "product_brochure",
        "치료재료 급여 등재 절차와 소모품 취급 안내",
        (
            "소모품이 건강보험 급여 대상인지 묻는 문의가 반복되어 등재 절차를 정리했다.",
            "심평원의 신의료기술 등재 신청 가이드를 근거로 한다.",
            "우리 소모품은 대부분 별도 산정 대상이 아니므로 단정적으로 답하지 않는다.",
        ),
        "건강보험심사평가원",
        "https://www.hira.or.kr/ebooksc/2024/01/BZ202401189533243.pdf",
        "2024-01",
        "LC-GEL-500",
        False,
    ),
    DocumentSeed(
        "F09",
        "product_brochure",
        "치료재료 코드 조회 방법 안내",
        (
            "고객사 구매팀이 코드로 품목을 확인하려 할 때 쓰는 조회 경로를 정리했다.",
            "심평원 대국민 홈페이지의 치료재료 코드 조회 화면을 이용한다.",
            "코드가 없는 품목은 비급여이거나 별도 산정 불가임을 함께 설명한다.",
        ),
        "건강보험심사평가원",
        "https://www.hira.or.kr/bbsDummy.do?brdBltNo=46998&brdScnBltNo=4&pgmid=HIRAA010006011000",
        "상시 갱신",
        "LC-FILTER-B",
        False,
    ),
    DocumentSeed(
        "F10",
        "contract",
        "표준 계약서 작성 기준 메모",
        (
            "계약서에 반드시 들어가야 하는 항목과 특약 작성 시 유의점을 정리했다.",
            "보증 범위와 유지보수 조건은 고객사마다 문구가 달라지므로 임의로 바꾸지 않는다.",
            "법령상 제약은 의료기기 유통 및 판매질서 규칙을 따른다.",
        ),
        "국가법령정보센터",
        "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=138120",
        "법령 원문",
        None,
        True,
    ),
    DocumentSeed(
        "F11",
        "quote",
        "견적서 작성 기준 메모",
        (
            "견적 유효기간 30일 원칙과 할인 승인 절차를 정리했다.",
            "볼륨 할인 구간과 팀장 승인이 필요한 할인율 기준을 담았다.",
            "유효기간이 지난 견적으로 계약을 진행하지 않는다.",
        ),
        "내부 기준",
        "https://www.khidi.or.kr/menu?menuId=MENU01530",
        "내부 문서",
        None,
        True,
    ),
    DocumentSeed(
        "F12",
        "purchase_order",
        "발주서 작성과 공급사 연락 기준",
        (
            "발주 마감 시각과 공급사별 리드타임을 정리했다.",
            "분할 발주 시 계약 금액을 넘지 않도록 누적 금액을 확인한다.",
            "입고 지연이 확인되면 고객사에 먼저 알린다.",
        ),
        "내부 기준",
        "https://www.khidi.or.kr/menu?menuId=MENU01530",
        "내부 문서",
        None,
        True,
    ),
)

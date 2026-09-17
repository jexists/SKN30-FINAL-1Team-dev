"""메디온 의료기기 영업팀 데모 데이터의 상수.

시더(scripts/seed_demo_medion.py)가 쓰는 값만 둔다. 날짜는 여기 없다. 전부 기준일의
상대 오프셋으로 시더가 계산한다.

사람 이름·연락처·이메일은 모두 가상이다. docs/data-sanitization-rules.md 에 따라
전화번호는 통화가 되지 않는 010-0000-NNNN 형식, 이메일은 예약 도메인(.test)을 쓴다.
병원 이름과 주소만 공공데이터 원본을 보존한다.
"""

from typing import NamedTuple
from uuid import UUID, uuid5

# 팀 범위를 한 곳에서 정한다. reset 이 지우는 범위도, 검증이 세는 범위도 이 팀이다.
#
# 팀과 계정은 사람이 이미 만들어 두었다. 시더는 이 둘을 만들지도 고치지도 않는다 —
# 확인만 하고, 그 안에 업무 데이터를 채운다. 팀 이름도 손대지 않는다.
TEAM_ID = UUID("85f2c57d-00c0-4790-9c71-4b23cd2100a6")
TEAM_NAME = "playdata"
SEED_TAG = "medion2026"


def sid(kind: str, key: str) -> UUID:
    """행 id. 팀 안에서 (종류, 자연키) 하나에 한 행씩 대응한다.

    기준일을 키에 넣지 않는다. 넣으면 날짜를 옮길 때마다 새 행이 쌓인다.
    """
    return uuid5(TEAM_ID, f"{SEED_TAG}:{kind}:{key}")


class MemberSeed(NamedTuple):
    key: str
    email: str
    display_name: str
    role_code: str


# 이 두 계정에 데모 데이터가 붙는다. 둘 다 이미 팀 playdata 에 있고, 시더는 id 만 조회한다.
# 계정을 만들지 않으므로 비밀번호를 받지도, 어디에 적지도 않는다.
# 표시 이름은 확인용이다. DB 와 다르면 엉뚱한 팀을 건드린 것이므로 중단한다.
LEADER = "leader"
MEMBER = "member"
MEMBERS = (
    MemberSeed(LEADER, "leader@playdata.com", "천성배", "manager"),
    MemberSeed(MEMBER, "test@playdata.com", "김진남", "member"),
)
MEMBER_BY_KEY = {m.key: m for m in MEMBERS}
EMAILS = tuple(m.email for m in MEMBERS)

# data/sample/Sales_DB.xlsx 품목리스트 시트를 옮긴 값이다. 제품군을 스키마의
# category_code(system·probe·consumable) 로 바꾼 것 말고는 모델명·판매단가가 원본 그대로다.
PRODUCTS = (
    ("LR1000", "system", 4_500_000, None, "보급형 의료용 레이저 시스템"),
    ("LR2000", "system", 5_200_000, None, "주력 의료용 레이저 시스템"),
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
UNIT_PRICE = {name: price for name, _, price, _, _ in PRODUCTS}

# 장비 본체만 딜의 대표 제품으로 쓴다. 프로브·소모품은 딜 품목에 곁들인다.
SYSTEM_MODELS = ("LR1000", "LR2000", "LR-PRO")
ACCESSORY_MODELS = ("LP1000", "LP1500", "LP2000", "LR-CORE1", "LR-CORE2", "LP100", "LP200")

# 담당자 이름 풀. 성과 이름을 조합해 만든다. 실제 인물과 무관한 가상 값이다.
SURNAMES = (
    "김", "이", "박", "최", "정", "강", "조", "윤",
    "장", "임", "한", "오", "서", "신", "권",
)
GIVEN_NAMES = (
    "도윤", "서연", "지훈", "하윤", "준서", "수아", "예준", "지우", "시우", "채원",
    "건우", "다은", "우진", "유진", "현우", "소율", "재민", "가은", "태윤", "윤서",
)
DEPARTMENTS = (
    "구매팀", "의공학팀", "영상의학과", "정형외과", "피부과", "재활의학과",
    "원무팀", "진료협력팀", "마취통증의학과", "성형외과",
)
JOB_TITLES = ("과장", "팀장", "원장", "부장", "실장", "주임", "대리", "차장")

# 화면이 아는 유입경로 코드만 쓴다 (backend/app/schemas/customers.py CustomerSource).
SOURCE_CODES = ("referral", "event", "online_form", "joint_past", "media", "other")

# 고객 상태 코드. seed_demo_auth 의 customer_contact_status 와 같다.
CONTACT_STATUS_CODES = ("new", "proposal", "negotiation", "contracted", "on_hold")

# 고객현황 메모. 상태 코드에 맞는 문장만 골라 쓴다. {name}/{job}/{dept} 를 채워 넣는다.
# 영업이 실제로 적는 정보(결정권자·예산·경쟁사·연락 방식·다음 액션)만 담는다.
CONTACT_MEMOS: dict[str, tuple[str, ...]] = {
    "new": (
        "{dept} 소개로 첫 통화. 사용 8년차 장비 교체를 검토 중이고 예산 시점은 미정. "
        "{name} {job}이 실무 창구, 최종 결정은 원장 결재.",
        "학회 부스에서 명함 교환 후 첫 방문. 장비 사양 자료만 전달한 상태. "
        "구매 시점은 내년 상반기로 듣고 있어 분기마다 접촉 예정.",
        "{dept} 증축 계획이 있어 장비 수요 예상. 예산 규모 미확인. "
        "오전 진료 전 통화가 가장 잘 닿음.",
        "홈페이지 문의로 유입. 현재 타사 장비 사용 중이며 유지보수 비용에 불만. "
        "{name} {job}에게 비교 자료 요청받음.",
    ),
    "proposal": (
        "제안서 전달 완료. 경쟁사 두 곳과 병행 검토 중이며 출력 사양 비교를 중요하게 봄. "
        "{dept} 사용 의견이 결정에 크게 반영된다.",
        "데모 일정 조율 중. {name} {job}은 사용 편의성, 원장은 투자 회수 기간을 먼저 본다. "
        "두 관점의 자료를 나눠 준비할 것.",
        "제안 범위는 본체 1대와 소모품 연간 계약. 추가 프로브는 다음 해 예산으로 미뤄 두자는 의견. "
        "결재선은 {dept} → 구매팀 → 원장.",
        "타 지점 도입 사례를 요청받아 전달함. 레퍼런스 병원 방문 의사 있음. "
        "연락은 메일 회신이 가장 빠르다.",
    ),
    "negotiation": (
        "단가와 납기가 쟁점. 동시 도입 조건의 할인율을 확인 중이고, 설치는 휴진일을 원한다. "
        "{name} {job}이 내부 결재를 올린 상태.",
        "견적 회신 대기 중. 구매팀 내부 검토가 2주째 이어져 {dept}를 통해 상황을 확인하고 있다. "
        "경쟁사 저가 제안이 함께 올라가 있다.",
        "계약 조건 중 보증 기간 연장과 소모품 단가를 조정 요청받음. "
        "결정권은 원장에게 있고 {name} {job}은 실무 의견을 붙이는 역할.",
        "예산 집행 시점을 분기 말로 맞추고 싶어 한다. 사양은 합의됐고 금액만 남았다. "
        "방문 협의를 선호하며 전화 응대는 짧다.",
    ),
    "contracted": (
        "계약 체결 완료. 설치 일정은 휴진일 기준으로 협의했고 사용자 교육은 {dept} 전원 대상. "
        "추가 도입 여지는 내년 예산 논의 때 다시 확인.",
        "납품·설치 완료. 사용 부서 반응은 좋은 편이고 소모품 재주문 주기는 분기 단위. "
        "{name} {job}이 유지보수 창구.",
        "계약 후 발주 진행 중. 입고 일정 공유가 중요해 주 1회 진행 상황을 전달하고 있다. "
        "다음 갱신 시점에 상위 모델 제안 예정.",
        "1호기 운영 중이며 만족도가 높다. 분원 개설 시 추가 도입 의사를 밝혔다. "
        "레퍼런스 병원으로 소개해도 좋다고 구두 동의함.",
    ),
    "on_hold": (
        "올해 예산 배정이 무산되어 보류. 내년 초 재검토 요청받음. "
        "{name} {job}과의 관계는 유지하고 분기마다 짧게 접촉할 것.",
        "{dept} 인력 이동으로 검토가 중단됨. 후임 확인 후 다시 접촉 예정.",
        "경쟁사 장비를 먼저 도입해 당분간 수요 없음. 계약 만료 시점에 맞춰 갱신 제안 준비.",
        "원장 장기 부재로 결재가 멈춘 상태. 복귀 시점 미확인이라 무리한 팔로업은 피한다.",
    ),
}

# 발주 공급처. 3개회사_매출데이터 샘플의 회사명을 옮긴 가상 상호다.
SUPPLIERS = ("레이저메디텍", "루미나레이저", "프로레이저솔루션")

WARRANTY = "설치일로부터 12개월 무상 보증, 소모품 및 사용자 과실 제외"
PAYMENT_TERMS = "납품 검수 완료 후 30일 이내 현금 지급"
DELIVERY_TERMS = "계약일로부터 3주 이내 설치 및 사용자 교육 포함"


class NoticeSeed(NamedTuple):
    key: str
    type: str
    tag: str
    title: str
    body: str
    starts_offset: int  # 기준일 기준 게시 시작 오프셋(일). 음수가 과거다.
    due_offset: int | None  # 지시사항 기한 오프셋(일). 공지는 None.
    target_status: str | None  # 지시를 받은 팀원의 이행 상태. 공지는 None.
    target_reason: str | None  # not_done 일 때만 채운다. DB CHECK 가 사유를 요구한다.


# 공지 3 + 팀장 지시사항 3.
# DIRECTIVE 는 notice_target 이 없으면 팀장에게도 팀원에게도 보이지 않는다.
# 세 지시의 이행 상태를 done·pending·not_done 으로 나눠 이행 현황 칸을 시연한다.
NOTICES = (
    NoticeSeed(
        "N01",
        "NOTICE",
        "실적",
        "이번 달 실적 마감 및 매출 인식 기준 안내",
        "<p>이번 달 실적 마감은 말일 18시입니다. 매출은 <strong>계약 체결일</strong> 기준으로"
        " 집계하므로, 계약서에 고객 서명이 완료된 건만 이번 달 실적에 반영됩니다.</p>"
        "<p>견적만 발송된 건은 다음 달로 넘어갑니다. 마감 전에 계약 관리 화면에서 계약일과"
        " 계약금액이 비어 있지 않은지 확인해 주세요.</p>",
        -10,
        None,
        None,
        None,
    ),
    NoticeSeed(
        "N02",
        "NOTICE",
        "교육",
        "LR-PRO 제품 교육 및 의료기기법 준법 교육 일정",
        "<p>신규 상위 모델 <strong>LR-PRO</strong> 제품 교육을 본사 교육장에서 진행합니다."
        " 출력 사양과 프로브 호환 범위가 기존 LR2000 과 달라 데모 전에 필수로 이수해야"
        " 합니다.</p>"
        "<p>이어서 의료기기법 준법 교육이 있습니다. 미허가 광고 문구 사용과 의료인 대상"
        " 경제적 이익 제공 금지가 핵심이니 전원 참석해 주세요.</p>",
        -5,
        None,
        None,
        None,
    ),
    NoticeSeed(
        "N03",
        "NOTICE",
        "인허가",
        "식약처 허가 갱신 대상 품목 안내",
        "<p>프로브 계열 <strong>LP1000 · LP1500</strong> 의 제조허가 갱신이 진행 중입니다."
        " 갱신 완료 전까지 해당 품목은 신규 견적에 포함하지 말아 주세요.</p>"
        "<p>이미 계약이 체결된 건의 납품에는 영향이 없습니다. 고객이 문의하면 공급에 차질이"
        " 없다는 점을 먼저 안내해 주세요.</p>",
        -2,
        None,
        None,
        None,
    ),
    NoticeSeed(
        "D01",
        "DIRECTIVE",
        "데모",
        "핵심 병원 장비 데모 준비 상태 점검",
        "<p>이번 분기 핵심 타깃 병원의 장비 데모 일정을 다시 확인해 주세요. 데모 장비 예약,"
        " 프로브 구성, 진료과 참석자까지 확정되어야 합니다.</p>"
        "<p>데모 당일 원장님이 참석하지 못하면 구매 결정이 한 달씩 밀립니다. 참석자 확정을"
        " 먼저 받아 주세요.</p>",
        -12,
        -7,
        "done",
        None,
    ),
    NoticeSeed(
        "D02",
        "DIRECTIVE",
        "견적",
        "견적 발송 후 팔로업 진행",
        "<p>견적을 보내고 일주일이 지난 건을 전부 팔로업해 주세요. 견적 유효기간이 지나면"
        " 가격을 다시 잡아야 해서 협상이 처음으로 돌아갑니다.</p>"
        "<p>통화가 안 되면 구매팀 외에 사용 부서에도 연락해 진행 상황을 확인해 주세요.</p>",
        -4,
        3,
        "pending",
        None,
    ),
    NoticeSeed(
        "D03",
        "DIRECTIVE",
        "계약",
        "계약 갱신 대상 사전 점검",
        "<p>계약 종료가 한 달 안쪽으로 들어온 건을 먼저 점검해 주세요. 유지보수 조건과"
        " 소모품 공급 단가를 갱신 전에 정리해야 합니다.</p>"
        "<p>경쟁사가 갱신 시점에 맞춰 들어오는 경우가 많습니다. 종료 2주 전에는 고객과"
        " 마주 앉아 있어야 합니다.</p>",
        -9,
        -2,
        "not_done",
        "대상 병원 구매팀 담당자가 휴가 중이라 다음 주로 미뤘습니다.",
    ),
)


class SupportSeed(NamedTuple):
    key: str
    title: str
    body: str
    status_code: str
    is_urgent: bool
    occurred_offset: int  # 기준일 기준 발생일 오프셋(일). 전부 과거다.
    owner: str
    responses: tuple[str, ...]


# C/S 8건. 상태 네 가지를 두 건씩 나눠 목록 탭과 대시보드 카드를 모두 채운다.
# 딜은 시더가 계약·발주 단계 딜 중에서 붙인다. 고객사는 그 딜의 고객사와 같아야 한다.
SUPPORTS = (
    SupportSeed(
        "S01",
        "설치 후 출력 편차 문의",
        "설치 교육 이후 출력이 설정값보다 낮게 나온다는 연락을 받았습니다. 프로브 연결부"
        " 접촉 불량이 의심되어 현장 점검을 요청합니다.",
        "received",
        True,
        -3,
        MEMBER,
        (),
    ),
    SupportSeed(
        "S02",
        "소모품 교체 주기 문의",
        "소모성 액세서리 교체 주기를 문서로 달라는 요청입니다. 사용 빈도가 높은 곳이라"
        " 권장 주기보다 빨리 교체해야 할 수 있습니다.",
        "received",
        False,
        -2,
        LEADER,
        (),
    ),
    SupportSeed(
        "S03",
        "전원 인가 시 간헐적 재부팅",
        "하루 두세 차례 재부팅된다는 신고입니다. 전원부 또는 접지 문제로 보여 현장 전압을"
        " 먼저 확인하기로 했습니다.",
        "diagnosing",
        True,
        -8,
        MEMBER,
        ("현장 전압을 측정했습니다. 접지가 분리되어 있어 병원 시설팀과 보완 일정을 잡았습니다.",),
    ),
    SupportSeed(
        "S04",
        "사용자 계정 초기화 요청",
        "장비 관리자 계정 비밀번호를 분실했습니다. 본인 확인 후 초기화 절차를 안내하고"
        " 있습니다.",
        "diagnosing",
        False,
        -6,
        LEADER,
        ("병원 의공학팀장 명의 공문을 받아 초기화 절차를 진행 중입니다.",),
    ),
    SupportSeed(
        "S05",
        "프로브 케이블 파손 교체",
        "프로브 케이블 피복이 벗겨져 교체가 필요합니다. 대체 프로브를 먼저 보내고 수리품을"
        " 회수하기로 했습니다.",
        "in_progress",
        True,
        -12,
        MEMBER,
        (
            "대체 프로브를 발송했습니다. 회수품은 다음 방문 때 가져오겠습니다.",
            "대체 프로브 정상 동작을 확인했습니다. 수리 완료까지 그대로 사용하기로 했습니다.",
        ),
    ),
    SupportSeed(
        "S06",
        "납품 일정 변경 요청",
        "병원 리모델링 일정이 밀려 납품일을 2주 미뤄 달라는 요청입니다. 생산팀과 입고 일정을"
        " 조정하고 있습니다.",
        "in_progress",
        False,
        -15,
        LEADER,
        ("생산팀과 입고 일정을 다시 잡았습니다. 변경된 일정으로 발주서를 갱신했습니다.",),
    ),
    SupportSeed(
        "S07",
        "사용자 교육 추가 요청",
        "교대 근무자가 교육을 받지 못해 추가 회차를 요청했습니다. 야간 근무조 일정에 맞춰"
        " 진행했습니다.",
        "completed",
        False,
        -25,
        MEMBER,
        (
            "야간 근무조 대상 추가 교육을 진행했습니다.",
            "교육 이수 명단을 병원 의공학팀에 전달하고 종료했습니다.",
        ),
    ),
    SupportSeed(
        "S08",
        "보증 범위 확인 요청",
        "사용 중 발생한 외관 손상이 보증 범위인지 문의했습니다. 사용자 과실이라 유상 수리로"
        " 안내했습니다.",
        "completed",
        False,
        -32,
        LEADER,
        (
            "계약서 보증 조항을 근거로 유상 수리 대상임을 안내했습니다.",
            "고객이 유상 수리에 동의해 수리를 마치고 종료했습니다.",
        ),
    ),
)


class StageSeed(NamedTuple):
    """서사 구간 딜 하나. 파이프라인 9단계를 골고루 채운다."""

    key: str
    stage_code: str
    owner: str
    model: str
    quantity: int
    opened_offset: int  # 기준일 기준 개설일 오프셋(일). 음수가 과거다.
    title: str
    memo: str


# 서사 구간(기준일 −150 ~ 기준일) 딜. 활동·보고서·발주·C/S 가 여기에 붙는다.
# 9단계가 모두 나오고, 성공·진행중·장기 팔로업·경쟁사 실패가 모두 들어간다.
NARRATIVE_DEALS = (
    StageSeed("V01", "needs_validation", MEMBER, "LR1000", 1, -18,
              "노후 장비 교체 검토", "사용 8년차 장비 교체를 검토 중. 예산 시점 미정."),
    StageSeed("V02", "needs_validation", LEADER, "LR2000", 1, -11,
              "신규 진료과 개설 대응", "진료과 신설에 맞춘 장비 도입 문의."),
    StageSeed("V03", "needs_validation", MEMBER, "LR1000", 1, -140,
              "장기 팔로업 건", "작년부터 검토만 이어지는 건. 예산 배정이 계속 밀린다."),
    StageSeed("D04", "product_demo", MEMBER, "LR2000", 1, -40,
              "장비 데모 평가", "데모 후 사용 부서 평가 진행 중."),
    StageSeed("D05", "product_demo", LEADER, "LR-PRO", 1, -33,
              "상급종합 데모 평가", "원장 참관 데모 완료. 출력 사양 비교 자료 요청."),
    StageSeed("Q06", "quote_sent", MEMBER, "LR2000", 1, -52,
              "견적 검토 대기", "견적 발송 후 구매팀 내부 검토 중."),
    StageSeed("Q07", "quote_sent", LEADER, "LR1000", 2, -47,
              "2대 동시 도입 견적", "2대 동시 도입 조건으로 단가 협의 중."),
    StageSeed("C08", "contract_sent", MEMBER, "LR-PRO", 1, -66,
              "계약서 검토 요청", "계약서 발송. 법무 검토 대기."),
    StageSeed("C09", "contract_review", LEADER, "LR2000", 1, -74,
              "계약 조건 협의", "고객 서명 완료. 내부 계약 검토 중."),
    StageSeed("C10", "contract_completed", MEMBER, "LR2000", 1, -88,
              "계약 완료 건", "계약 체결. 발주 준비 중."),
    StageSeed("C11", "contract_completed", LEADER, "LR-PRO", 1, -95,
              "상급종합 계약 완료", "계약 체결. 설치 일정 협의 예정."),
    StageSeed("O12", "order_in_progress", MEMBER, "LR1000", 1, -110,
              "발주 진행 건", "발주 접수. 생산 대기."),
    StageSeed("O13", "order_in_progress", LEADER, "LR2000", 2, -118,
              "2대 발주 진행", "2대 발주. 입고 일정 조율 중."),
    StageSeed("O14", "order_delivered", MEMBER, "LR2000", 1, -132,
              "납품 완료 건", "설치 및 사용자 교육 완료."),
    StageSeed("O15", "order_delivered", LEADER, "LR-PRO", 1, -145,
              "상급종합 납품 완료", "설치 완료. 추가 프로브 논의 중."),
    StageSeed("X16", "closed_cancelled", MEMBER, "LR2000", 1, -80,
              "경쟁사 전환 건", "경쟁사 저가 제안으로 종료. 가격이 결정적이었다."),
    StageSeed("X17", "closed_cancelled", LEADER, "LR1000", 1, -60,
              "예산 미배정 종료", "올해 예산 배정 무산으로 종료. 내년 재검토 요청."),
)

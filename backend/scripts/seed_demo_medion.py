"""메디온 의료기기 영업팀 데모 데이터 시더.

로그인한 팀장과 팀원이 대시보드·공지·일정·보고서·고객·딜·견적·계약·발주·C/S·매출분석을
모두 돌아볼 수 있도록, 데모 팀 하나에 서로 이어진 데이터를 넣는다.

같은 명령을 몇 번 실행해도 결과가 같다. 기본 동작은 reset → seed → verify 다.
reset 은 이 데모 팀이 소유한 행만 지운다. 다른 팀·다른 계정 데이터는 건드리지 않는다.

팀과 두 계정은 사람이 미리 만들어 둔 것을 쓴다. 시더는 계정을 만들지도 고치지도 않고,
팀 이름도 손대지 않는다. 그래서 비밀번호를 받을 일도 없다.

    cd backend
    uv run python -m scripts.seed_demo_medion --dry-run
    uv run python -m scripts.seed_demo_medion
    uv run python -m scripts.seed_demo_medion --reset --yes
    uv run python -m scripts.seed_demo_medion --verify

기준일은 --base-date 로 옮길 수 있고 기본값은 실행일이다. 스크립트에 절대 날짜가 없다.
"""

import argparse
import asyncio
import hashlib
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.agent import AgentRun, ContractNextMeetingSuggestion
from app.models.configuration import (
    ActivityActionTag,
    ActivityCategory,
    ContractStatus,
    CustomerContactStatus,
    PurchaseOrderStatus,
    QuoteStatus,
    SalesDealType,
)
from app.models.content import (
    Document,
    File,
    Report,
    ReportActivity,
    ReportAttachment,
    ReportDeal,
    ReportSubmission,
)
from app.models.crm import (
    Activity,
    CustomerCompany,
    CustomerContact,
    CustomerContactAssignee,
    SupportRequest,
    SupportRequestEditBackup,
    SupportResponse,
)
from app.models.sales import (
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesDeal,
    SalesDealItem,
    SalesPipeline,
    SalesPipelineStage,
    SalesTarget,
)
from app.models.workspace import Member, Notice, NoticeImage, NoticeTarget, Team
from scripts.demo import hospitals, medion
from scripts.demo.medion import LEADER, MEMBER, TEAM_ID, TEAM_NAME, sid
from scripts.seed_demo_auth import seed_team_configuration

SEOUL = ZoneInfo("Asia/Seoul")

# 고객사 표본 크기. 목록 검색·필터·페이지네이션(30건/쪽)을 시연할 만큼만 넣는다.
COMPANY_COUNT = 400
# 담당자를 붙일 앞쪽 고객사 수. 나머지는 미개척 고객사로 남는다.
CONTACT_COMPANY_COUNT = 100


# ---------------------------------------------------------------- 영업 흐름

# 딜 하나가 지나가는 활동 순서. offset 은 개설일로부터의 일수다.
# 견적일(step 5)과 계약일(step 7)을 이 표에서 끌어내므로 딜의 날짜와 활동이 어긋나지 않는다.
FLOW = (
    ("첫 방문 상담", "visit", "first_call", 0),
    ("니즈 확인 미팅", "visit", "meeting", 7),
    ("병원 장비 데모", "demo", "demo_in_progress", 18),
    ("데모 결과 논의", "visit", "demo_completed", 25),
    ("구매부서 견적 협의", "visit", "meeting", 33),
    ("견적서 전달", "visit", "quote_completed", 40),
    ("원장·진료과 미팅", "visit", "meeting", 50),
    ("계약 조건 협의 및 체결", "visit", "contract_completed", 60),
    ("설치 및 사용자 교육", "education", "product_training", 75),
    ("납품 일정 조율 및 확인", "delivery", "delivery_completed", 85),
)
QUOTE_STEP = 5
CONTRACT_STEP = 7

# 단계별로 어디까지 진행됐는지. 리스트 길이가 곧 만들어지는 활동 수다.
STAGE_STEPS = {
    "needs_validation": 2,
    "product_demo": 4,
    "quote_sent": 6,
    "contract_sent": 7,
    "contract_review": 7,
    "contract_completed": 8,
    "order_in_progress": 9,
    "order_delivered": 10,
    "closed_cancelled": 6,
}
# 평일 채움. 서사 흐름만 따르면 미팅이 하나도 없는 평일이 대부분이라 화면이 빈다.
# 이번 달 구간(기준일 −14 ~ +3)은 평일마다 1인당 세 건, 그 이전 일곱 달은 평일 열에
# 여덟만 한 건을 채운다. 과거 건에는 미팅 보고서가 그대로 따라붙는다.
DENSE_FROM, DENSE_TO = -14, 3
DENSE_MIN = 3
SPARSE_MONTHS = 7
SPARSE_MIN = 1
SPARSE_RATIO = 8  # pick(..., 10) 이 이 값보다 작은 날만 채운다.
FILL_HOURS = (9, 11, 13, 15, 17)

# 월간 보고서가 덮는 개월 수. 일일·주간도 같은 구간에서 만든다.
PERIOD_MONTHS = 3

# 고객이 서명한 단계. contract_sent 는 계약서를 보내기만 해 서명일이 없다.
SIGNED_STAGES = ("contract_review", "contract_completed", "order_in_progress", "order_delivered")
ORDER_STAGES = ("order_in_progress", "order_delivered")

# 화면 탭이 되는 견적·계약 상태를 단계에 맞춰 고른다.
QUOTE_STATUS_BY_STAGE = {
    "quote_sent": "sent",
    "contract_sent": "completed",
    "contract_review": "completed",
    "contract_completed": "completed",
    "order_in_progress": "completed",
    "order_delivered": "completed",
    "closed_cancelled": "negotiating",
}
CONTRACT_STATUS_BY_STAGE = {
    "contract_sent": "reviewing",
    "contract_review": "signed",
    "contract_completed": "completed",
    "order_in_progress": "completed",
    "order_delivered": "completed",
}

# ---------------------------------------------------------------- 보고서 서식

# 화면은 본문을 구획으로 읽는다. frontend/src/shared/reportSections.ts 의
# HEADING = /^\*\*(.+?)\*\*$/ 가 굵은 소제목 한 줄을 찾고, 하나도 없으면 null 을 돌려
# 원문 그대로 그린다. 그래서 소제목이 없으면 LLM 이 쓴 보고서처럼 보이지 않는다.
#
# 유형별 고정 항목은 backend/app/agents/reports/skills/*/SKILL.md 의 '작성 순서' 다.
# 마지막 항목만 목록이고 나머지는 서술 문단이다.
MEETING_ORDER = ("미팅 목적", "논의 내용", "고객 요구", "합의사항", "후속 조치")
DAILY_ORDER = ("오늘 한 일", "거래처별 결과", "미완료·문제", "다음 업무")
WEEKLY_ORDER = ("목표", "실적", "차이", "원인", "다음 주 조치")
MONTHLY_ORDER = ("성과", "원인", "문제", "개선안", "다음 달 계획")

# 근거가 없는 항목의 표기. report-style/SKILL.md 가 정한 문구 그대로다.
# ReportView 의 BLANK 정규식이 이 말로 시작하는 값을 회색으로 뺀다.
BLANK_SECTION = "해당사항 없음 (제공된 자료에 관련 내용 없음)"


def josa(word: str, with_batchim: str, without: str) -> str:
    """받침 유무로 조사를 고른다. '대리' + 이/가 → '대리가', '과장' → '과장이'.

    템플릿에 조사를 박아 두면 '대리이' 같은 비문이 나온다. 한글 음절은
    (코드 - 0xAC00) % 28 이 0 이 아니면 받침이 있다.
    """
    if not word:
        return without
    code = ord(word[-1]) - 0xAC00
    return with_batchim if 0 <= code <= 11171 and code % 28 else without


def action(task: str, *fields: tuple[str, str]) -> str:
    """후속 조치 한 줄.

    이름표는 reportSections.ts 의 FIELD_LABELS 에 있는 것만 파싱된다
    (담당자·담당·기한·완료 기준·상태·이행 여부·조건·선행조건·요청 대상).
    구분자는 앞뒤 공백이 있는 ' · ' 여야 값 안의 가운뎃점이 잘리지 않는다.
    """
    parts = [f"**{task}**", *(f"{label}: {value}" for label, value in fields)]
    return "- " + " · ".join(parts)


def render_sections(order: tuple[str, ...], values: dict[str, Any]) -> str:
    """굵은 소제목 한 줄 + 빈 줄 + 내용. 마지막 항목은 목록으로 받는다."""
    blocks = []
    for heading in order:
        value = values.get(heading)
        if isinstance(value, tuple | list):
            body = "\n".join(value) if value else f"- {BLANK_SECTION}"
        else:
            body = (value or "").strip() or BLANK_SECTION
        blocks.append(f"**{heading}**\n\n{body}")
    return "\n\n".join(blocks)


def day_label(day: date) -> str:
    return f"{day.month}월 {day.day}일"


# 흐름 단계별 미팅 보고서. 딜 섹션 제목과 네 개 서술 항목, 후속 조치 목록을 갖는다.
# 본문은 합니다체다. 확인되지 않은 것은 지어내지 않고 '미확인' 으로 둔다 —
# 모든 칸을 자신 있게 채우면 오히려 사람이 쓴 요약처럼 보인다.
MEETING_SECTIONS: dict[int, dict[str, Any]] = {
    0: {
        "title": "첫 방문·교체 시점 미확인",
        "미팅 목적": "{company} 첫 방문으로 장비 운용 현황과 교체 계획을 확인했습니다."
        " 도입 검토가 시작된 단계인지는 미확인입니다.",
        "논의 내용": "{department}에서 운용 중인 장비의 도입 시기와 하루 사용 건수를"
        " 확인했습니다. 사용 연차가 쌓이면서 출력이 예전 같지 않다는 이야기가 있었습니다."
        " {model} 계열의 제품군과 대략적인 가격대를 안내했습니다.",
        "고객 요구": "{person_sub} 당장의 검토 계획은 없다고 밝혔습니다. 예산 배정 시점은"
        " 미확인입니다.",
        "합의사항": "재방문 일정에 대한 합의 여부는 미확인입니다.",
        "actions": lambda d: (
            action(
                "제품 계열 자료 전달",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "수신 확인"),
                ("상태", "요청"),
            ),
        ),
    },
    1: {
        "title": "노후 장비 교체 검토·예산 시점 미정",
        "미팅 목적": "{company}의 장비 교체 니즈를 구체화하기 위해 재방문했습니다.",
        "논의 내용": "사용 중인 장비의 출력이 떨어져 시술 준비 시간이 늘고 있다는 설명을"
        " 들었습니다. {model} 급으로 교체하는 방향을 검토하고 있으며, {department} 인원의"
        " 숙련도를 고려해 조작 방식이 크게 달라지지 않는 모델을 선호했습니다.",
        "고객 요구": "{person_nom} 예산 배정 전에 실물을 먼저 보고 싶다고 요청했습니다."
        " 예산 시점은 미확인입니다.",
        "합의사항": "데모를 진행하기로 합의했습니다. 구체적인 날짜는 미정입니다.",
        "actions": lambda d: (
            action(
                "데모 일정 조율",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "날짜 확정"),
                ("상태", "합의"),
            ),
            action(
                "사용 부서 참석자 확정",
                ("요청 대상", "{department}"),
                ("담당", "담당 미지정"),
                ("기한", "미확인"),
                ("완료 기준", "참석자 명단 수신"),
                ("상태", "요청"),
            ),
        ),
    },
    2: {
        "title": "데모 진행·소모품 단가 확인 요청",
        "미팅 목적": "{company}에서 {model} 실물 데모를 진행했습니다.",
        "논의 내용": "{department} 인원이 직접 조작해 출력 설정과 프로브 교체 절차를"
        " 확인했습니다. 준비 시간이 기존 장비보다 짧다는 점을 현장에서 확인했습니다."
        " 시술 건당 소모품 소요량에 대한 질문이 있었습니다.",
        "고객 요구": "소모품 연간 소요량과 단가를 문서로 달라는 요청이 있었습니다.",
        "합의사항": "도입 여부에 대한 합의는 확인되지 않았습니다.",
        "actions": lambda d: (
            action(
                "소모품 연간 소요량·단가 정리 전달",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "문서 전달"),
                ("상태", "요청"),
            ),
        ),
    },
    3: {
        "title": "사용 부서 평가 긍정·경쟁사 사양 비교 필요",
        "미팅 목적": "데모 결과에 대한 {department} 내부 평가를 확인했습니다.",
        "논의 내용": "사용 부서 평가는 긍정적이었습니다. 다만 경쟁사 장비와 출력 사양을"
        " 나란히 놓은 자료가 없어 내부 보고가 어렵다는 이야기가 있었습니다. 기존 장비의"
        " 처리 방안은 정해지지 않았습니다.",
        "고객 요구": "{person_nom} 경쟁사 대비 사양 비교표를 요청했습니다.",
        "합의사항": "비교표 전달 후 견적 협의를 진행하기로 합의했습니다.",
        "actions": lambda d: (
            action(
                "사양 비교표 작성·전달",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "비교표 전달"),
                ("상태", "합의"),
            ),
            action(
                "기존 장비 처리 방안 확인",
                ("담당", "담당 미지정"),
                ("기한", "미확인"),
                ("완료 기준", "미확인"),
                ("상태", "요청"),
            ),
        ),
    },
    4: {
        "title": "구성 협의·유지비 포함 견적 요청",
        "미팅 목적": "{company} 구매부서와 견적 구성을 협의했습니다.",
        "논의 내용": "{model} {quantity}대에 소모품을 묶은 구성을 제안했습니다. 예상"
        " 금액대는 {amount} 수준으로 안내했습니다. 설치비와 사용자 교육을 공급가에 포함하는"
        " 조건을 설명했습니다.",
        "고객 요구": "{person_sub} 연간 유지비까지 포함한 형태의 견적을 요청했습니다.",
        "합의사항": "제안한 구성으로 정식 견적서를 발행하기로 합의했습니다.",
        "actions": lambda d: (
            action(
                "정식 견적서 발행",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "견적서 발송"),
                ("상태", "합의"),
            ),
        ),
    },
    5: {
        "title": "견적 발송·경쟁사 병행 검토",
        "미팅 목적": "{company}에 {model} {quantity}대 기준 견적서를 전달했습니다.",
        "논의 내용": "견적 금액은 {amount}입니다. 유효기간은 발행일로부터 30일입니다. 설치와"
        " 사용자 교육을 포함한 조건을 함께 적었습니다. 경쟁사 견적도 병행 검토 중이라는"
        " 이야기가 있어 단가보다 설치·교육 조건을 강조했습니다.",
        "고객 요구": "{person_sub} 내부 검토 후 회신하겠다고 밝혔습니다. 회신 시점은"
        " 미확인입니다.",
        "합의사항": "계약 여부에 대한 합의는 확인되지 않았습니다.",
        "actions": lambda d: (
            action(
                "견적 회신 팔로업 연락",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "회신 확보"),
                ("상태", "요청"),
            ),
            action(
                "원장 면담 요청",
                ("조건", "회신 지연 시"),
                ("담당", "본인"),
                ("기한", "미확인"),
                ("완료 기준", "면담 성사"),
                ("상태", "요청"),
            ),
        ),
    },
    6: {
        "title": "도입 배경 공감·결제 조건 조정 요청",
        "미팅 목적": "{company} 원장과 {department} 담당자가 함께한 자리에서 도입 배경을"
        " 설명했습니다.",
        "논의 내용": "진료 건수 증가에 대비한 투자라는 점에 공감대가 있었습니다. 설치 시"
        " 진료를 멈춰야 하는 시간이 얼마나 되는지 질문이 있어 반나절 이내로 안내했습니다.",
        "고객 요구": "{person_nom} 결제 조건을 검수 후 30일로 조정해 달라고 요청했습니다."
        " 납품 시기를 앞당겨 달라는 요청도 있었습니다.",
        "합의사항": "결제 조건 조정에 합의했습니다. 납품 시기는 생산 일정을 확인한 뒤"
        " 회신하기로 했습니다.",
        "actions": lambda d: (
            action(
                "조정된 조건으로 계약서 준비",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "계약서 발송"),
                ("상태", "합의"),
            ),
            action(
                "생산 일정 확인",
                ("요청 대상", "생산팀"),
                ("담당", "본인"),
                ("기한", "미확인"),
                ("완료 기준", "납품 가능일 회신"),
                ("상태", "요청"),
            ),
        ),
    },
    7: {
        "title": "계약 체결·검수 후 30일 결제",
        "미팅 목적": "{company_with} 계약 조건을 최종 협의하고 체결했습니다.",
        "논의 내용": "{model} {quantity}대 기준 계약금액은 {amount}입니다. 대금은 납품 검수"
        " 완료 후 30일 이내 지급 조건입니다. 보증은 설치일로부터 12개월이며 소모품과 사용자"
        " 과실은 제외한다는 점을 다시 확인했습니다.",
        "고객 요구": "{person_sub} 설치 일정을 진료가 적은 요일로 잡아 달라고 요청했습니다.",
        "합의사항": "계약 체결에 합의하고 서명을 받았습니다.",
        "actions": lambda d: (
            action(
                "발주 등록",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "발주서 접수"),
                ("상태", "합의"),
            ),
            action(
                "설치·사용자 교육 일정 조율",
                ("담당", "본인"),
                ("기한", "미확인"),
                ("완료 기준", "일정 확정"),
                ("상태", "합의"),
            ),
        ),
    },
    8: {
        "title": "설치 완료·교대 근무자 추가 교육 필요",
        "미팅 목적": "{company}에 {model} 장비를 설치하고 사용자 교육을 진행했습니다.",
        "논의 내용": "{department} 인원을 대상으로 출력 설정, 프로브 교체 절차, 일일 점검"
        " 항목을 다뤘습니다. 설치 위치의 접지 상태를 함께 확인했고 이상은 없었습니다.",
        "고객 요구": "교대 근무자가 참석하지 못해 추가 교육 회차를 요청받았습니다.",
        "합의사항": "추가 교육을 진행하기로 합의했습니다. 날짜는 미정입니다.",
        "actions": lambda d: (
            action(
                "교대 근무자 추가 교육 일정 확인",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "교육 이수 명단 전달"),
                ("상태", "합의"),
            ),
        ),
    },
    9: {
        "title": "납품 확인·소모품 정기 공급 논의",
        "미팅 목적": "{company} 납품 일정을 최종 확인했습니다.",
        "논의 내용": "{model} {quantity}대와 소모품 입고를 현장에서 확인했습니다."
        " 인수인계 확인서에 서명을 받았고 미결 항목은 없습니다.",
        "고객 요구": "{person_nom} 소모품을 정기적으로 공급받는 조건을 문의했습니다.",
        "합의사항": "정기 공급 조건을 정리해 다음 방문 때 제안하기로 합의했습니다.",
        "actions": lambda d: (
            action(
                "소모품 정기 공급 제안서 작성",
                ("담당", "본인"),
                ("기한", d["followup"]),
                ("완료 기준", "제안서 전달"),
                ("상태", "합의"),
            ),
            action(
                "3개월 뒤 정기 점검 예약",
                ("담당", "본인"),
                ("기한", "미확인"),
                ("완료 기준", "점검일 확정"),
                ("상태", "요청"),
            ),
        ),
    },
}

# 팀장 지시사항에서 나온 업무. FLOW 단계가 아니라 별도 본문을 쓴다.
DIRECTIVE_SECTIONS: dict[str, Any] = {
    "title": "지시 점검·조건 변경 없음",
    "미팅 목적": "팀장 지시에 따라 {company} 건의 진행 상태를 점검했습니다.",
    "논의 내용": "{department} {person_with} 통화해 {model} {quantity}대 건의 현재 상태와 다음"
    " 일정을 확인했습니다. 진행 금액은 {amount} 기준이며 조건 변경은 없습니다.",
    "고객 요구": "고객 측 추가 요구는 확인되지 않았습니다.",
    "합의사항": "다음 일정에 대한 합의 여부는 미확인입니다.",
    "actions": lambda d: (
        action(
            "점검 결과 팀장 보고",
            ("요청 대상", "영업팀장"),
            ("담당", "본인"),
            ("기한", d["followup"]),
            ("완료 기준", "보고 완료"),
            ("상태", "합의"),
        ),
    ),
}

# 오늘·미래 일정에는 보고서를 만들지 않는다. 아직 일어나지 않은 미팅이다.


def _template(tid: str, name: str, placeholder: str) -> dict[str, Any]:
    """화면이 쓰는 자유 본문 양식.

    id·이름이 frontend/src/shared/meetings.ts, reports.ts 와 같아야 한다. 다르면
    샘플을 넣은 보고서만 옛 양식으로 열린다.
    """
    return {
        "id": tid,
        "name": name,
        "owner": "",
        "updated": "",
        "fields": [
            {
                "id": "body",
                "label": "보고서 본문",
                "type": "textarea",
                "required": True,
                "aiFilled": True,
                "placeholder": placeholder,
            }
        ],
    }


TEMPLATES = {
    "meeting": _template(
        "builtin-meeting-freeform", "미팅 보고서", "미팅에서 논의한 내용을 입력하세요."
    ),
    "daily": _template(
        "builtin-daily-freeform",
        "일일보고서",
        "하루 동안 진행한 업무와 미팅 내용을 자유롭게 작성하세요.",
    ),
    "weekly": _template(
        "builtin-weekly-freeform",
        "주간보고서",
        "한 주 동안의 성과와 다음 계획을 자유롭게 작성하세요.",
    ),
    "monthly": _template(
        "builtin-monthly-freeform",
        "월간보고서",
        "한 달 동안의 실적과 다음 계획을 자유롭게 작성하세요.",
    ),
}


# ---------------------------------------------------------------- 헬퍼


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=SEOUL)


def won(amount: int) -> str:
    return f"{amount:,}원"


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month(day: date) -> date:
    return (day.replace(day=1) + timedelta(days=32)).replace(day=1)


def add_months(day: date, months: int) -> date:
    total = day.year * 12 + (day.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def weekdays(start: date, end: date) -> list[date]:
    """start 부터 end 까지(양끝 포함)의 평일."""
    days = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def week_starts(first: date, last: date) -> list[date]:
    """first 주부터 last 주까지의 주 시작일(일요일)."""
    weeks = []
    day = first
    while day <= last:
        weeks.append(day)
        day += timedelta(days=7)
    return weeks


def week_start(day: date) -> date:
    """대시보드와 화면이 모두 일요일 시작을 쓴다."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def pick(key: str, bound: int) -> int:
    """키에서 0 이상 bound 미만의 정수를 만든다.

    random 모듈을 쓰지 않는다. 시드를 고정해도 파이썬 판이 바뀌면 수열이 달라지는데,
    그러면 같은 기준일로 다시 돌렸을 때 데이터가 조용히 바뀐다.
    """
    digest = hashlib.blake2b(key.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % bound


# 주말 일정은 예외로만 둔다. 키 해시가 0 인 건만 주말에 남긴다.
WEEKEND_KEEP = 12


def weekday_day(day: date, key: str, *, forward: bool) -> date:
    """주말이면 평일로 민다. 지난 일정은 금요일로, 앞으로의 일정은 월요일로."""
    if day.weekday() < 5 or pick(f"wknd:{key}", WEEKEND_KEEP) == 0:
        return day
    step = 1 if forward else -1
    while day.weekday() >= 5:
        day += timedelta(days=step)
    return day


async def upsert(session: AsyncSession, model: Any, values: dict[str, Any]) -> None:
    """id 가 같으면 갱신한다. id 가 시드 이름에서 나오므로 다시 실행해도 늘지 않는다."""
    stmt = insert(model).values(**values)
    updates = {key: getattr(stmt.excluded, key) for key in values if key != "id"}
    await session.execute(stmt.on_conflict_do_update(index_elements=[model.id], set_=updates))


async def link(session: AsyncSession, model: Any, values: dict[str, Any]) -> None:
    """복합 기본키를 쓰는 연결 표. 이미 있으면 그대로 둔다."""
    await session.execute(insert(model).values(**values).on_conflict_do_nothing())


async def upsert_report_deal(session: AsyncSession, values: dict[str, Any]) -> None:
    stmt = insert(ReportDeal).values(**values)
    updates = {
        key: getattr(stmt.excluded, key)
        for key in values
        if key not in {"report_id", "sales_deal_id"}
    }
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[ReportDeal.report_id, ReportDeal.sales_deal_id], set_=updates
        )
    )


# ---------------------------------------------------------------- 계정


def masked_target() -> str:
    """연결 대상을 사람이 확인할 수 있게 보여준다. 자격증명은 지운다."""
    parts = urlsplit(settings.database_url)
    host = parts.hostname or "(알 수 없음)"
    port = f":{parts.port}" if parts.port else ""
    name = (parts.path or "/").lstrip("/") or "(기본)"
    return f"{host}{port}/{name}"


async def resolve_accounts(db: AsyncSession) -> dict[str, UUID]:
    """두 데모 계정의 member.id 를 조회한다. 만들지도, 고치지도 않는다.

    계정과 팀은 사람이 이미 만들어 두었다. 시더가 손대면 되돌릴 사람이 없다.
    기대와 다르면(팀이 다르거나 역할이 다르면) 엉뚱한 곳에 쓰는 것이므로 중단한다.
    """
    rows = (
        await db.execute(
            select(Member.id, Member.email, Member.team_id, Member.display_name, Member.role_code)
            .where(Member.email.in_(medion.EMAILS))
        )
    ).all()
    found = {row.email: row for row in rows}

    ids: dict[str, UUID] = {}
    problems: list[str] = []
    for seed in medion.MEMBERS:
        row = found.get(seed.email)
        if row is None:
            problems.append(f"  {seed.email} 의 member 행이 없습니다.")
            continue
        if row.team_id != TEAM_ID:
            problems.append(
                f"  {seed.email} 이 다른 팀에 속해 있습니다 (team_id={row.team_id})."
            )
            continue
        if row.role_code != seed.role_code:
            problems.append(
                f"  {seed.email} 의 역할이 {row.role_code} 입니다 (기대 {seed.role_code})."
            )
            continue
        if row.display_name != seed.display_name:
            problems.append(
                f"  {seed.email} 의 이름이 {row.display_name} 입니다"
                f" (기대 {seed.display_name})."
            )
            continue
        ids[seed.key] = row.id

    if problems:
        raise SystemExit(
            "데모 계정이 기대와 다릅니다. 엉뚱한 팀을 건드리지 않으려고 중단합니다.\n"
            + "\n".join(problems)
            + "\n계정은 Supabase Dashboard 와 /admin 화면에서 발급합니다."
        )
    return ids


async def ensure_team(db: AsyncSession) -> None:
    """대상 팀이 있는지만 확인한다. 이름도 회사명도 바꾸지 않는다."""
    name = (
        await db.execute(select(Team.name).where(Team.id == TEAM_ID))
    ).scalar_one_or_none()
    if name is None:
        raise SystemExit(f"팀 {TEAM_ID} 이 없습니다. 팀부터 만들어 주세요.")
    if name != TEAM_NAME:
        raise SystemExit(
            f"팀 {TEAM_ID} 의 이름이 '{name}' 입니다 (기대 '{TEAM_NAME}').\n"
            "다른 팀을 가리키고 있을 수 있어 중단합니다."
        )


# ---------------------------------------------------------------- 시더


class Seeder:
    def __init__(self, db: AsyncSession, base: date, member_ids: dict[str, UUID]) -> None:
        self.db = db
        self.base = base
        self.members = member_ids
        self.counts: dict[str, int] = defaultdict(int)

        self.status: dict[str, UUID] = {}
        self.category: dict[str, UUID] = {}
        self.action_tag: dict[str, UUID] = {}
        self.deal_type: dict[str, UUID] = {}
        self.order_status: dict[str, UUID] = {}
        self.quote_status: dict[str, UUID] = {}
        self.contract_status: dict[str, UUID] = {}
        self.pipeline_id: UUID | None = None
        self.stages: dict[str, tuple[UUID, str, int]] = {}

        self.products: dict[str, UUID] = {}
        self.companies: list[tuple[UUID, str, str | None]] = []
        self.contacts: list[dict[str, Any]] = []
        self.deals: list[dict[str, Any]] = []
        self.activities: list[dict[str, Any]] = []

    def bump(self, label: str, amount: int = 1) -> None:
        self.counts[label] += amount

    def day(self, offset: int) -> date:
        return self.base + timedelta(days=offset)

    # ------------------------------------------------------------ 구성

    async def load_configuration(self) -> None:
        """seed_team_configuration 이 넣은 룩업과 파이프라인을 코드로 찾아 둔다."""
        lookups = (
            (CustomerContactStatus, self.status),
            (ActivityCategory, self.category),
            (ActivityActionTag, self.action_tag),
            (SalesDealType, self.deal_type),
            (PurchaseOrderStatus, self.order_status),
            (QuoteStatus, self.quote_status),
            (ContractStatus, self.contract_status),
        )
        for model, target in lookups:
            rows = (
                await self.db.execute(
                    select(model.code, model.id).where(
                        model.team_id == TEAM_ID, model.deleted_at.is_(None)
                    )
                )
            ).all()
            target.update({row.code: row.id for row in rows})
            if not target:
                raise SystemExit(f"{model.__tablename__} 룩업이 비어 있습니다.")

        pipeline = (
            await self.db.execute(
                select(SalesPipeline.id).where(
                    SalesPipeline.team_id == TEAM_ID,
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
                    SalesPipelineStage.phase_code,
                ).where(SalesPipelineStage.sales_pipeline_id == pipeline)
            )
        ).all()
        self.stages = {r.stage_code: (r.id, r.outcome_code, 0) for r in rows}
        self.phases = {r.stage_code: r.phase_code for r in rows}
        for code in STAGE_STEPS:
            if code not in self.stages:
                raise SystemExit(f"파이프라인에 {code} 단계가 없습니다.")

    # ------------------------------------------------------------ 제품·고객사

    async def seed_products(self) -> None:
        for position, (name, category, price, shelf, spec) in enumerate(medion.PRODUCTS):
            product_id = sid("product", name)
            self.products[name] = product_id
            await upsert(
                self.db,
                Product,
                {
                    "id": product_id,
                    "team_id": TEAM_ID,
                    "name": name,
                    "active": True,
                    "category_code": category,
                    "unit_price": price,
                    "shelf_life_months": shelf,
                    "spec": spec,
                    "memo": None,
                    "image_storage_key": None,
                },
            )
            self.bump("product")
            del position

    async def seed_companies(self) -> None:
        """공공데이터 병원을 고객사로 넣는다. 이름·우편번호·주소·지역만 쓴다."""
        for hospital in hospitals.sample(COMPANY_COUNT):
            company_id = sid("customer_company", hospital.name)
            self.companies.append((company_id, hospital.name, hospital.region_code))
            await upsert(
                self.db,
                CustomerCompany,
                {
                    "id": company_id,
                    "team_id": TEAM_ID,
                    "name": hospital.name,
                    "region_code": hospital.region_code,
                    # 원본에 사업자번호가 없다. 지어내면 실존 사업자와 겹칠 수 있어 비워 둔다.
                    "business_no": None,
                    "postcode": hospital.postcode,
                    "address": hospital.address,
                    "address_detail": None,
                    "created_at": at(self.day(-200), 9),
                },
            )
            self.bump("customer_company")

    async def seed_contacts(self) -> None:
        """앞쪽 고객사에 담당자를 붙인다. 나머지는 미개척 고객사로 남긴다."""
        for index in range(CONTACT_COMPANY_COUNT):
            company_id, company_name, _ = self.companies[index]
            # 다섯 곳마다 담당자를 둘 둔다. 고객 상세에서 복수 담당자를 시연한다.
            for slot in range(2 if index % 5 == 0 else 1):
                key = f"{index:03d}-{slot}"
                owner = LEADER if (index + slot) % 2 == 0 else MEMBER
                name = (
                    medion.SURNAMES[pick(f"sn:{key}", len(medion.SURNAMES))]
                    + medion.GIVEN_NAMES[pick(f"gn:{key}", len(medion.GIVEN_NAMES))]
                )
                registered = self.day(-200 + pick(f"reg:{key}", 150))
                contact_id = sid("customer_contact", key)
                record = {
                    "id": contact_id,
                    "company_id": company_id,
                    "company_name": company_name,
                    "company_index": index,
                    "name": name,
                    "owner": owner,
                    "department": medion.DEPARTMENTS[
                        pick(f"dept:{key}", len(medion.DEPARTMENTS))
                    ],
                    "job_title": medion.JOB_TITLES[pick(f"jt:{key}", len(medion.JOB_TITLES))],
                }
                self.contacts.append(record)
                status_code = medion.CONTACT_STATUS_CODES[
                    pick(f"st:{key}", len(medion.CONTACT_STATUS_CODES))
                ]
                # 여섯 곳에 한 곳은 메모를 비워 둔다. 빈 메모 화면도 데모에 필요하다.
                memos = medion.CONTACT_MEMOS[status_code]
                memo = (
                    None
                    if index % 6 == 5
                    else memos[pick(f"memo:{key}", len(memos))].format(
                        name=name, job=record["job_title"], dept=record["department"]
                    )
                )
                await upsert(
                    self.db,
                    CustomerContact,
                    {
                        "id": contact_id,
                        "company_id": company_id,
                        "owner_member_id": self.members[owner],
                        "created_by_member_id": self.members[owner],
                        "name": name,
                        "department": record["department"],
                        "job_title": record["job_title"],
                        # 예약 도메인과 통화되지 않는 번호만 쓴다.
                        "email": f"contact{index:03d}{slot}@demo.test",
                        "phone": f"010-0000-{2000 + index * 2 + slot:04d}",
                        "telephone": None,
                        "fax": None,
                        "customer_contact_status_id": self.status[status_code],
                        "source_code": medion.SOURCE_CODES[
                            pick(f"src:{key}", len(medion.SOURCE_CODES))
                        ],
                        "memo": memo,
                        "visited": index % 3 != 2,
                        "registered_at": at(registered, 10),
                        "deleted_at": None,
                    },
                )
                self.bump("customer_contact")
                # 담당 배정. 팀원 역할은 이 표로 고객을 거르므로 소유자는 반드시 넣는다.
                await link(
                    self.db,
                    CustomerContactAssignee,
                    {"customer_contact_id": contact_id, "member_id": self.members[owner]},
                )
                # 열 곳마다 팀장·팀원을 함께 배정해 공동 담당을 시연한다.
                if index % 10 == 0:
                    other = MEMBER if owner == LEADER else LEADER
                    await link(
                        self.db,
                        CustomerContactAssignee,
                        {"customer_contact_id": contact_id, "member_id": self.members[other]},
                    )
                    self.bump("customer_contact_assignee_shared")

    # ------------------------------------------------------------ 딜

    def _contact_for(self, owner: str, key: str) -> dict[str, Any]:
        """딜 담당자와 고객 담당자의 소유자를 맞춘다.

        팀원 역할의 활동 조회가 '내 활동이면서 내 고객' 인 것만 통과시키므로,
        둘이 어긋나면 그 팀원 화면에서 일정이 통째로 사라진다.
        """
        pool = [c for c in self.contacts if c["owner"] == owner]
        return pool[pick(f"ct:{key}", len(pool))]

    def _amounts(self, key: str, model: str, quantity: int) -> dict[str, Any]:
        system_price = medion.UNIT_PRICE[model]
        accessory = medion.ACCESSORY_MODELS[pick(f"acc:{key}", len(medion.ACCESSORY_MODELS))]
        accessory_qty = 2 + pick(f"aq:{key}", 5)
        deal_amount = system_price * quantity + medion.UNIT_PRICE[accessory] * accessory_qty
        # 계약은 견적에서 0~4% 깎인다. 발주 매입가(판매가의 75%)보다 항상 크다.
        discount = deal_amount * pick(f"dc:{key}", 5) // 100
        contract_amount = (deal_amount - discount) // 10_000 * 10_000
        return {
            "accessory": accessory,
            "accessory_qty": accessory_qty,
            "deal_amount": deal_amount,
            "quote_amount": deal_amount,
            "contract_amount": contract_amount,
            "order_amount": system_price * quantity * 75 // 100,
        }

    def plan_deals(self) -> None:
        """딜 목록을 먼저 다 만든 뒤 번호를 붙인다. 번호가 실행마다 같아야 한다."""
        plans: list[dict[str, Any]] = []

        # 1) 매출 축. 2년 전 1월부터 이번 달까지 매월 계약이 체결된 확정 딜을 깔아 둔다.
        #    매출분석의 연/반기/분기/월 탭과 대시보드의 이번 달 카드가 모두 이 구간을 읽는다.
        start = date(self.base.year - 2, 1, 1)
        month = start
        while month <= month_start(self.base):
            tag = month.isoformat()
            count = 2 + pick(f"cnt:{tag}", 4)
            for j in range(count):
                key = f"R{tag}-{j}"
                owner = LEADER if (month.month + j) % 2 == 0 else MEMBER
                # 팀장이 상위 모델을 더 자주 맡아 담당자별 실적 차이가 드러난다.
                models = ("LR2000", "LR-PRO", "LR2000") if owner == LEADER else ("LR1000", "LR2000")
                model = models[pick(f"md:{key}", len(models))]
                quantity = 1 + pick(f"qt:{key}", 2)

                last = (next_month(month) - timedelta(days=1)).day
                if month == month_start(self.base):
                    last = self.base.day  # 이번 달 계약일이 오늘을 넘지 않게 한다.
                signed = month.replace(day=1 + pick(f"sd:{key}", last))
                opened = signed - timedelta(days=45 + pick(f"op:{key}", 40))
                quote_on = signed - timedelta(days=10 + pick(f"qd:{key}", 20))
                stage = "order_delivered" if j % 4 == 3 else "contract_completed"

                plans.append(
                    {
                        "key": key,
                        "owner": owner,
                        "stage": stage,
                        "model": model,
                        "quantity": quantity,
                        "opened": opened,
                        "quote_on": quote_on,
                        "signed": signed,
                        "closed": None,
                        "rich": False,
                        "title": f"{model} {quantity}대 도입",
                        "memo": None,
                    }
                )
            month = next_month(month)

        # 2) 서사 축. 최근 구간의 딜에만 활동·보고서·발주·C/S 가 붙는다.
        for seed in medion.NARRATIVE_DEALS:
            steps = STAGE_STEPS[seed.stage_code]
            opened = self.day(seed.opened_offset)
            quote_on = opened + timedelta(days=FLOW[QUOTE_STEP][3]) if steps > QUOTE_STEP else None
            signed = (
                opened + timedelta(days=FLOW[CONTRACT_STEP][3])
                if seed.stage_code in SIGNED_STAGES
                else None
            )
            closed = (
                opened + timedelta(days=FLOW[steps - 1][3] + 5)
                if seed.stage_code == "closed_cancelled"
                else None
            )
            plans.append(
                {
                    "key": seed.key,
                    "owner": seed.owner,
                    "stage": seed.stage_code,
                    "model": seed.model,
                    "quantity": seed.quantity,
                    "opened": opened,
                    "quote_on": quote_on,
                    "signed": signed,
                    "closed": closed,
                    "rich": True,
                    "title": f"{seed.title} ({seed.model})",
                    "memo": seed.memo,
                }
            )

        # 번호는 계약연도 기준으로 매긴다. 화면에서 연도별로 읽히는 편이 자연스럽다.
        counter: dict[int, int] = defaultdict(int)
        stage_seq: dict[str, int] = defaultdict(int)
        for plan in plans:
            plan.update(self._amounts(plan["key"], plan["model"], plan["quantity"]))
            year = (plan["signed"] or plan["opened"]).year
            counter[year] += 1
            plan["deal_no"] = f"MD-DL-{year}-{counter[year]:04d}"
            # 번호의 연도는 딜 번호와 맞춘다. 견적 연도로 매기면 계약이 해를 넘긴 딜에서
            # 같은 (연도, 일련번호) 가 두 번 나와 유일 제약에 걸린다.
            plan["quote_no"] = f"MD-QT-{year}-{counter[year]:04d}" if plan["quote_on"] else None
            has_contract_no = plan["stage"] in SIGNED_STAGES or plan["stage"] == "contract_sent"
            plan["contract_no"] = f"MD-CT-{year}-{counter[year]:04d}" if has_contract_no else None
            plan["contact"] = self._contact_for(plan["owner"], plan["key"])
            plan["stage_position"] = stage_seq[plan["stage"]]
            stage_seq[plan["stage"]] += 1
        self.deals = plans

    async def seed_deals(self) -> None:
        deal_types = ("new_installation", "expansion", "renewal", "maintenance")
        for plan in self.deals:
            deal_id = sid("sales_deal", plan["key"])
            plan["id"] = deal_id
            contact = plan["contact"]
            stage_id, outcome, _ = self.stages[plan["stage"]]
            signed = plan["signed"]
            # 확정 딜만 계약 종료일을 갖는다. 1년 뒤로 두면 1년 전 계약이 갱신 카드에 잡힌다.
            ends_on = signed + timedelta(days=365) if signed else None

            await upsert(
                self.db,
                SalesDeal,
                {
                    "id": deal_id,
                    "team_id": TEAM_ID,
                    "deal_no": plan["deal_no"],
                    "customer_company_id": contact["company_id"],
                    "customer_contact_id": contact["id"],
                    "owner_member_id": self.members[plan["owner"]],
                    "product_id": self.products[plan["model"]],
                    "sales_pipeline_id": self.pipeline_id,
                    "sales_pipeline_stage_id": stage_id,
                    "title": plan["title"],
                    "description": None,
                    "sales_deal_type_id": self.deal_type[
                        deal_types[pick(f"dt:{plan['key']}", len(deal_types))]
                    ],
                    "deal_amount": plan["deal_amount"],
                    "opened_on": plan["opened"],
                    "closed_on": plan["closed"],
                    "quote_no": plan["quote_no"],
                    "quote_issued_on": plan["quote_on"],
                    "quote_valid_until": (
                        plan["quote_on"] + timedelta(days=30) if plan["quote_on"] else None
                    ),
                    "quote_amount": plan["quote_amount"] if plan["quote_on"] else None,
                    "quote_status_id": self.quote_status.get(
                        QUOTE_STATUS_BY_STAGE.get(plan["stage"], "")
                    ),
                    "contract_no": plan["contract_no"],
                    "contract_signed_on": signed,
                    "contract_ends_on": ends_on,
                    "contract_amount": plan["contract_amount"] if plan["contract_no"] else None,
                    "contract_status_id": self.contract_status.get(
                        CONTRACT_STATUS_BY_STAGE.get(plan["stage"], "")
                    ),
                    "quote_delivery_terms": medion.DELIVERY_TERMS if plan["quote_on"] else None,
                    "contract_payment_terms": medion.PAYMENT_TERMS if plan["contract_no"] else None,
                    "contract_late_interest_terms": None,
                    "warranty_terms": medion.WARRANTY if signed else None,
                    "expected_delivery_at": (
                        at(signed + timedelta(days=21), 14)
                        if signed and plan["stage"] != "order_delivered"
                        else None
                    ),
                    "memo": plan["memo"],
                    "quote_memo": None,
                    "contract_memo": None,
                    "order_memo": None,
                    "source_code": None,
                    "stage_position": plan["stage_position"],
                    "deleted_at": None,
                    "created_at": at(plan["opened"], 9),
                    "updated_at": at(plan["signed"] or plan["opened"], 17),
                },
            )
            self.bump("sales_deal")
            self.bump(f"deal_{outcome}")

            # 딜 품목. 장비 본체와 곁들인 액세서리를 함께 담아 견적 금액과 맞춘다.
            for position, (model, quantity) in enumerate(
                ((plan["model"], plan["quantity"]), (plan["accessory"], plan["accessory_qty"]))
            ):
                await upsert(
                    self.db,
                    SalesDealItem,
                    {
                        "id": sid("sales_deal_item", f"{plan['key']}:{position}"),
                        "sales_deal_id": deal_id,
                        "product_id": self.products[model],
                        "quantity": quantity,
                        "unit_price": medion.UNIT_PRICE[model],
                        "position": position,
                    },
                )
                self.bump("sales_deal_item")

    # ------------------------------------------------------------ 일정·미팅

    async def _activity(
        self,
        key: str,
        *,
        owner: str,
        contact: dict[str, Any],
        title: str,
        category: str,
        action_tag: str | None,
        day: date,
        hour: int,
        deal_id: UUID | None = None,
        product: str | None = None,
        note: str | None = None,
        step: int | None = None,
        deal_key: str | None = None,
    ) -> UUID:
        activity_id = sid("activity", key)
        # 오늘 일정은 옮기지 않는다. 대시보드가 기준일 일정을 세어 검증한다.
        if day != self.base:
            day = weekday_day(day, key, forward=day > self.base)
        starts = at(day, hour)
        ends = starts + timedelta(hours=1)
        # 오늘 일정은 아직 진행 중이다. 완료 처리는 지난 일정에만 한다.
        completed = ends if day < self.base else None
        await upsert(
            self.db,
            Activity,
            {
                "id": activity_id,
                "team_id": TEAM_ID,
                "owner_member_id": self.members[owner],
                "customer_contact_id": contact["id"],
                # 딜을 달면 딜의 고객사와 같아야 한다. 아니면 모든 활동 조회에서 사라진다.
                "customer_company_id": contact["company_id"],
                "end_user_contact_id": None,
                "activity_category_id": self.category[category],
                "activity_action_tag_id": self.action_tag[action_tag] if action_tag else None,
                "title": title,
                "starts_at": starts,
                "ends_at": ends,
                "all_day": False,
                "due_at": None,
                "location": contact["company_name"],
                "completed_at": completed,
                "note": note,
                "deleted_at": None,
                "product_id": self.products[product] if product else None,
                "sales_deal_id": deal_id,
                "purchase_order_id": None,
                "created_at": at(day, 8),
                "updated_at": completed or starts,
            },
        )
        self.bump("activity")
        self.activities.append(
            {
                "id": activity_id,
                "key": key,
                "owner": owner,
                "day": day,
                # 보고서의 report.content.time 이 이 값을 쓴다.
                "hour": hour,
                "contact": contact,
                "step": step,
                "deal_key": deal_key,
                "title": title,
            }
        )
        return activity_id

    def _fill_step(self, plan: dict[str, Any], day: date) -> int:
        """개설일로부터 지난 날수에 가장 가까운 FLOW 단계.

        제목과 보고서 본문이 모두 이 단계에서 나오므로, 날짜와 이야기가 어긋나지 않는다.
        """
        elapsed = (day - plan["opened"]).days
        last = STAGE_STEPS[plan["stage"]] - 1
        step = min(range(len(FLOW)), key=lambda i: abs(FLOW[i][3] - elapsed))
        return min(step, last)

    def _fill_pool(self, owner: str, day: date) -> list[dict[str, Any]]:
        """그 날 살아 있던 딜. 개설 전이거나 이미 끝난 딜에는 미팅을 붙이지 않는다."""
        return [
            plan
            for plan in self.deals
            if plan["owner"] == owner
            and plan["opened"] <= day
            and (plan["closed"] is None or day <= plan["closed"])
            # 계약 뒤에도 설치·교육·납품 미팅이 이어지므로 석 달까지는 붙인다.
            and (plan["signed"] is None or day <= plan["signed"] + timedelta(days=90))
        ]

    async def _fill_weekdays(self) -> None:
        """평일이 비지 않게 미팅을 채운다.

        서사 딜 17건의 FLOW 만으로는 하루 0건인 평일이 대부분이다. 매출 축의 얕은 딜도
        고객·모델·금액을 모두 갖고 있어(plan_deals) 미팅 보고서 본문이 그대로 나온다.
        """
        counts: dict[tuple[str, date], int] = defaultdict(int)
        hours: dict[tuple[str, date], set[int]] = defaultdict(set)
        for record in self.activities:
            counts[(record["owner"], record["day"])] += 1
            hours[(record["owner"], record["day"])].add(record["hour"])

        dense_start = self.day(DENSE_FROM)
        last = self.day(DENSE_TO)
        day = add_months(month_start(self.base), -SPARSE_MONTHS)
        while day <= last:
            if day.weekday() >= 5:
                day += timedelta(days=1)
                continue
            for owner in (LEADER, MEMBER):
                if day >= dense_start:
                    target = DENSE_MIN
                elif pick(f"sparse:{owner}:{day.isoformat()}", 10) < SPARSE_RATIO:
                    target = SPARSE_MIN
                else:
                    target = 0
                pool = self._fill_pool(owner, day)
                if not pool:
                    continue
                used = hours[(owner, day)]
                for index in range(counts[(owner, day)], target):
                    key = f"fill:{owner}:{day.isoformat()}:{index}"
                    plan = pool[pick(f"fillpick:{key}", len(pool))]
                    step = self._fill_step(plan, day)
                    title, category, tag, _ = FLOW[step]
                    hour = next((h for h in FILL_HOURS if h not in used), FILL_HOURS[-1])
                    used.add(hour)
                    await self._activity(
                        key,
                        owner=owner,
                        contact=plan["contact"],
                        title=f"{plan['contact']['company_name']} {title}",
                        category=category,
                        action_tag=tag,
                        day=day,
                        hour=hour,
                        deal_id=plan["id"],
                        product=plan["model"],
                        step=step,
                        deal_key=plan["key"],
                    )
                    self.bump("activity_fill")
            day += timedelta(days=1)

    async def seed_activities(self) -> None:
        # 1) 서사 딜의 진행 흐름. 견적일·계약일이 이 표에서 나왔으므로 날짜가 어긋나지 않는다.
        for plan in self.deals:
            if not plan["rich"]:
                continue
            contact = plan["contact"]
            for step in range(STAGE_STEPS[plan["stage"]]):
                title, category, tag, offset = FLOW[step]
                day = plan["opened"] + timedelta(days=offset)
                if day >= self.base:
                    break
                await self._activity(
                    f"{plan['key']}:{step}",
                    owner=plan["owner"],
                    contact=contact,
                    title=f"{contact['company_name']} {title}",
                    category=category,
                    action_tag=tag,
                    day=day,
                    hour=9 + pick(f"hr:{plan['key']}:{step}", 8),
                    deal_id=plan["id"],
                    product=plan["model"],
                    step=step,
                    deal_key=plan["key"],
                )

        # 2) 오늘 일정. 팀장과 팀원 각각 세 건씩 둬 두 사람의 대시보드가 모두 차게 한다.
        today_titles = (
            ("병원 장비 데모", "demo", "demo_in_progress"),
            ("구매부서 견적 협의", "visit", "meeting"),
            ("원장·진료과 미팅", "visit", "meeting"),
        )
        for owner in (LEADER, MEMBER):
            pool = [p for p in self.deals if p["rich"] and p["owner"] == owner]
            for index, (title, category, tag) in enumerate(today_titles):
                plan = pool[index % len(pool)]
                await self._activity(
                    f"today:{owner}:{index}",
                    owner=owner,
                    contact=plan["contact"],
                    title=f"{plan['contact']['company_name']} {title}",
                    category=category,
                    action_tag=tag,
                    day=self.base,
                    hour=(10, 14, 16)[index],
                    deal_id=plan["id"],
                    product=plan["model"],
                    deal_key=plan["key"],
                )
                self.bump("activity_today")

        # 2.5) 평일 채움. 위 두 단계가 끝난 뒤 부족한 날만 메운다. 순서를 바꾸면 겹친다.
        await self._fill_weekdays()

        # 3) 앞으로의 일정. 아직 끝나지 않은 딜에만 후속을 단다. 보고서는 달지 않는다.
        future_titles = (
            ("납품 일정 조율", "delivery", "delivery_completed"),
            ("설치·사용자 교육", "education", "product_training"),
            ("계약 조건 후속 협의", "visit", "meeting"),
        )
        for plan in self.deals:
            if not plan["rich"] or plan["stage"] in ("closed_cancelled", "order_delivered"):
                continue
            for index in range(1 + pick(f"fu:{plan['key']}", 2)):
                title, category, tag = future_titles[
                    pick(f"ft:{plan['key']}:{index}", len(future_titles))
                ]
                offset = 2 + pick(f"fo:{plan['key']}:{index}", 44)
                await self._activity(
                    f"future:{plan['key']}:{index}",
                    owner=plan["owner"],
                    contact=plan["contact"],
                    title=f"{plan['contact']['company_name']} {title}",
                    category=category,
                    action_tag=tag,
                    day=self.day(offset),
                    hour=9 + pick(f"fh:{plan['key']}:{index}", 8),
                    deal_id=plan["id"],
                    product=plan["model"],
                    deal_key=plan["key"],
                )
                self.bump("activity_future")

        # 4) 지시사항에서 나온 업무. notice → activity 외래키가 스키마에 없어서,
        #    본문 첫 줄에 근거를 적어 화면에서 두 화면을 이어 볼 수 있게 한다.
        directive_titles = {
            "D01": ("데모 준비 상태 점검", "demo", "demo_requested"),
            "D02": ("견적 발송 건 팔로업", "call", "meeting"),
            "D03": ("계약 갱신 사전 점검", "visit", "meeting"),
        }
        member_deals = [p for p in self.deals if p["rich"] and p["owner"] == MEMBER]
        for index, seed in enumerate(n for n in medion.NOTICES if n.type == "DIRECTIVE"):
            title, category, tag = directive_titles[seed.key]
            plan = member_deals[index % len(member_deals)]
            due = self.day(seed.due_offset or 0)
            await self._activity(
                f"directive:{seed.key}",
                owner=MEMBER,
                contact=plan["contact"],
                title=f"{plan['contact']['company_name']} {title}",
                category=category,
                action_tag=tag,
                day=due,
                hour=11,
                deal_id=plan["id"],
                product=plan["model"],
                note=f"지시사항: {seed.title} (기한 {due.month}월 {due.day}일)",
                deal_key=plan["key"],
            )
            self.bump("activity_directive")

    # ------------------------------------------------------------ 보고서

    def _review(
        self, author: str, day: date, key: str
    ) -> tuple[str, UUID | None, datetime | None]:
        """작성 시점으로 검토 상태를 정한다.

        팀장이 쓴 글은 검토자가 없다. 팀원 글은 한 주가 지나면 확정된다 — 한 달 전 보고서가
        검토 대기로 남아 있으면 결재가 멈춘 팀처럼 보인다. 열에 한 건만 대기로 남겨
        검토 대기 탭이 비지 않게 한다.
        """
        if author == LEADER:
            return "approved", None, None
        delta = (self.base - day).days
        if delta >= 7:
            if pick(f"pend:{key}", 10) != 0:
                return "approved", self.members[LEADER], at(day + timedelta(days=2), 10)
            return "submitted", None, None
        if delta >= 3:
            return "submitted", None, None
        return "draft", None, None

    def _facts(self, plan: dict[str, Any]) -> dict[str, str]:
        """본문 템플릿이 쓰는 낱말. 조사가 이미 붙은 꼴로 만들어 둔다."""
        contact = plan["contact"]
        person = f"{contact['name']} {contact['job_title']}"
        return {
            "company": contact["company_name"],
            "department": contact["department"],
            "person": person,
            "person_sub": person + josa(person, "은", "는"),
            "person_nom": person + josa(person, "이", "가"),
            "person_with": person + josa(person, "과", "와"),
            "company_with": contact["company_name"] + josa(contact["company_name"], "과", "와"),
            "model": plan["model"],
            "quantity": str(plan["quantity"]),
            "amount": won(plan["contract_amount"]),
        }

    def _deal_body(self, plan: dict[str, Any], step: int | None, day: date) -> tuple[str, str]:
        """딜 섹션의 (제목, 본문). 화면이 읽는 굵은 소제목 꼴로 낸다."""
        spec = MEETING_SECTIONS[step] if step is not None else DIRECTIVE_SECTIONS
        facts = self._facts(plan)
        facts["followup"] = day_label(day + timedelta(days=7))
        values = {
            heading: spec[heading].format(**facts)
            for heading in MEETING_ORDER
            if heading in spec
        }
        values["후속 조치"] = tuple(line.format(**facts) for line in spec["actions"](facts))
        return spec["title"], render_sections(MEETING_ORDER, values)

    def _assessment(self, plan: dict[str, Any]) -> dict[str, Any]:
        """딜 카드의 ML 배지 근거.

        실제 모델을 돌린 값이 아니다. model_version 에 그 사실을 남겨 둔다.
        프런트(generatedDraft.readMeetingAnalysis)는 label·확률·버전 셋이 모두
        맞을 때만 배지를 그리므로 타입을 정확히 맞춘다.
        """
        stage = plan["stage"]
        if stage in ("contract_completed", "order_in_progress", "order_delivered"):
            label, low, span = "high", 78, 16
        elif stage in ("contract_sent", "contract_review", "quote_sent"):
            label, low, span = "high", 55, 21
        elif stage == "closed_cancelled":
            label, low, span = "watch", 15, 16
        else:
            label, low, span = "watch", 30, 21
        return {
            "meeting_run_id": str(sid("agent_run", plan["key"])),
            "analysis_run_id": None,
            "analysis_status": "completed",
            "deal_assessment": {
                "label": label,
                "high_probability": (low + pick(f"ml:{plan['key']}", span)) / 100,
                "model_version": "demo-seed-v1",
            },
            "features": None,
            "analysis_error": None,
            "report_error": None,
        }

    async def _write_report(self, values: dict[str, Any]) -> None:
        await upsert(self.db, Report, values)
        self.bump("report")
        self.bump(f"report_{values['report_kind']}")
        self.bump(f"report_status_{values['status_code']}")

    async def _meeting_report(
        self,
        key: str,
        *,
        record: dict[str, Any],
        plans: list[dict[str, Any]],
        status_override: tuple[str, UUID | None, datetime | None] | None = None,
        review_note: str | None = None,
    ) -> None:
        """미팅 보고서 한 건과 딜 섹션들.

        미팅 정보(부서·고객 담당자·장소)는 report.content 에서만 읽는다
        (frontend/src/pages/Meetings/useMeetingReports.ts). 여기를 비우면 화면이
        영영 '—' 를 그린다 — 일정을 다시 조회하는 경로가 없다.
        """
        day = record["day"]
        author = plans[0]["owner"]
        contact = plans[0]["contact"]
        title = record["title"]
        status, reviewer, reviewed_at = status_override or self._review(author, day, key)
        report_id = sid("report", key)
        written = at(day, 18)

        await self._write_report(
            {
                "id": report_id,
                "team_id": TEAM_ID,
                "author_member_id": self.members[author],
                # 미팅 보고서는 수신자를 두지 않는다. 딜 단위로 읽히는 문서다.
                "recipient_member_id": None,
                "template_snapshot": TEMPLATES["meeting"],
                "source_activity_id": record["id"],
                # 미팅의 딜은 report_deal 이 들고 있다. 여기 두면 두 곳이 갈린다.
                "sales_deal_id": None,
                "customer_company_id": contact["company_id"],
                "report_kind": "meeting",
                "report_date": day,
                "period_start": None,
                "period_end": None,
                "status_code": status,
                "content": {
                    "time": f"{record['hour']:02d}:00",
                    "hospital": contact["company_name"],
                    "dept": contact["department"],
                    "contact": f"{contact['name']} {contact['job_title']}",
                    "place": f"{contact['company_name']} {contact['department']}",
                    "title": title,
                },
                "title": title,
                "body": None,
                # 딜이 둘 이상일 때만 공통 기록을 남긴다. 여기는 소제목 없는 평목록이다
                # (backend/app/agents/reports/skills/report-shared/SKILL.md).
                "common_body": self._common_body(record, plans) if len(plans) > 1 else None,
                "unassigned_body": self._unassigned_body(record, plans),
                "structured_values": {},
                "transcript": None,
                "source_snapshot": None,
                "ai_evidence": None,
                "note": None,
                "review_note": review_note,
                "reviewed_by_member_id": reviewer,
                "reviewed_at": reviewed_at,
                "created_at": written,
                "updated_at": reviewed_at or written,
            }
        )

        for position, plan in enumerate(plans):
            # 함께 본 딜은 자기 단계에 맞는 본문을 갖는다. 같은 글을 두 번 쓰면
            # 딜마다 다른 이야기가 오가는 실제 미팅처럼 보이지 않는다.
            step = record["step"] if position == 0 else STAGE_STEPS[plan["stage"]] - 1
            section_title, body = self._deal_body(plan, step, day)
            snapshot = {
                "id": str(plan["id"]),
                "label": plan["deal_no"],
                "note": plan["title"],
            }
            await upsert_report_deal(
                self.db,
                {
                    "report_id": report_id,
                    "sales_deal_id": plan["id"],
                    "deal_snapshot": snapshot,
                    "content": {
                        "product": plan["model"],
                        "title": section_title,
                        "values": {"body": body},
                    },
                    "position": position,
                    "deal_no_snapshot": snapshot["label"],
                    "deal_title_snapshot": snapshot["note"],
                    "title": section_title,
                    "body": body,
                    "structured_values": {},
                    "ai_evidence": self._assessment(plan),
                    "created_at": written,
                    "updated_at": reviewed_at or written,
                },
            )
            self.bump("report_deal")
        if len(plans) > 1:
            self.bump("report_multi_deal")

    def _common_body(self, record: dict[str, Any], plans: list[dict[str, Any]]) -> str:
        """미팅 공통 기록. 소제목 없이 확인된 사실을 한 줄에 하나씩 쓴다."""
        company = plans[0]["contact"]["company_name"]
        models = " · ".join(plan["model"] for plan in plans)
        return "\n".join(
            (
                f"- {company} 건 {len(plans)}건({models})을 한자리에서 함께 검토했습니다.",
                "- 두 건의 설치 일정을 같은 주에 묶는 방안을 논의했습니다.",
                f"- 다음 공통 점검은 {day_label(record['day'] + timedelta(days=14))}로"
                " 이야기했으며 확정 여부는 미확인입니다.",
            )
        )

    def _unassigned_body(
        self, record: dict[str, Any], plans: list[dict[str, Any]]
    ) -> str | None:
        """딜 미지정 기록. 어느 딜에도 붙지 않는 확인 필요 사항만 남긴다."""
        if len(plans) < 2 or pick(f"un:{record['key']}", 2) == 0:
            return None
        return "\n".join(
            (
                "- 기존 장비의 처리 방안은 어느 건에 속하는지 확인되지 않았습니다.",
                "- 원내 전기 증설 필요 여부는 시설팀 확인이 필요합니다.",
            )
        )

    async def _period_report(
        self,
        key: str,
        *,
        author: str,
        kind: str,
        day: date,
        title: str,
        order: tuple[str, ...],
        values: dict[str, Any],
        period: tuple[date, date] | None = None,
        activity_ids: tuple[UUID, ...] = (),
    ) -> None:
        """일일·주간·월간 보고서. 미팅과 같은 굵은 소제목 꼴을 쓴다."""
        status, reviewer, reviewed_at = self._review(author, day, key)
        report_id = sid("report", key)
        body = render_sections(order, values)
        written = at(day, 18)

        await self._write_report(
            {
                "id": report_id,
                "team_id": TEAM_ID,
                "author_member_id": self.members[author],
                "recipient_member_id": None if author == LEADER else self.members[LEADER],
                "template_snapshot": TEMPLATES[kind],
                "source_activity_id": None,
                "sales_deal_id": None,
                "customer_company_id": None,
                "report_kind": kind,
                "report_date": day,
                "period_start": period[0] if period else None,
                "period_end": period[1] if period else None,
                "status_code": status,
                "content": {"values": {"body": body}},
                "title": title,
                "body": body,
                "common_body": None,
                "unassigned_body": None,
                "structured_values": {},
                "transcript": None,
                "source_snapshot": None,
                "ai_evidence": None,
                "note": None,
                "review_note": None,
                "reviewed_by_member_id": reviewer,
                "reviewed_at": reviewed_at,
                "created_at": written,
                "updated_at": reviewed_at or written,
            }
        )
        for activity_id in activity_ids:
            await link(
                self.db, ReportActivity, {"report_id": report_id, "activity_id": activity_id}
            )

    def _companion(self, record: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any] | None:
        """같은 고객사·같은 담당자의 다른 딜. 한 미팅에서 둘을 함께 본 것으로 쓴다.

        새 딜을 만들지 않는다. 이미 있는 딜 중 미팅일 이전에 열린 것만 고른다 —
        아직 열리지도 않은 딜을 미팅에서 논의할 수는 없다.
        """
        if pick(f"pair:{record['key']}", 3) != 0:
            return None
        company_id = plan["contact"]["company_id"]
        pool = [
            other
            for other in self.deals
            if other["key"] != plan["key"]
            and other["owner"] == plan["owner"]
            and other["contact"]["company_id"] == company_id
            and other["opened"] <= record["day"]
        ]
        return pool[pick(f"pairpick:{record['key']}", len(pool))] if pool else None

    async def seed_reports(self) -> None:
        deals_by_key = {p["key"]: p for p in self.deals}
        # 월간이 덮는 구간. 일일·주간도 같은 날부터 만든다. 보고서 상세의 '관련 보고서'가
        # 하위 보고서를 날짜로 다시 조회해 그리므로(frontend/src/pages/Daily/sources.ts),
        # 이 구간이 어긋나면 월간을 열었을 때 관련 보고서가 빈다.
        period_start = add_months(month_start(self.base), -PERIOD_MONTHS)

        # 1) 미팅 보고서. 지난 일정은 하나도 빠짐없이 붙인다.
        #    화면이 완료된 미팅에 '보고서 미작성' 을 띄우므로 빠뜨리면 데모 중에 드러난다.
        #    오늘과 미래 일정에는 만들지 않는다 — 아직 일어나지 않은 미팅이다.
        meeting_records = [
            r for r in self.activities if r["day"] < self.base and r["deal_key"]
        ]
        # 팀장이 되돌려 보낸 보고서를 한 건 남긴다. 반려 탭이 비어 있지 않게 한다.
        member_records = [
            r for r in meeting_records if deals_by_key[r["deal_key"]]["owner"] == MEMBER
        ]
        returned_id = member_records[len(member_records) // 2]["id"] if member_records else None

        for record in meeting_records:
            plan = deals_by_key[record["deal_key"]]
            plans = [plan]
            companion = self._companion(record, plan)
            if companion is not None:
                plans.append(companion)
            returned = record["id"] == returned_id
            await self._meeting_report(
                f"meeting:{record['key']}",
                record=record,
                plans=plans,
                status_override=(
                    ("changes_requested", self.members[LEADER], at(self.base, 9))
                    if returned
                    else None
                ),
                review_note=(
                    "다음 액션의 기한이 없습니다. 팔로업 날짜를 적어 다시 올려 주세요."
                    if returned
                    else None
                ),
            )

        # 2) 일일 보고서. 월간 구간 시작일부터 어제까지, 활동이 있었던 평일만 쓴다.
        by_owner_day: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
        for record in self.activities:
            if record["day"] < self.base:
                by_owner_day[(record["owner"], record["day"])].append(record)

        for owner in (LEADER, MEMBER):
            for day in weekdays(period_start, self.base - timedelta(days=1)):
                records = by_owner_day.get((owner, day), [])
                if not records:
                    continue
                companies = sorted({r["contact"]["company_name"] for r in records})
                quoted = [
                    r for r in records if deals_by_key[r["deal_key"]]["quote_on"] is not None
                ]
                await self._period_report(
                    f"daily:{owner}:{day.isoformat()}",
                    author=owner,
                    kind="daily",
                    day=day,
                    title=f"{day_label(day)} 일일업무",
                    order=DAILY_ORDER,
                    values={
                        "오늘 한 일": f"{day_label(day)} 거래처 {len(companies)}곳을 방문해"
                        f" 미팅 {len(records)}건을 진행했습니다.",
                        "거래처별 결과": " ".join(
                            f"{r['contact']['company_name']}에서 {r['title']} 건을"
                            " 진행했습니다."
                            for r in records
                        ),
                        "미완료·문제": (
                            f"견적을 보낸 {len(quoted)}건의 회신이 아직 오지 않았습니다."
                            if quoted
                            else BLANK_SECTION
                        ),
                        "다음 업무": (
                            action(
                                "회신 없는 견적 팔로업",
                                ("담당", "본인"),
                                ("기한", day_label(day + timedelta(days=1))),
                                ("완료 기준", "회신 확보"),
                                ("상태", "요청"),
                            ),
                        ),
                    },
                    activity_ids=tuple(r["id"] for r in records),
                )

        # 3) 주간 보고서. 월간 구간 시작 주부터 지난주까지. 월간의 관련 보고서가 이걸 읽는다.
        for owner in (LEADER, MEMBER):
            for start in week_starts(
                week_start(period_start), week_start(self.base) - timedelta(days=7)
            ):
                end = start + timedelta(days=6)
                previous = [
                    r
                    for r in self.activities
                    if r["owner"] == owner
                    and start - timedelta(days=7) <= r["day"] < start
                    and r["day"] < self.base
                ]
                records = [
                    r
                    for r in self.activities
                    if r["owner"] == owner and start <= r["day"] <= end and r["day"] < self.base
                ]
                if not records:
                    continue
                companies = sorted({r["contact"]["company_name"] for r in records})
                gap = len(records) - len(previous)
                signed = [
                    p
                    for p in self.deals
                    if p["owner"] == owner and p["signed"] and start <= p["signed"] <= end
                ]
                await self._period_report(
                    f"weekly:{owner}:{start.isoformat()}",
                    author=owner,
                    kind="weekly",
                    day=end,
                    title=f"{day_label(start)} 주간업무",
                    period=(start, end),
                    order=WEEKLY_ORDER,
                    values={
                        "목표": "담당 거래처 방문과 진행 중인 견적의 회신 확보가 이번 주"
                        " 목표였습니다. 주간 수치 목표는 별도로 설정되어 있지 않습니다.",
                        "실적": f"{day_label(start)}부터 {day_label(end)}까지 방문"
                        f" {len(records)}건, 거래처 {len(companies)}곳을 진행했습니다."
                        f" 계약은 {len(signed)}건입니다."
                        f" 주요 거래처는 {', '.join(companies[:4])}입니다.",
                        "차이": (
                            f"지난주 {len(previous)}건 대비 방문이 {abs(gap)}건"
                            f" {'늘었습니다' if gap > 0 else '줄었습니다'}."
                            if gap
                            else f"지난주와 같은 {len(records)}건을 진행했습니다."
                        ),
                        "원인": "데모 이후 견적까지 이어진 건에 방문이 몰렸습니다."
                        " 개별 건의 지연 원인은 미확인입니다.",
                        "다음 주 조치": (
                            action(
                                "유효기간 남은 견적 우선 팔로업",
                                ("담당", "본인"),
                                ("기한", day_label(end + timedelta(days=5))),
                                ("완료 기준", "회신 확보"),
                                ("상태", "요청"),
                            ),
                            action(
                                "계약 검토 중인 건의 법무 회신 확인",
                                ("담당", "본인"),
                                ("기한", "미확인"),
                                ("완료 기준", "회신 수신"),
                                ("상태", "요청"),
                            ),
                        ),
                    },
                    activity_ids=tuple(r["id"] for r in records),
                )

        # 4) 월간 보고서. 지난 PERIOD_MONTHS 개월.
        for owner in (LEADER, MEMBER):
            for index in range(1, PERIOD_MONTHS + 1):
                start = add_months(month_start(self.base), -index)
                end = next_month(start) - timedelta(days=1)
                records = [
                    r for r in self.activities if r["owner"] == owner and start <= r["day"] <= end
                ]
                signed = [
                    p
                    for p in self.deals
                    if p["owner"] == owner and p["signed"] and start <= p["signed"] <= end
                ]
                total = sum(p["contract_amount"] for p in signed)
                await self._period_report(
                    f"monthly:{owner}:{start.isoformat()}",
                    author=owner,
                    kind="monthly",
                    day=end,
                    title=f"{start.year}년 {start.month}월 월간업무",
                    period=(start, end),
                    order=MONTHLY_ORDER,
                    values={
                        "성과": f"{start.year}년 {start.month}월 계약 {len(signed)}건,"
                        f" 계약금액 합계 {won(total)}입니다. 방문·미팅은 {len(records)}건을"
                        " 진행했습니다.",
                        "원인": (
                            "데모 이후 견적까지 2주 안에 이어진 건이 계약으로 연결됐습니다."
                            if signed
                            else "계약으로 연결된 건이 없습니다. 견적 단계에서 회신이 지연된"
                            " 것이 원인으로 보이며 개별 사유는 미확인입니다."
                        ),
                        "문제": "견적을 보낸 뒤 회신이 지연되는 건이 남아 있습니다."
                        " 경쟁사와 병행 검토 중인 곳이 있습니다.",
                        "개선안": "견적 발행 시 회신 기한을 함께 적어 팔로업 시점을 분명히"
                        " 하겠습니다. 구매부서 외에 사용 부서도 함께 접촉하겠습니다.",
                        "다음 달 계획": (
                            action(
                                "데모까지 끝난 건의 견적 마무리",
                                ("담당", "본인"),
                                ("기한", day_label(end + timedelta(days=15))),
                                ("완료 기준", "견적 발송"),
                                ("상태", "합의"),
                            ),
                            action(
                                "계약 종료 임박 거래처 갱신 협의 착수",
                                ("담당", "본인"),
                                ("기한", "미확인"),
                                ("완료 기준", "갱신 협의 개시"),
                                ("상태", "요청"),
                            ),
                        ),
                    },
                )

    async def seed_orders(self) -> None:
        """계약이 끝난 딜에만 발주를 단다.

        발주 목록 API 가 딜 단계의 phase_code='order' 를 강제하므로, 발주가 붙은 딜은
        반드시 발주 진행·납품 완료 단계에 있어야 화면에서 보인다.
        """
        in_progress = ("order_received", "dispatch_request_completed", "in_production",
                       "stock_received")
        sequence = 0
        for plan in self.deals:
            if plan["stage"] not in ORDER_STAGES:
                continue
            sequence += 1
            delivered = plan["stage"] == "order_delivered"
            signed = plan["signed"]
            ordered_on = signed + timedelta(days=3)
            if delivered:
                status = "delivered"
                receipt_on = ordered_on + timedelta(days=21)
            else:
                status = in_progress[pick(f"os:{plan['key']}", len(in_progress))]
                # 아직 진행 중인 발주의 입고 예정일은 앞으로다. 주간 밴드가 이 값을 센다.
                receipt_on = self.day(1 + pick(f"rc:{plan['key']}", 10))
            due_on = max(ordered_on + timedelta(days=21), receipt_on)

            order_id = sid("purchase_order", plan["key"])
            await upsert(
                self.db,
                PurchaseOrder,
                {
                    "id": order_id,
                    "team_id": TEAM_ID,
                    "order_no": f"MD-PO-{ordered_on.year}-{sequence:04d}",
                    "sales_deal_id": plan["id"],
                    "supplier_name": medion.SUPPLIERS[
                        pick(f"sup:{plan['key']}", len(medion.SUPPLIERS))
                    ],
                    "purchase_order_status_id": self.order_status[status],
                    "ordered_on": ordered_on,
                    "due_on": due_on,
                    "expected_receipt_on": receipt_on,
                    "request_department": "영업팀",
                    "cooperation_department": "생산팀",
                    "created_by_member_id": self.members[plan["owner"]],
                    "expected_customer_company_id": plan["contact"]["company_id"],
                    "memo": None,
                    "deleted_at": None,
                    "created_at": at(ordered_on, 10),
                    "updated_at": at(receipt_on if delivered else ordered_on, 15),
                },
            )
            await upsert(
                self.db,
                PurchaseOrderItem,
                {
                    "id": sid("purchase_order_item", plan["key"]),
                    "purchase_order_id": order_id,
                    "product_id": self.products[plan["model"]],
                    "quantity": plan["quantity"],
                    # 매입 단가. 판매가의 75% 라 발주 합계가 계약금액을 넘지 않는다.
                    "unit_price": plan["order_amount"] // plan["quantity"],
                    "position": 0,
                },
            )
            self.bump("purchase_order")
            self.bump(f"order_{status}")

    # ------------------------------------------------------------ C/S

    async def seed_supports(self) -> None:
        """불만은 반드시 딜에 붙는다. 복합 외래키라 딜과 고객사 짝이 맞아야 한다."""
        eligible = [
            p
            for p in self.deals
            if p["rich"] and self.phases[p["stage"]] in ("contract", "order", "closed")
        ]
        for index, seed in enumerate(medion.SUPPORTS):
            pool = [p for p in eligible if p["owner"] == seed.owner] or eligible
            plan = pool[index % len(pool)]
            occurred = self.day(seed.occurred_offset)
            request_id = sid("support_request", seed.key)
            await upsert(
                self.db,
                SupportRequest,
                {
                    "id": request_id,
                    "team_id": TEAM_ID,
                    "customer_company_id": plan["contact"]["company_id"],
                    "sales_deal_id": plan["id"],
                    "assignee_member_id": self.members[seed.owner],
                    "title": f"{plan['contact']['company_name']} {seed.title}",
                    "body": seed.body,
                    "is_urgent": seed.is_urgent,
                    "status_code": seed.status_code,
                    "occurred_at": at(occurred, 11),
                    "registered_at": at(occurred, 13),
                    "updated_at": at(occurred + timedelta(days=1), 10),
                },
            )
            self.bump("support_request")
            self.bump(f"support_{seed.status_code}")
            for position, body in enumerate(seed.responses):
                await upsert(
                    self.db,
                    SupportResponse,
                    {
                        "id": sid("support_response", f"{seed.key}:{position}"),
                        "support_request_id": request_id,
                        "responder_member_id": self.members[seed.owner],
                        "body": body,
                        "responded_at": at(occurred + timedelta(days=position + 1), 14),
                    },
                )
                self.bump("support_response")

    # ------------------------------------------------------------ 매출 목표

    async def seed_targets(self) -> None:
        """담당자별 월 목표. 회사별 목표는 넣지 않는다.

        팀 관리 화면은 customer_company_id 가 비어 있는 행만 합산하고 대시보드는 전부
        합산한다. 회사별 목표를 섞으면 두 화면이 다른 숫자를 말한다.
        """
        actual: dict[tuple[str, date], int] = defaultdict(int)
        for plan in self.deals:
            if plan["signed"] and self.stages[plan["stage"]][1] == "confirmed":
                actual[(plan["owner"], month_start(plan["signed"]))] += plan["contract_amount"]

        for owner in (LEADER, MEMBER):
            for index in range(12, -1, -1):
                month = add_months(month_start(self.base), -index)
                key = f"{owner}:{month.isoformat()}"
                # 과거 한 달만 일부러 비워 '목표 미설정' 상태를 시연한다.
                # 이번 달은 반드시 채운다. 대시보드 카드가 비면 안 된다.
                if owner == MEMBER and index == 5:
                    continue
                hit = actual.get((owner, month), 0)
                if hit == 0:
                    amount = 30_000_000
                else:
                    # 80~125%. 목표를 넘긴 달과 못 미친 달이 모두 나온다.
                    amount = hit * (80 + pick(f"tg:{key}", 46)) // 100
                await upsert(
                    self.db,
                    SalesTarget,
                    {
                        "id": sid("sales_target", key),
                        "owner_member_id": self.members[owner],
                        "customer_company_id": None,
                        "target_month": month,
                        "target_amount": amount // 100_000 * 100_000,
                    },
                )
                self.bump("sales_target")

    # ------------------------------------------------------------ 공지

    async def seed_notices(self) -> None:
        for position, seed in enumerate(medion.NOTICES):
            starts = self.day(seed.starts_offset)
            notice_id = sid("notice", seed.key)
            due = self.day(seed.due_offset) if seed.due_offset is not None else None
            await upsert(
                self.db,
                Notice,
                {
                    "id": notice_id,
                    "team_id": TEAM_ID,
                    "author_member_id": self.members[LEADER],
                    "type": seed.type,
                    "tag": seed.tag or None,
                    "title": seed.title,
                    "body": seed.body,
                    "image_storage_key": None,
                    "image_alt": None,
                    "published_at": at(starts, 9),
                    "due_at": at(due, 18) if due else None,
                    "due_text": f"{due.month}월 {due.day}일까지" if due else None,
                    # 게시 시작일이 오늘보다 뒤면 대시보드 티커에 뜨지 않는다.
                    "display_start_date": starts,
                    "display_end_date": None,
                    "is_hidden": False,
                    "sort_order": position,
                    "updated_at": at(starts, 9),
                    "deleted_at": None,
                },
            )
            self.bump("notice")
            self.bump(f"notice_{seed.type.lower()}")
            if seed.type != "DIRECTIVE":
                continue
            # 수신자가 없으면 팀장에게도 팀원에게도 보이지 않는다.
            changed = (
                None
                if seed.target_status == "pending"
                else at(self.day(seed.starts_offset + 2), 10)
            )
            await self.db.execute(
                insert(NoticeTarget)
                .values(
                    notice_id=notice_id,
                    member_id=self.members[MEMBER],
                    created_at=at(starts, 9),
                    status_code=seed.target_status,
                    status_reason=seed.target_reason,
                    status_changed_at=changed,
                    status_changed_by_member_id=self.members[MEMBER] if changed else None,
                )
                .on_conflict_do_update(
                    index_elements=[NoticeTarget.notice_id, NoticeTarget.member_id],
                    set_={
                        "status_code": seed.target_status,
                        "status_reason": seed.target_reason,
                        "status_changed_at": changed,
                        "status_changed_by_member_id": self.members[MEMBER] if changed else None,
                    },
                )
            )
            self.bump("notice_target")

    # ------------------------------------------------------------ 실행

    async def run(self) -> None:
        await self.load_configuration()
        await self.seed_products()
        await self.seed_companies()
        await self.seed_contacts()
        self.plan_deals()
        await self.seed_deals()
        await self.seed_activities()
        await self.seed_reports()
        await self.seed_orders()
        await self.seed_supports()
        await self.seed_targets()
        await self.seed_notices()


# ---------------------------------------------------------------- 리셋

# 삭제는 생성의 역순이다. 자식이 먼저 사라져야 부모를 지울 수 있다.
# 팀·구성원·룩업·파이프라인은 남긴다. 계정은 고정 자산이고, 룩업을 지우면 남은 행이
# 참조할 대상이 사라진다. 조건은 전부 이 팀을 가리킨다 — 다른 팀은 어느 경로로도 안 걸린다.
RESET_ORDER: tuple[tuple[Any, str], ...] = (
    (File, "file"),
    (Document, "document"),
    (ContractNextMeetingSuggestion, "contract_next_meeting_suggestion"),
    (ReportSubmission, "report_submission"),
    (Report, "report"),
    (AgentRun, "agent_run"),
    (SalesTarget, "sales_target"),
    (NoticeImage, "notice_image"),
    (Notice, "notice"),
    (SupportRequestEditBackup, "support_request_edit_backup"),
    (SupportResponse, "support_response"),
    (SupportRequest, "support_request"),
    (Activity, "activity"),
    (PurchaseOrder, "purchase_order"),
    (SalesDeal, "sales_deal"),
    (CustomerContact, "customer_contact"),
    (CustomerCompany, "customer_company"),
    (Product, "product"),
)


def _reset_scope(model: Any) -> Any:
    """모델마다 이 팀의 행을 고르는 조건. team_id 가 없는 표는 부모를 타고 간다."""
    team_reports = select(Report.id).where(Report.team_id == TEAM_ID)
    team_documents = select(Document.id).where(Document.team_id == TEAM_ID)
    if model is File:
        return model.report_id.in_(team_reports) | model.document_id.in_(team_documents)
    if model is ContractNextMeetingSuggestion:
        return model.sales_deal_id.in_(select(SalesDeal.id).where(SalesDeal.team_id == TEAM_ID))
    if model is SalesTarget:
        # 팀 전체가 아니라 두 데모 계정만. 같은 팀의 다른 사람이 세워 둔 목표는 남긴다.
        return model.owner_member_id.in_(
            select(Member.id).where(Member.team_id == TEAM_ID, Member.email.in_(medion.EMAILS))
        )
    if model is SupportResponse:
        return model.support_request_id.in_(
            select(SupportRequest.id).where(SupportRequest.team_id == TEAM_ID)
        )
    if model is SupportRequestEditBackup:
        return model.support_request_id.in_(
            select(SupportRequest.id).where(SupportRequest.team_id == TEAM_ID)
        )
    if model is CustomerContact:
        return model.company_id.in_(
            select(CustomerCompany.id).where(CustomerCompany.team_id == TEAM_ID)
        )
    return model.team_id == TEAM_ID


async def reset_demo_data(db: AsyncSession) -> dict[str, int]:
    """이 데모 팀이 소유한 행만 지운다."""
    # 보고서에 붙은 첨부는 트리거가 DELETE 와 UPDATE 를 모두 막는다. 미리 확인해
    # 보고서를 지우려다 트랜잭션 한복판에서 터지는 일을 없앤다.
    blocked = (
        await db.execute(
            select(ReportAttachment.id).where(
                ReportAttachment.team_id == TEAM_ID, ReportAttachment.report_id.is_not(None)
            )
        )
    ).scalars().all()
    if blocked:
        raise SystemExit(
            "보고서에 귀속된 첨부가 있어 초기화할 수 없습니다.\n"
            "report_attachment_immutable 트리거가 삭제를 막습니다. 해당 id:\n  "
            + "\n  ".join(str(i) for i in blocked)
        )

    removed: dict[str, int] = {}
    # 아직 보고서에 붙지 않은 첨부는 지울 수 있다.
    result = await db.execute(
        delete(ReportAttachment).where(
            ReportAttachment.team_id == TEAM_ID, ReportAttachment.report_id.is_(None)
        )
    )
    if result.rowcount:
        removed["report_attachment"] = result.rowcount

    for model, label in RESET_ORDER:
        result = await db.execute(delete(model).where(_reset_scope(model)))
        if result.rowcount:
            removed[label] = result.rowcount
    return removed


# ---------------------------------------------------------------- 진입점


class _DryRun(Exception):
    """트랜잭션을 되돌리려고 일부러 던진다."""


def parse_base_date(raw: str | None) -> date:
    if raw is None:
        return datetime.now(SEOUL).date()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise SystemExit(f"--base-date 형식이 YYYY-MM-DD 가 아닙니다: {raw}") from None


def confirm(base: date, *, reset: bool) -> None:
    """무엇을 어디에 쓰는지 보여주고 사람에게 확인받는다."""
    print("대상")
    print(f"  DB        {masked_target()}")
    print(f"  APP_ENV   {settings.app_env}")
    print(f"  팀        {TEAM_NAME}  (team_id={TEAM_ID})")
    for seed in medion.MEMBERS:
        print(f"  계정      {seed.email}  ({seed.role_code})")
    print(f"  기준일    {base.isoformat()}")
    if reset:
        print("  초기화    위 팀이 소유한 행만 지웁니다. 다른 팀은 건드리지 않습니다.")
        answer = input("계속하려면 팀 이름을 그대로 입력하세요: ").strip()
        if answer != TEAM_NAME:
            raise SystemExit("입력이 팀 이름과 달라 중단합니다.")


async def run(
    *, base: date, reset: bool, seed: bool, verify: bool, dry_run: bool
) -> None:
    if settings.app_env == "production":
        raise SystemExit("운영 환경에서는 실행할 수 없습니다. APP_ENV 를 확인해 주세요.")

    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as db, db.begin():
            await ensure_team(db)
            member_ids = await resolve_accounts(db)

            if reset:
                removed = await reset_demo_data(db)
                total = sum(removed.values())
                print(f"reset: {total}건 삭제" + (f" {dict(removed)}" if removed else ""))

            if seed:
                # 팀별 룩업과 파이프라인. 이미 있으면 그대로 둔다.
                await seed_team_configuration(db, TEAM_ID)
                await db.flush()
                seeder = Seeder(db, base, member_ids)
                await seeder.run()
                print("seed:")
                for label in sorted(seeder.counts):
                    print(f"  {label:<32} {seeder.counts[label]:>6}")

            if dry_run:
                raise _DryRun
    except _DryRun:
        print("dry-run: 아무것도 저장하지 않고 되돌렸습니다.")
        return

    if verify and not dry_run:
        from scripts.verify_demo_medion import run as verify_run

        async with sessionmaker() as db:
            failures = await verify_run(db, base)
        if failures:
            raise SystemExit(f"검증 실패 {failures}건")


def main() -> None:
    parser = argparse.ArgumentParser(description="메디온 의료기기 영업팀 데모 데이터 시더")
    parser.add_argument("--base-date", help="기준일 YYYY-MM-DD. 기본값은 실행일입니다.")
    parser.add_argument("--reset", action="store_true", help="이 팀의 행을 지웁니다.")
    parser.add_argument("--seed", action="store_true", help="데이터를 넣습니다.")
    parser.add_argument("--verify", action="store_true", help="검증만 돌립니다.")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 되돌립니다.")
    parser.add_argument("--yes", action="store_true", help="확인 입력을 건너뜁니다.")
    args = parser.parse_args()

    # 아무 단계도 고르지 않으면 셋 다 한다.
    reset, seed, verify = args.reset, args.seed, args.verify
    if not (reset or seed or verify):
        reset = seed = verify = True

    base = parse_base_date(args.base_date)
    if args.base_date and seed and not reset:
        raise SystemExit(
            "--base-date 를 옮길 때는 --reset 이 함께 필요합니다.\n"
            "날짜 축만 옮기면 계약일·발주일·보고서 상태가 서로 어긋납니다."
        )

    if not args.yes and not args.dry_run and sys.stdin.isatty():
        confirm(base, reset=reset)
    else:
        confirm(base, reset=False)

    asyncio.run(run(base=base, reset=reset, seed=seed, verify=verify, dry_run=args.dry_run))


if __name__ == "__main__":
    main()

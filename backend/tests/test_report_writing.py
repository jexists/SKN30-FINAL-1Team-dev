import json
import os

import pytest

from app.agents import report_writing
from app.core.config import settings

LIVE_TEMPLATE = {
    "fields": [
        {"id": "attendees", "label": "참석자"},
        {"id": "reaction", "label": "고객 반응"},
        {"id": "decision", "label": "결정 사항"},
        {"id": "next", "label": "후속 조치"},
    ]
}


@pytest.mark.anyio
async def test_run_uses_report_prompt_and_input(monkeypatch):
    captured = {}

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return report_writing.ReportDraftOutput(
            fields=[report_writing.ReportDraftField(field_id="summary", value="미팅 초안")],
            summary="초안",
        )

    monkeypatch.setattr(report_writing, "generate_structured", fake_generate_structured)

    output = await report_writing.run(
        {
            "report_kind": "meeting",
            "report_date": "2026-08-21",
            "template_snapshot": {"fields": [{"id": "summary", "label": "미팅 요약"}]},
            "content": {"summary": ""},
            "transcript": "고객이 다음 주에 견적서를 요청했다.",
            "guidance": None,
        }
    )

    assert output.summary == "초안"
    assert output.fields[0].field_id == "summary"
    assert captured["instructions"] == report_writing.SYSTEM_PROMPT
    assert (
        '보고서 양식(JSON): {"fields":[{"id":"summary","label":"미팅 요약"}]}'
        in captured["input_text"]
    )
    assert '현재 작성값(JSON): {"summary":""}' in captured["input_text"]
    assert "미팅 기록: 고객이 다음 주에 견적서를 요청했다." in captured["input_text"]
    assert captured["schema"] is report_writing.ReportDraftOutput
    assert captured["schema_name"] == "report_draft"


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_SMOKE") != "1",
    reason="RUN_LLM_SMOKE=1일 때만 실제 API를 호출합니다.",
)
@pytest.mark.anyio
async def test_live_run_prints_real_report():
    assert settings.llm_configured, "LLM_API_URL, LLM_API_KEY, LLM_MODEL 설정이 필요합니다."

    output = await report_writing.run(
        {
            "report_kind": "meeting",
            "report_date": "2026-08-21",
            "template_snapshot": LIVE_TEMPLATE,
            "content": {"values": {field["id"]: "" for field in LIVE_TEMPLATE["fields"]}},
            "transcript": (
                "합성 테스트 미팅입니다. 영업 담당자 박민수와 고객 담당자 김영희가 참석했습니다. "
                "고객은 제품 도입에 긍정적이며 견적서를 검토하기로 했습니다. "
                "다음 주 수요일까지 견적서를 전달하고 후속 미팅을 잡기로 했습니다."
            ),
            "guidance": None,
        }
    )

    print("\n[실제 LLM 응답]")
    print(json.dumps(output.model_dump(), ensure_ascii=False, indent=2))

    expected_ids = {field["id"] for field in LIVE_TEMPLATE["fields"]}
    actual_ids = [field.field_id for field in output.fields]
    assert len(actual_ids) == len(set(actual_ids)), f"중복 field_id가 있습니다: {actual_ids}"
    assert set(actual_ids) == expected_ids, f"field_id가 양식과 다릅니다: {actual_ids}"
    assert output.summary.strip()
    print("[성공] 실제 LLM 보고서 검증 통과")

"""기간 보고서의 소스 경계와 단일 작성·검토·수정 실행을 검사한다."""

import asyncio
import copy
import json
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_report_writing_deep import effective_instructions, scripted

from app.agents.meeting import content, features
from app.agents.reports import harness, period, period_sources
from app.schemas.report_drafts import ReportDraftOutput
from app.schemas.reports import REPORT_BODY_MAX_LENGTH
from app.services.llm import LLMError, LLMNotConfigured

MEETING_A = UUID(int=101)
MEETING_B = UUID(int=102)


def sample():
    reports = [
        {
            "id": str(UUID(int=200 + index)),
            "submission_id": str(meeting_id),
            "report_kind": "meeting",
            "sales_deal_id": str(UUID(int=300 + index)),
            "source_activity_id": str(meeting_id),
            "report_date": "2026-08-31",
            "title": title,
            "values": {"body": body},
        }
        for index, (meeting_id, title, body) in enumerate(
            [
                (MEETING_A, "합성회사 A · 보안 제품", "보안 승인 후 예산을 검토할 예정이다."),
                (MEETING_A, "합성회사 A · 운영 제품", "가격 비교 자료를 요청했다."),
                (MEETING_B, "합성회사 B · 분석 제품", "기술팀 검토 중이며 도입은 미확정이다."),
            ],
            1,
        )
    ]
    return {
        "report_kind": "daily",
        "report_date": "2026-08-31",
        "template_snapshot": {
            "id": "builtin-daily-freeform",
            "name": "일일보고서",
            "fields": [
                {
                    "id": "body",
                    "label": "보고서 본문",
                    "type": "textarea",
                    "required": True,
                    "aiFilled": True,
                }
            ],
        },
        "content": {
            "values": {"body": "사용자가 작성하던 메모"},
            "activities": [],
            "attachments": [],
        },
        "transcript": "추가 메모: 자료 요청을 구매 확정으로 쓰지 말 것.",
        "guidance": "조건과 미확정 사항을 보존해주세요.",
        "report_sources": {
            "reports": reports,
            "meetings": [
                {
                    "activity_id": str(MEETING_A),
                    "submission_id": str(MEETING_A),
                    "common_report": {"body": "합성회사 A의 구매팀과 미팅했다."},
                    "unassigned_report": {
                        "body": "딜 미지정 · 확인 필요: ‘그것도 보내주세요.’의 대상은 불명확하다."
                    },
                },
                {
                    "activity_id": str(MEETING_B),
                    "submission_id": str(MEETING_B),
                    "common_report": {"body": "합성회사 B의 기술팀과 온라인으로 만났다."},
                    "unassigned_report": None,
                },
            ],
        },
    }


def draft():
    return {
        "fields": [
            {
                "field_id": "body",
                "value": "합성회사 A의 구매팀과 미팅했습니다. 보안 제품은 보안 승인 후 예산을 "
                "검토할 예정이며, 운영 제품은 가격 비교 자료를 요청했습니다. 추가 자료 요청은 "
                "대상 딜 확인이 필요합니다.\n\n"
                "합성회사 B의 기술팀과 온라인으로 만났습니다. 분석 제품은 기술팀 검토 중이며 "
                "도입은 아직 확정되지 않았습니다.",
            }
        ]
    }


def period_sample(kind: str):
    source = sample()
    monthly = kind == "monthly"
    source.update(
        report_kind=kind,
        report_date="2026-08-31" if monthly else "2026-09-06",
        period_start="2026-08-01" if monthly else "2026-08-31",
        period_end="2026-08-31" if monthly else "2026-09-06",
        transcript=None,
    )
    source["report_sources"] = {
        "reports": [
            {
                "id": str(UUID(int=501 + index)),
                "submission_id": str(UUID(int=601 + index)),
                "report_kind": "weekly" if monthly else "daily",
                "report_date": "2026-08-31",
                "period_start": "2026-08-31" if monthly else None,
                "period_end": "2026-09-06" if monthly else None,
                "values": {"body": f"확정 하위 본문 {index}: 8월 31일 검토, 9월 2일 계획"},
            }
            for index in range(2)
        ],
        "meetings": [],
        "activities": [],
    }
    return source


def test_source_units_keep_each_meeting_boundary_and_shared_notes():
    units = period_sources.source_units(period_sources.build_source(sample()))

    assert [unit["source_type"] for unit in units] == ["meeting_bundle", "meeting_bundle"]
    first = units[0]["content"]
    assert len(first["deal_reports"]) == 2
    assert first["meeting_context"][0]["common_report"]["body"].startswith("합성회사 A")
    assert "딜 미지정" in first["meeting_context"][0]["unassigned_report"]["body"]


def test_preparation_digest_preserves_assigned_source_boundary():
    unit = harness.WorkUnit(
        work_unit_id="prepare-meeting-1",
        scope="meeting_bundle:1",
        schema=period.PeriodSourceDigest,
        locations=frozenset({"meeting_bundle:1"}),
        evidence_refs=frozenset({"meeting_bundle:1"}),
        output_shape="PeriodSourceDigest",
    )
    digest = period.PeriodSourceDigest(
        source_id="meeting_bundle:1",
        report_kind="daily",
        facts=[
            {
                "kind": "fact",
                "content": "검토 중",
                "source_id": "meeting_bundle:1",
                "evidence_ref": "meeting_bundle:1",
            }
        ],
        evidence_refs=["meeting_bundle:1"],
    )
    period._validate_unit(unit, digest, None, unit.locations)
    with pytest.raises(PermissionError, match="report_source_not_allowed"):
        period._validate_unit(
            unit,
            period.PeriodSourceDigest.model_validate({
                **digest.model_dump(),
                "facts": [{**digest.facts[0].model_dump(), "source_id": "meeting_bundle:2"}],
            }),
            None,
            unit.locations,
        )


@pytest.mark.parametrize("kind", ["weekly", "monthly"])
def test_weekly_monthly_use_only_child_submissions(kind):
    units = period_sources.source_units(period_sources.build_source(period_sample(kind)))
    assert len(units) == 2
    assert all(unit["source_type"] == "child_submission" for unit in units)
    assert len(units[0]["content"]["reports"]) == 1
    assert "meeting_context" not in str(units)


def test_validated_activity_and_attachment_are_factual_units():
    source = sample()
    source["report_sources"] = {
        "reports": [],
        "meetings": [],
        "activities": [{"id": "activity-1", "source": "캘린더", "title": "확정 활동"}],
    }
    source["content"]["attachments"] = [
        {"id": "forged", "name": "forged.pdf", "state": "done", "extract": "클라이언트 값"}
    ]
    source["attachments"] = [
        {
            "id": "file-1",
            "kind": "pdf",
            "name": "evidence.pdf",
            "byte_size": 123,
            "extract": "서버 첨부 근거",
        }
    ]

    units = period_sources.source_units(period_sources.build_source(source))

    assert [unit["source_type"] for unit in units] == ["direct_activity", "attachment"]
    assert "서버 첨부 근거" in str(units)
    assert "클라이언트 값" not in str(units)


def test_calendar_wrappers_and_navigation_are_excluded_from_period_input():
    source = sample()
    source["content"]["activities"] = [
        {"source": "캘린더", "included": True, "title": "오래된 화면 값"}
    ]
    source["report_sources"]["activities"] = [
        {"id": "activity-1", "source": "캘린더", "title": "DB 확정 값"}
    ]
    assert (
        period_sources.build_source(source)["activities"] == source["report_sources"]["activities"]
    )
    assert "오래된 화면 값" not in str(period_sources.build_source(source))


def test_summary_is_not_part_of_period_output_contract():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ReportDraftOutput.model_validate({**draft(), "summary": "중복 요약"})


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
def test_period_uses_frozen_submissions_directly_and_preserves_output(monkeypatch, kind):
    source = sample() if kind == "daily" else period_sample(kind)
    original = copy.deepcopy(source)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Period must bypass meeting analysis")

    monkeypatch.setattr(content, "run", forbidden)
    monkeypatch.setattr(features, "run_for_deals", forbidden)
    seen = scripted(monkeypatch, [draft(), {"issues": []}])
    output = asyncio.run(period.run(source))
    assert output.model_dump() == draft()
    assert source == original
    assert len(seen) == 2
    payload = json.loads(seen[0]["input_text"])
    expected = period_sources.build_source(source)
    assert payload == {
        "run_context": period_sources.run_context(expected),
        "source_units": period_sources.source_units(expected),
    }
    assert json.loads(seen[1]["input_text"])["source"] == payload
    for call in seen:
        assert f"/skills/{period.PERIOD_WRITER_ROLES[kind]}/SKILL.md" in harness.skill_files(
            call["skill_role"]
        )
        assert period.GUIDANCE_CONTRACT in effective_instructions(call)
        assert call["role"] in {period.PERIOD_WRITER_ROLES[kind], harness.REVIEWER_ROLE}
    assert seen[0]["schema"] is ReportDraftOutput
    assert seen[1]["schema"] is harness.ReportReview


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
def test_feedback_triggers_exactly_one_repair_and_no_final_llm_call(monkeypatch, kind):
    repaired = {"fields": [{"field_id": "body", "value": "보안 승인 후 예산 검토 예정입니다."}]}
    seen = scripted(
        monkeypatch, [draft(), {"issues": ["fields[0].value: 조건을 복원하라."]}, repaired]
    )
    assert (
        asyncio.run(period.run(sample() if kind == "daily" else period_sample(kind))).model_dump()
        == repaired
    )
    assert len(seen) == 3
    assert sum(call["schema"] is harness.ReportReview for call in seen) == 1
    repair = json.loads(seen[2]["input_text"])
    assert repair["draft"] == draft()
    assert repair["source"] == json.loads(seen[0]["input_text"])


@pytest.mark.parametrize(
    "kind,label",
    [
        ("daily", "다음 업무"),
        ("weekly", "다음 주 조치"),
        ("monthly", "다음 달 계획"),
    ],
)
def test_period_action_tail_keeps_bullets_and_narrative_rules_through_repair(
    monkeypatch, kind, label
):
    body = (
        f"**성과**\n\n이번 기간 결과를 확인했습니다.\n\n**{label}**\n\n"
        "- 제안 | 보안 체크리스트 전달 | 담당: 본인 | 기한: 다음 주(기준일 미확인) | "
        "완료 기준: 전달 확인 | 조건: 고객 승인 후"
    )
    response = {"fields": [{"field_id": "body", "value": body}]}
    source = sample() if kind == "daily" else period_sample(kind)
    seen = scripted(
        monkeypatch,
        [response, {"issues": ["fields[0].value: 조건을 보존하라."]}, response],
    )

    result = asyncio.run(period.run(source))

    assert len(seen) == 3
    for call in seen:
        instructions = effective_instructions(call)
        assert label in instructions
        assert "마지막 섹션" in instructions
        assert "한 항목당" in instructions
        assert "핵심어 중심의 Markdown 순서 없는 목록" in instructions
        assert "합니다체" in instructions
        assert "담당자·기한·완료 기준" in instructions
        assert f"- {label} 미확인" in instructions
    assert seen[1]["role"] == harness.REVIEWER_ROLE
    assert result.fields[0].value == body
    assert result.fields[0].value.split(f"**{label}**\n\n", 1)[1].startswith("- ")
    assert "담당: 본인" in result.fields[0].value
    assert "기한: 다음 주(기준일 미확인)" in result.fields[0].value
    assert "조건: 고객 승인 후" in result.fields[0].value


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
def test_period_payload_preserves_subreports_attachment_extract_and_guidance_through_repair(
    monkeypatch, kind
):
    source = sample() if kind == "daily" else period_sample(kind)
    source["guidance"] = (
        f"{kind} 추가 결정사항: 가격 검토는 미확정입니다. 후속조치 담당과 기한은 확인 필요합니다."
    )
    source["attachments"] = [
        {
            "id": f"attachment-{kind}",
            "name": f"{kind}.pdf",
            "extract": f"{kind} 첨부 추출문: 고객의 추가 요청",
        }
    ]
    expected = period_sources.build_source(source)
    expected_payload = {
        "run_context": period_sources.run_context(expected),
        "source_units": period_sources.source_units(expected),
    }
    seen = scripted(monkeypatch, [draft(), {"issues": ["후속조치를 반영하라."]}, draft()])

    asyncio.run(period.run(source))

    assert len(seen) == 3
    for call in seen:
        payload = json.loads(call["input_text"])
        frozen = payload.get("source", payload)
        assert frozen == expected_payload
        assert frozen["run_context"]["guidance"] == source["guidance"]
        assert any(
            unit["source_type"] == ("meeting_bundle" if kind == "daily" else "child_submission")
            for unit in frozen["source_units"]
        )
        attachment_units = [
            unit for unit in frozen["source_units"] if unit["source_type"] == "attachment"
        ]
        assert (
            attachment_units[0]["content"]["attachment"]["extract"]
            == source["attachments"][0]["extract"]
        )


@pytest.mark.parametrize("stage", ["review", "repair"])
@pytest.mark.parametrize(
    "failure",
    [
        None,
        {},
        {"issues": [""]},
        RuntimeError("private-detail"),
        TimeoutError(),
        LLMError("llm_provider_error:429"),
        LLMError("llm_provider_error:503"),
        LLMError("llm_request_failed:ReadTimeout"),
        LLMError("llm_response_not_json"),
    ],
)
def test_review_and_repair_failure_keeps_draft(monkeypatch, caplog, stage, failure):
    events = []
    monkeypatch.setattr(period, "log_agent_event", lambda *args, **kwargs: events.append(kwargs))
    responses = [draft()]
    if stage == "repair":
        responses.append({"issues": ["조건을 보존하라."]})
    seen = scripted(monkeypatch, [*responses, failure])
    assert asyncio.run(period.run(sample())).model_dump() == draft()
    assert len(seen) == (2 if stage == "review" else 3)
    assert events[-1]["call_count"] == len(seen)
    assert events[-1]["semantic_review_count"] == 1
    assert events[-1]["repair_count"] == int(stage == "repair")
    assert '"outcome": "degraded"' in caplog.text
    assert "valid_draft_fallback" in caplog.text
    assert "private-detail" not in caplog.text


@pytest.mark.parametrize(
    "invalid",
    [
        {"fields": [{"field_id": "wrong", "value": "내용"}]},
        {"fields": [{"field_id": "body", "value": "   "}]},
        {"fields": [{"field_id": "body", "value": "가" * 5001}]},
        {"fields": [{"field_id": "body", "value": "내용"}] * 2},
    ],
)
def test_malformed_repair_preserves_draft_but_invalid_initial_output_fails(monkeypatch, invalid):
    seen = scripted(monkeypatch, [draft(), {"issues": ["조건을 복원하라."]}, invalid])
    assert asyncio.run(period.run(sample())).model_dump() == draft()
    assert len(seen) == 3
    scripted(monkeypatch, [invalid])
    with pytest.raises(LLMError):
        asyncio.run(period.run(sample()))


@pytest.mark.parametrize("stage", ["review", "repair"])
@pytest.mark.parametrize(
    "failure",
    [
        asyncio.CancelledError(),
        ValueError("input_invalid"),
        PermissionError("owner_invalid"),
        LLMError("period_report_sources_invalid"),
        LLMNotConfigured("llm_not_configured"),
        LLMError("report_agent_unsupported_endpoint"),
        LLMError("llm_provider_error:401"),
        LLMError("llm_provider_error:403"),
    ],
)
def test_cancellation_and_input_errors_after_draft_are_never_fallback(monkeypatch, stage, failure):
    events = []
    monkeypatch.setattr(period, "log_agent_event", lambda *args, **kwargs: events.append(kwargs))
    responses = [draft()]
    if stage == "repair":
        responses.append({"issues": ["조건을 복원하라."]})
    seen = scripted(monkeypatch, [*responses, failure])
    with pytest.raises(type(failure)) as caught:
        asyncio.run(period.run(sample()))
    assert caught.value is failure
    assert events[-1]["outcome"] == "failed"
    assert len(seen) == len(responses) + 1


def test_current_body_and_guidance_survive_without_selected_reports(monkeypatch):
    source = sample()
    source["report_sources"] = {"reports": [], "meetings": [], "activities": []}
    seen = scripted(monkeypatch, [draft(), {"issues": []}])
    asyncio.run(period.run(source))
    payload = json.loads(seen[0]["input_text"])
    assert payload["source_units"] == []
    assert payload["run_context"]["current_body"] == source["content"]["values"]["body"]
    assert payload["run_context"]["transcript"] == source["transcript"]
    assert payload["run_context"]["guidance"] == source["guidance"]


def test_meeting_bundle_keeps_multiple_maximum_length_bodies():
    source = sample()
    reports = source["report_sources"]["reports"][:2]
    for report in reports:
        report["values"]["body"] = "가" * REPORT_BODY_MAX_LENGTH
    units = period_sources.source_units(period_sources.build_source(source))
    assert units[0]["content"]["deal_reports"] == reports
    assert len(json.dumps(units[0], ensure_ascii=False)) > 60_000


def test_worker_packing_does_not_repeat_the_api_source_count_limit():
    source = sample()
    # 선택 개수는 API가 검사한다. worker의 자료 포장은 별도 개수 한도를 추가하지 않는다.
    activities = [{"id": str(index), "title": "확정 활동"} for index in range(129)]
    source["report_sources"] = {
        "reports": [],
        "meetings": [],
        "activities": activities,
    }
    units = period_sources.source_units(period_sources.build_source(source))
    assert [unit["content"]["activity"] for unit in units] == activities
    assert units[-1]["source_id"] == "direct_activity:129"


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update(report_kind="meeting"), "period_report_kind_invalid"),
        (
            lambda value: value["template_snapshot"].update(fields=[]),
            "period_report_template_invalid",
        ),
        (
            lambda value: value["content"]["values"].update(summary="구형 요약"),
            "period_report_values_invalid",
        ),
        (lambda value: value.update(report_sources=[]), "period_report_sources_invalid"),
    ],
)
def test_invalid_input_rejected_before_generation(monkeypatch, mutation, error):
    source = sample()
    mutation(source)
    seen = scripted(monkeypatch, [])
    with pytest.raises(LLMError, match=error):
        asyncio.run(period.run(source))
    assert seen == []


@pytest.mark.parametrize("kind", ["weekly", "monthly"])
def test_period_rejects_grandchild_meeting_payload_before_any_model_call(monkeypatch, kind):
    source = period_sample(kind)
    source["report_sources"]["meetings"] = sample()["report_sources"]["meetings"]
    calls = scripted(monkeypatch, [])
    with pytest.raises(LLMError, match="period_report_sources_invalid"):
        asyncio.run(period.run(source))
    assert calls == []


def test_monthly_writer_review_and_repair_keep_period_and_heading_rules(monkeypatch):
    source = period_sample("monthly")
    calls = scripted(monkeypatch, [draft(), {"issues": ["월 밖 집계를 제거하라."]}, draft()])
    asyncio.run(period.run(source))
    for call in calls:
        assert "월경계 주간" in effective_instructions(call)
        assert "비례 배분하지 않" in effective_instructions(call)
        assert "굵은 소제목" in effective_instructions(call)
        assert "독립된 한 줄" in effective_instructions(call)
        assert "빈 줄 뒤" in effective_instructions(call)
        payload = json.loads(call["input_text"])
        frozen = payload.get("source", payload)
        assert frozen["run_context"]["period_end"] == "2026-08-31"
        child = frozen["source_units"][0]["content"]["reports"][0]
        assert child["period_end"] == "2026-09-06"
        assert "9월 2일" in child["values"]["body"]

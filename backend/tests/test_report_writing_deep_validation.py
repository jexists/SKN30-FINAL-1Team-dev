import hashlib
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from app.agents import report_writing_deep as agent
from app.services.llm import LLMError, LLMNotConfigured

DEAL_A, DEAL_B, OTHER_DEAL = (UUID(int=value) for value in (1, 2, 3))


def _case(*, unassigned=True):
    rows = [
        ("담당자 두 명이 참석했다.", "meeting_context", []),
        ("회사는 물류센터를 운영한다.", "company_context", []),
        ("두 딜 모두 보안 검토가 필요하다.", "all_selected_deals", []),
        ("A 장비의 견적만 요청했다.", "deal", [DEAL_A]),
        ("B 서비스 예산은 미승인이다.", "deal", [DEAL_B]),
        ("A와 B를 묶은 가격을 문의했다.", "deal", [DEAL_A, DEAL_B]),
        ("그거 견적도 보내 달랬는데 어느 딜인지는 모른다.", "unresolved", []),
        ("선택하지 않은 C 장비는 다음에 이야기하기로 했다.", "out_of_scope", []),
    ][: 8 if unassigned else 6]
    transcript = "\n".join(text for text, _, _ in rows)
    source = agent.ReportWritingInput.model_validate(
        {
            "transcript": transcript,
            "evidence": {
                "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(),
                "selected_deal_ids": [DEAL_A, DEAL_B],
                "items": [
                    {
                        "segment": {
                            "segment_id": f"S{number:04d}",
                            "start": transcript.index(text),
                            "end": transcript.index(text) + len(text),
                            "text": text,
                        },
                        "applicability": {"scope": scope, "deal_ids": ids},
                    }
                    for number, (text, scope, ids) in enumerate(rows, 1)
                ],
            },
        }
    )
    draft = agent.FreeformMeetingReports(
        deal_reports=[
            agent.DealReport(
                sales_deal_id=deal,
                title=f"{deal} 논의",
                body=f"{rows[index][0]} {rows[5][0]}",
                evidence_ids=[f"S{index + 1:04d}", "S0006"],
            )
            for deal, index in ((DEAL_A, 3), (DEAL_B, 4))
        ],
        common_report=agent.ReportBody(
            body=" ".join(text for text, _, _ in rows[:3]),
            evidence_ids=["S0001", "S0002", "S0003"],
        ),
        unassigned_report=agent.ReportBody(
            body="딜 미지정 · 확인 필요: " + "\n".join(text for text, _, _ in rows[6:]),
            evidence_ids=["S0007", "S0008"],
        )
        if unassigned
        else None,
    )
    return source, draft


def test_common_report_is_required_even_when_a_deal_mentions_common_context():
    source, draft = _case()
    assert agent.ReportWritingInput.model_validate(source.model_dump(mode="json")) == source
    assert source.crm_context == {}
    agent.validate_reports(source, draft)

    draft.deal_reports[0].body += " " + draft.common_report.body
    draft.deal_reports[0].evidence_ids.extend(draft.common_report.evidence_ids)
    agent.validate_reports(source, draft)
    draft.common_report = None
    with pytest.raises(ValueError, match="report_common_evidence_mismatch"):
        agent.validate_reports(source, draft)
    issue = agent._structural_issues(source, draft)[0]
    assert issue["missing_ids"] == ["S0001", "S0002", "S0003"]
    assert {item["segment_id"] for item in issue["required_raw_quotes"]} == set(
        issue["missing_ids"]
    )


def test_common_report_is_absent_when_all_evidence_belongs_to_deals():
    source, draft = _case()
    payload = source.model_dump(mode="json")
    for item in payload["evidence"]["items"][:3]:
        item["applicability"] = {"scope": "deal", "deal_ids": [str(DEAL_A)]}
    source = agent.ReportWritingInput.model_validate(payload)
    draft.deal_reports[0].body += " " + draft.common_report.body
    draft.deal_reports[0].evidence_ids.extend(draft.common_report.evidence_ids)
    draft.common_report = None
    agent.validate_reports(source, draft)
    draft.common_report = agent.ReportBody(body="근거 없는 공통 내용", evidence_ids=[])
    with pytest.raises(ValueError, match="report_common_without_evidence"):
        agent.validate_reports(source, draft)


@pytest.mark.parametrize(
    "part, error",
    [
        ("hash", "report_transcript_hash_mismatch"),
        ("segment", "source_segment_text_mismatch"),
        ("gap", "source_segment_gap"),
        ("extra", "extra_forbidden"),
    ],
)
def test_input_rejects_tampered_source(part, error):
    source, _ = _case()
    payload = source.model_dump(mode="json")
    if part == "hash":
        payload["evidence"]["transcript_sha256"] = "0" * 64
    elif part == "segment":
        payload["evidence"]["items"][0]["segment"]["text"] = "원문에 없는 내용."
    elif part == "gap":
        payload["evidence"]["items"].pop(3)
    else:
        payload["unrecognized"] = True
    with pytest.raises(ValidationError, match=error):
        agent.ReportWritingInput.model_validate(payload)


@pytest.mark.parametrize(
    "body, refs, error",
    [
        (" \n ", [], "report_body_empty"),
        ("내용", ["S0001", "S0001"], "report_evidence_duplicate"),
        ("내용", ["arbitrary-id"], "string_pattern_mismatch"),
    ],
)
def test_report_body_rejects_invalid_structure(body, refs, error):
    with pytest.raises(ValidationError, match=error):
        agent.ReportBody(body=body, evidence_ids=refs)


@pytest.mark.parametrize("ids", [(DEAL_A,), (DEAL_A, DEAL_A), (DEAL_A, OTHER_DEAL)])
def test_reports_require_each_selected_deal_once(ids):
    source, draft = _case()
    draft.deal_reports = [
        draft.deal_reports[0].model_copy(update={"sales_deal_id": deal}) for deal in ids
    ]
    with pytest.raises(ValueError, match="report_selected_deals_mismatch"):
        agent.validate_reports(source, draft)


@pytest.mark.parametrize(
    "target, refs, error",
    [
        ("a", ["S0004"], "report_deal_evidence_mismatch"),
        ("b", ["S0005"], "report_deal_evidence_mismatch"),
        ("a", ["S0004", "S0006", "S0005"], "report_deal_evidence_mismatch"),
        ("a", ["S0004", "S0006", "S0007"], "report_deal_evidence_mismatch"),
        ("a", ["S0004", "S0006", "S9999"], "report_deal_evidence_mismatch"),
        ("common", ["S0004"], "report_common_evidence_mismatch"),
        ("common", ["S0001", "S0002"], "report_common_evidence_mismatch"),
        ("unassigned", ["S0007"], "report_unassigned_evidence_missing"),
        ("unassigned", ["S0008"], "report_unassigned_evidence_missing"),
        ("unassigned", ["S0007", "S0008", "S0004"], "report_unassigned_evidence_missing"),
    ],
)
def test_reports_reject_missing_or_mixed_evidence(target, refs, error):
    source, draft = _case()
    report = {
        "a": draft.deal_reports[0],
        "b": draft.deal_reports[1],
        "common": draft.common_report,
        "unassigned": draft.unassigned_report,
    }[target]
    report.evidence_ids = refs
    with pytest.raises(ValueError, match=error):
        agent.validate_reports(source, draft)


@pytest.mark.parametrize("segment_index", [6, 7])
def test_unresolved_and_out_of_scope_must_keep_original_text(segment_index):
    source, draft = _case()
    text = source.evidence.items[segment_index].segment.text
    draft.unassigned_report.body = draft.unassigned_report.body.replace(text, "요약으로 대체")
    with pytest.raises(ValueError, match="report_unassigned_original_missing"):
        agent.validate_reports(source, draft)


def test_unassigned_report_is_required_only_when_there_is_unassigned_evidence():
    source, draft = _case()
    draft.unassigned_report = None
    with pytest.raises(ValueError, match="report_unassigned_evidence_missing"):
        agent.validate_reports(source, draft)

    source, draft = _case(unassigned=False)
    agent.validate_reports(source, draft)
    draft.unassigned_report = agent.ReportBody(body="근거 없는 미지정 내용", evidence_ids=[])
    with pytest.raises(ValueError, match="report_unassigned_without_evidence"):
        agent.validate_reports(source, draft)


@pytest.fixture
def model_settings(monkeypatch):
    monkeypatch.setattr(agent.settings, "llm_api_url", "https://provider.invalid/v1/responses")
    monkeypatch.setattr(agent.settings, "llm_api_key", SecretStr("synthetic-test-key"))
    monkeypatch.setattr(agent.settings, "llm_model", "synthetic-model")
    monkeypatch.setattr(agent.settings, "llm_timeout_seconds", 7.0)


@pytest.mark.parametrize(
    "endpoint, base, responses",
    [
        ("https://provider.invalid/v1/responses", "https://provider.invalid/v1", True),
        ("https://provider.invalid/v1/responses/", "https://provider.invalid/v1", True),
        (
            "https://provider.invalid/api/v2/chat/completions",
            "https://provider.invalid/api/v2",
            False,
        ),
        ("http://localhost:1234/v1/chat/completions", "http://localhost:1234/v1", False),
    ],
)
def test_model_config_preserves_api_base_without_endpoint_suffix(
    model_settings,
    monkeypatch,
    endpoint,
    base,
    responses,
):
    monkeypatch.setattr(agent.settings, "llm_api_url", endpoint)
    model = agent._configured_model()
    assert model.openai_api_base == base
    assert model.use_responses_api is responses
    assert model.model_name == "synthetic-model"
    assert model.request_timeout.read == 180.0
    assert model.request_timeout.connect == 10.0
    assert model.stream_chunk_timeout == 180.0
    assert model.streaming is True
    assert model.stream_usage is True
    assert model.max_retries == 0


def test_model_config_respects_larger_timeout(model_settings, monkeypatch):
    monkeypatch.setattr(agent.settings, "llm_timeout_seconds", 240.0)
    model = agent._configured_model()
    assert model.request_timeout.read == 240.0
    assert model.stream_chunk_timeout == 240.0
    assert model.request_timeout.connect == 10.0


def test_executive_report_prompt_version_is_explicit():
    assert agent.PROMPT_VERSION == "report_writing.deep.v9"
    skill = (agent.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "핵심 사실이 현재 딜의 진행, 보류 또는 다음 판단에 미치는 의미" in skill
    assert "상급자의 결정이나 지원이 실제로 필요하다는 근거" in skill


def test_deal_schema_emits_identity_before_live_body():
    assert list(agent.DealReport.model_json_schema()["properties"]) == [
        "sales_deal_id",
        "title",
        "body",
        "evidence_ids",
    ]
    with pytest.raises(ValidationError, match="report_evidence_duplicate"):
        agent.DealReport(sales_deal_id=DEAL_A, body="내용", evidence_ids=["S0001", "S0001"])


def test_new_reports_require_title_but_legacy_snapshot_still_deserializes():
    source, draft = _case()
    payload = draft.model_dump(mode="json")
    payload["deal_reports"][0].pop("title")
    legacy = agent.FreeformMeetingReports.model_validate(payload)

    assert legacy.deal_reports[0].title is None
    with pytest.raises(ValueError, match="report_deal_title_missing"):
        agent.validate_reports(source, legacy)
    agent.validate_reports(source, legacy, require_titles=False)


@pytest.mark.parametrize("field", ["title", "body"])
def test_selected_deal_without_current_evidence_requires_exact_marker(field):
    source, draft = _case()
    payload = source.model_dump(mode="json")
    for item in payload["evidence"]["items"][4:6]:
        item["applicability"] = {"scope": "deal", "deal_ids": [str(DEAL_A)]}
    source = agent.ReportWritingInput.model_validate(payload)
    draft.deal_reports[0].evidence_ids = ["S0004", "S0005", "S0006"]
    draft.deal_reports[1].title = agent.NO_DEAL_EVIDENCE_TEXT
    draft.deal_reports[1].body = agent.NO_DEAL_EVIDENCE_TEXT
    draft.deal_reports[1].evidence_ids = []
    agent.validate_reports(source, draft)

    for invalid in (
        "이전 보고서의 논의만 있음",
        f"{agent.NO_DEAL_EVIDENCE_TEXT}. 과거에는 예산을 검토했다.",
    ):
        setattr(draft.deal_reports[1], field, invalid)
        with pytest.raises(ValueError, match="report_deal_no_evidence_marker_missing"):
            agent.validate_reports(source, draft)


def test_selected_deal_without_evidence_reports_marker_error_for_missing_title():
    source, draft = _case()
    payload = source.model_dump(mode="json")
    for item in payload["evidence"]["items"][4:6]:
        item["applicability"] = {"scope": "deal", "deal_ids": [str(DEAL_A)]}
    source = agent.ReportWritingInput.model_validate(payload)
    draft.deal_reports[0].evidence_ids = ["S0004", "S0005", "S0006"]
    draft.deal_reports[1].title = None
    draft.deal_reports[1].body = agent.NO_DEAL_EVIDENCE_TEXT
    draft.deal_reports[1].evidence_ids = []

    with pytest.raises(ValueError, match="report_deal_no_evidence_marker_missing"):
        agent.validate_reports(source, draft)


def test_structural_feedback_reports_all_repairs_and_quotes_without_reassigning_common():
    source, draft = _case()
    draft.deal_reports[0].evidence_ids = ["S0001", "S0005", "S0006"]
    draft.unassigned_report.evidence_ids = ["S0007", "S0004"]
    draft.unassigned_report.body = "불확실한 요청이 있었다."
    issues = agent._structural_issues(source, draft)
    deal = next(item for item in issues if item["code"] == "report_deal_evidence_mismatch")
    assert deal["path"] == "deal_reports[0].evidence_ids"
    assert deal["sales_deal_id"] == str(DEAL_A)
    assert deal["missing_ids"] == ["S0004"]
    assert deal["unexpected_ids"] == ["S0005"]
    assert "S0001" in deal["allowed_ids"]
    assert deal["required_raw_quotes"] == [
        {"segment_id": "S0004", "text": source.evidence.items[3].segment.text}
    ]
    unassigned = next(
        item for item in issues if item["code"] == "report_unassigned_evidence_missing"
    )
    assert unassigned["path"] == "unassigned_report.evidence_ids"
    assert unassigned["missing_ids"] == ["S0008"]
    assert unassigned["unexpected_ids"] == ["S0004"]
    assert {item["segment_id"] for item in unassigned["required_raw_quotes"]} == {"S0007", "S0008"}
    assert all(item["repair_action"] for item in issues)
    assert any(item["code"] == "report_unassigned_original_missing" for item in issues)
    with pytest.raises(ValueError, match="report_deal_evidence_mismatch"):
        agent.validate_reports(source, draft)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://provider.invalid/v1",
        "https://provider.invalid/v1/completions",
        "ftp://provider.invalid/v1/responses",
        "https:///v1/responses",
        "https://user:password@provider.invalid/v1/responses",
        "https://provider.invalid/v1/responses?mode=test",
        "https://provider.invalid/v1/responses#fragment",
    ],
)
def test_model_config_rejects_unsupported_urls(model_settings, monkeypatch, endpoint):
    monkeypatch.setattr(agent.settings, "llm_api_url", endpoint)
    with pytest.raises(LLMError, match="report_agent_unsupported_endpoint"):
        agent._configured_model()


@pytest.mark.parametrize(
    "field, value",
    [
        ("llm_api_key", SecretStr("")),
        ("llm_api_key", SecretStr(" \t\n")),
        ("llm_api_url", ""),
        ("llm_model", ""),
    ],
)
def test_model_config_rejects_missing_credentials(model_settings, monkeypatch, field, value):
    monkeypatch.setattr(agent.settings, field, value)
    with pytest.raises(LLMNotConfigured, match="llm_not_configured"):
        agent._configured_model()

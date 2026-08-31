import asyncio
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents import meeting_analysis
from app.ml import deal_baseline
from app.schemas.meeting_content import (
    MeetingContentAnalysisOutput,
    MeetingContentInput,
    build_evidence_ledger,
)

UNKNOWN_FEATURES = {name: "Unknown" for name in deal_baseline.FEATURE_NAMES}


def test_feature_contract_uses_unknown_instead_of_guessing():
    """미확인 특성은 추측하지 않고 Unknown으로 유지하는지 검증한다."""
    output = meeting_analysis.MeetingFeatureOutput(
        features=UNKNOWN_FEATURES,
    )
    assert output.features.model_dump() == UNKNOWN_FEATURES
    assert tuple(output.features.model_dump()) == deal_baseline.FEATURE_NAMES

    with pytest.raises(ValidationError):
        meeting_analysis.MeetingFeatureOutput(
            features={**UNKNOWN_FEATURES, "Authority": "Maybe"},
        )

    with pytest.raises(ValidationError):
        meeting_analysis.MeetingFeatureOutput(
            features={**UNKNOWN_FEATURES, "unexpected": "Yes"},
        )


def test_input_snapshot_rejects_empty_or_oversized_transcript():
    """빈 원문과 길이 제한을 넘긴 원문이 거부되는지 검증한다."""
    with pytest.raises(ValueError, match="transcript_required"):
        meeting_analysis.input_snapshot("  ")
    with pytest.raises(ValueError, match="transcript_too_long"):
        meeting_analysis.input_snapshot("가" * 50_001)


@pytest.mark.anyio
async def test_run_uses_structured_llm_output_as_model_input(monkeypatch):
    """LLM의 구조화 결과가 그대로 딜 모델 입력으로 전달되는지 검증한다."""
    extracted = meeting_analysis.MeetingFeatureOutput(
        features=UNKNOWN_FEATURES,
    )
    captured = {}

    async def fake_generate_structured(**kwargs):
        """LLM 호출 인자를 기록하고 고정된 구조화 결과를 반환한다."""
        captured.update(kwargs)
        return extracted

    def fake_predict(features):
        """모델 입력 계약을 확인하고 고정된 예측을 반환한다."""
        assert features == UNKNOWN_FEATURES
        return deal_baseline.DealPrediction(
            label="watch",
            high_probability=0.31,
            model_version=deal_baseline.MODEL_VERSION,
        )

    monkeypatch.setattr(meeting_analysis, "generate_structured", fake_generate_structured)
    monkeypatch.setattr(deal_baseline, "predict", fake_predict)

    result = await meeting_analysis.run(
        meeting_analysis.input_snapshot("고객이 다음 주까지 수정 견적서를 요청했습니다.")
    )

    assert result.deal_assessment.features.model_dump() == UNKNOWN_FEATURES
    assert result.deal_assessment.label == "watch"
    assert result.deal_assessment.high_probability == 0.31
    assert result.deal_assessment.model_version == deal_baseline.MODEL_VERSION
    assert captured["instructions"] == meeting_analysis.SYSTEM_PROMPT
    assert captured["schema"] is meeting_analysis.MeetingFeatureOutput
    assert captured["schema_name"] == "meeting_features"
    assert "고객이 다음 주까지 수정 견적서를 요청했습니다." in captured["input_text"]


def _ledger(deal_ids):
    texts = ["이번 미팅에 구매팀이 참석했다."]
    texts += [f"딜 {index} 전용 근거." for index in range(len(deal_ids))]
    texts += ["미지정 비밀 원문.", "무관한 내용.", "모든 선택 딜의 보안 검토가 필요하다."]
    segments = []
    start = 0
    for index, text in enumerate(texts, 1):
        segments.append(
            {"segment_id": f"S{index:04}", "start": start, "end": start + len(text), "text": text}
        )
        start += len(text) + 1
    source = MeetingContentInput(
        transcript="\n".join(texts), selected_deal_ids=deal_ids, segments=segments
    )
    scopes = [("meeting_context", [])]
    scopes += [("deal", [deal_id]) for deal_id in deal_ids]
    scopes += [("unresolved", []), ("out_of_scope", []), ("all_selected_deals", [])]
    analysis = MeetingContentAnalysisOutput(
        assignments=[
            {"segment_id": segment.segment_id, "applicability": {"scope": scope, "deal_ids": ids}}
            for segment, (scope, ids) in zip(source.segments, scopes, strict=True)
        ]
    )
    return build_evidence_ledger(source, analysis)


def _payload(kwargs):
    return json.loads(kwargs["input_text"].split("\n", 1)[1].rsplit("\n", 1)[0])


def _prediction(features):
    return deal_baseline.DealPrediction(label="watch", high_probability=0.3, model_version="mock")


@pytest.mark.anyio
async def test_deal_features_receive_only_allowed_evidence_and_crm(monkeypatch):
    deal_a, deal_b, company, other_company = (uuid4() for _ in range(4))
    crm = {
        "company": {"id": str(company), "name": "합성회사"},
        "contact": {"source_code": "event"},
        "deals": [
            {"sales_deal_id": str(deal_a), "title": "A 거래"},
            {"id": str(deal_b), "title": "B 거래"},
        ],
        "trade_history": [
            {"customer_company_id": str(company), "description": "과거 납품"},
            {"customer_company_id": str(other_company), "description": "타사 비밀"},
            {"description": "회사 미확인 이력"},
        ],
        "additional_context": [
            {
                "kind": "previous_reports",
                "sales_deal_id": str(deal_a),
                "data": {"items": [{"body": "A 이전 보고서"}]},
            },
            {
                "kind": "previous_reports",
                "sales_deal_id": str(deal_b),
                "data": {"items": [{"body": "B 이전 보고서"}]},
            },
        ],
        "unrelated": "루트 비밀",
    }
    seen = {}

    async def generate(**kwargs):
        payload = _payload(kwargs)
        seen[payload["sales_deal_id"]] = payload
        return meeting_analysis.MeetingFeatureOutput(
            features={**UNKNOWN_FEATURES, "Source": "Direct mail"}
        )

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    monkeypatch.setattr(deal_baseline, "predict", _prediction)
    result = await meeting_analysis.run_for_deals(_ledger([deal_a, deal_b]), crm)

    assert [item.sales_deal_id for item in result] == [deal_a, deal_b]
    assert all(item.features.Source == "Event" and item.error is None for item in result)
    for index, deal_id in enumerate([deal_a, deal_b]):
        payload = seen[str(deal_id)]
        text = json.dumps(payload, ensure_ascii=False)
        assert f"딜 {index} 전용 근거." in text
        assert f"딜 {1 - index} 전용 근거." not in text
        assert "구매팀이 참석했다" in text and "모든 선택 딜의 보안 검토" in text
        assert "미지정 비밀" not in text and "무관한 내용" not in text
        assert "타사 비밀" not in text and "회사 미확인 이력" not in text
        assert "루트 비밀" not in text
        assert "과거 납품" in text
        other = "B" if index == 0 else "A"
        assert f"{other} 거래" not in text and f"{other} 이전 보고서" not in text
        assert payload["source_value"] == "Event"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "source_code,expected",
    [
        ("referral", "Referral"),
        ("event", "Event"),
        ("online_form", "Online form"),
        ("joint_past", "Joint past"),
        ("media", "Media"),
        ("other", "Other"),
        ("legacy_source", "Unknown"),
        (None, "Unknown"),
        ([], "Unknown"),
    ],
)
async def test_source_uses_only_six_contact_codes(monkeypatch, source_code, expected):
    deal_id = uuid4()

    async def generate(**kwargs):
        return meeting_analysis.MeetingFeatureOutput(
            features={**UNKNOWN_FEATURES, "Source": "Referral"}
        )

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    monkeypatch.setattr(deal_baseline, "predict", _prediction)
    result = await meeting_analysis.run_for_deals(
        _ledger([deal_id]),
        {
            "contact": {"source_code": source_code},
            "company": {"source_code": "event"},
            "deals": [{"id": str(deal_id), "source_code": "online_form"}],
        },
    )
    assert result[0].features.Source == expected
    assert result[0].assessment.features.Source == expected
    assert result[0].error is None


@pytest.mark.anyio
async def test_per_deal_failures_preserve_other_results_and_extracted_features(monkeypatch):
    deal_a, deal_b, deal_c = (uuid4() for _ in range(3))

    async def generate(**kwargs):
        deal_id = _payload(kwargs)["sales_deal_id"]
        if deal_id == str(deal_a):
            raise RuntimeError("private provider details")
        return meeting_analysis.MeetingFeatureOutput(
            features={
                **UNKNOWN_FEATURES,
                "Authority": "High" if deal_id == str(deal_b) else "Unknown",
            }
        )

    def predict(features):
        if features["Authority"] == "High":
            raise RuntimeError("private model details")
        return _prediction(features)

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    monkeypatch.setattr(deal_baseline, "predict", predict)
    result = await meeting_analysis.run_for_deals(_ledger([deal_a, deal_b, deal_c]), {})

    assert result[0].error == "deal_feature_failed" and result[0].features is None
    assert result[1].error == "deal_prediction_failed" and result[1].features.Authority == "High"
    assert result[1].assessment is None
    assert result[2].error is None and result[2].assessment is not None
    assert "private" not in str(result)


@pytest.mark.anyio
async def test_at_most_three_deals_are_analyzed_concurrently(monkeypatch):
    current = peak = 0

    async def generate(**kwargs):
        nonlocal current, peak
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0)
        current -= 1
        return meeting_analysis.MeetingFeatureOutput(features=UNKNOWN_FEATURES)

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    monkeypatch.setattr(deal_baseline, "predict", _prediction)
    result = await meeting_analysis.run_for_deals(_ledger([uuid4() for _ in range(5)]), {})

    assert peak == 3
    assert len(result) == 5
    assert all(item.error is None for item in result)


@pytest.mark.anyio
async def test_timeout_preserves_completed_deals_and_features_before_slow_ml(monkeypatch):
    deal_a, deal_b, deal_c = (uuid4() for _ in range(3))
    cancelled = set()
    previous_tasks = asyncio.all_tasks()

    async def generate(**kwargs):
        deal_id = _payload(kwargs)["sales_deal_id"]
        if deal_id == str(deal_c):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.add("features")
        return meeting_analysis.MeetingFeatureOutput(
            features={
                **UNKNOWN_FEATURES,
                "Authority": "High" if deal_id == str(deal_b) else "Unknown",
            }
        )

    async def predict_in_thread(function, features):
        if features["Authority"] == "High":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.add("prediction")
        return _prediction(features)

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    monkeypatch.setattr(meeting_analysis.asyncio, "to_thread", predict_in_thread)
    result = await meeting_analysis.run_for_deals(
        _ledger([deal_a, deal_b, deal_c]), {}, timeout=0.02
    )

    assert [item.sales_deal_id for item in result] == [deal_a, deal_b, deal_c]
    assert result[0].error is None and result[0].assessment is not None
    assert result[1].error == "deal_analysis_timeout"
    assert result[1].features.Authority == "High" and result[1].assessment is None
    assert result[2].error == "deal_analysis_timeout" and result[2].features is None
    assert cancelled == {"features", "prediction"}
    assert asyncio.all_tasks() <= previous_tasks


@pytest.mark.anyio
async def test_caller_cancellation_cleans_running_and_semaphore_waiting_deals(monkeypatch):
    started, finished = set(), set()
    ready = asyncio.Event()
    previous_tasks = asyncio.all_tasks()

    async def generate(**kwargs):
        deal_id = _payload(kwargs)["sales_deal_id"]
        started.add(deal_id)
        if len(started) == 3:
            ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.add(deal_id)

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    task = asyncio.create_task(
        meeting_analysis.run_for_deals(_ledger([uuid4() for _ in range(5)]), {})
    )
    await asyncio.wait_for(ready.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(started) == 3 and finished == started
    assert asyncio.all_tasks() <= previous_tasks

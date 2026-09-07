import asyncio
import copy
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
from app.services.llm import LLMError

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
        "contact": {
            "id": "private-contact-id",
            "name": "private-contact-name",
            "department": "구매부",
            "job_title": "부장",
            "source_code": None,
            "owner_member_id": "private-owner-id",
            "memo": "private-contact-memo",
        },
        "deals": [
            {"sales_deal_id": str(deal_a), "title": "A 거래", "source_code": "event"},
            {"id": str(deal_b), "title": "B 거래", "source_code": "referral"},
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
    original = copy.deepcopy(crm)
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
    assert [item.features.Source for item in result] == ["Event", "Referral"]
    assert all(item.error is None for item in result)
    assert crm == original
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
        assert payload["source_value"] == ("Event" if index == 0 else "Referral")
        assert payload["crm_context"]["contact"] == {"department": "구매부", "job_title": "부장"}
        assert "private-" not in text


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
async def test_source_uses_each_deals_effective_source_code(monkeypatch, source_code, expected):
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
            "contact": {"source_code": "referral"},
            "company": {"source_code": "event"},
            "deals": [{"id": str(deal_id), "source_code": source_code}],
        },
    )
    assert result[0].features.Source == expected
    if expected == "Unknown":
        assert result[0].assessment is None
        assert result[0].error == "deal_prediction_insufficient_features"
    else:
        assert result[0].assessment.features.Source == expected
        assert result[0].error is None


@pytest.mark.anyio
async def test_all_unknown_skips_prediction_but_partial_unknown_still_predicts(monkeypatch):
    no_signal, partial_signal = uuid4(), uuid4()
    predicted = []

    async def generate(**kwargs):
        deal_id = _payload(kwargs)["sales_deal_id"]
        return meeting_analysis.MeetingFeatureOutput(
            features={
                **UNKNOWN_FEATURES,
                "Authority": "High" if deal_id == str(partial_signal) else "Unknown",
            }
        )

    def predict(features):
        predicted.append(features)
        return _prediction(features)

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    monkeypatch.setattr(deal_baseline, "predict", predict)
    result = await meeting_analysis.run_for_deals(_ledger([no_signal, partial_signal]), {})

    assert result[0].features.model_dump() == UNKNOWN_FEATURES
    assert result[0].assessment is None
    assert result[0].error == "deal_prediction_insufficient_features"
    assert len(predicted) == 1 and predicted[0]["Authority"] == "High"
    assert result[1].assessment is not None and result[1].error is None


@pytest.mark.anyio
async def test_per_deal_failures_preserve_other_results_and_extracted_features(monkeypatch):
    deal_a, deal_b, deal_c = (uuid4() for _ in range(3))

    async def generate(**kwargs):
        deal_id = _payload(kwargs)["sales_deal_id"]
        if deal_id == str(deal_a):
            raise LLMError("private provider details")
        return meeting_analysis.MeetingFeatureOutput(
            features={
                **UNKNOWN_FEATURES,
                "Authority": "High" if deal_id == str(deal_b) else "Low",
            }
        )

    def predict(features):
        if features["Authority"] == "High":
            raise deal_baseline.DealModelError("private model details")
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
async def test_unexpected_programming_error_fails_the_run(monkeypatch):
    async def generate(**kwargs):
        raise RuntimeError("programming bug")

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    with pytest.raises(RuntimeError, match="programming bug"):
        await meeting_analysis.run_for_deals(_ledger([uuid4()]), {})


@pytest.mark.anyio
async def test_transient_feature_failure_fails_the_run_for_worker_retry(monkeypatch):
    async def generate(**kwargs):
        raise LLMError("llm_request_failed:ConnectError")

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    with pytest.raises(LLMError, match="^llm_request_failed:ConnectError$"):
        await meeting_analysis.run_for_deals(_ledger([uuid4()]), {})


@pytest.mark.anyio
async def test_at_most_three_deals_are_analyzed_concurrently(monkeypatch):
    current = peak = 0

    async def generate(**kwargs):
        nonlocal current, peak
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0)
        current -= 1
        return meeting_analysis.MeetingFeatureOutput(
            features={**UNKNOWN_FEATURES, "Authority": "Low"}
        )

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
    completed, waiting_features, waiting_prediction = (asyncio.Event() for _ in range(3))
    real_wait = asyncio.wait

    async def expire_after_deals_are_ready(tasks, *, timeout):
        assert timeout == 60
        await asyncio.wait_for(
            asyncio.gather(completed.wait(), waiting_features.wait(), waiting_prediction.wait()),
            timeout=5,
        )
        return await real_wait(tasks, timeout=0)

    async def generate(**kwargs):
        if str(deal_c) in kwargs["input_text"]:
            waiting_features.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.add("features")
        return meeting_analysis.MeetingFeatureOutput(
            features={
                **UNKNOWN_FEATURES,
                "Authority": "High" if str(deal_b) in kwargs["input_text"] else "Low",
            }
        )

    async def predict_in_thread(function, features):
        if features["Authority"] == "High":
            waiting_prediction.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.add("prediction")
        completed.set()
        return _prediction(features)

    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    monkeypatch.setattr(meeting_analysis.asyncio, "to_thread", predict_in_thread)
    monkeypatch.setattr(meeting_analysis.asyncio, "wait", expire_after_deals_are_ready)
    result = await meeting_analysis.run_for_deals(_ledger([deal_a, deal_b, deal_c]), {}, timeout=60)

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

from types import SimpleNamespace

import pytest

from app.schemas.business_cards import BusinessCardFields
from app.services import business_cards


@pytest.mark.anyio
async def test_extract_builds_registration_ready_draft(monkeypatch):
    captured = {}

    async def _generate(**_kwargs):
        captured.update(_kwargs)
        return BusinessCardFields(
            name="합성 담당자",
            company_name="합성 회사",
            department="영업팀",
            job_title="팀장",
            phone="010-0000-0000",
            email="contact@example.test",
            website="https://example.test",
        )

    monkeypatch.setattr(business_cards, "generate_structured", _generate)

    draft = await business_cards.extract(
        ocr_text="합성 명함 OCR\n이메일: contact @ example . test",
        file_name="card.png",
    )

    assert draft.ready_for_contact_registration is True
    assert draft.missing_required_fields == []
    assert draft.fields.company_name == "합성 회사"
    assert business_cards.contact_memo(draft.fields) == "웹사이트: https://example.test"
    assert "contact@example.test" in captured["input_text"]


def test_normalize_ocr_contact_text_keeps_contact_symbols_parseable():
    value = "이메일: contact @ example . com\n사이트: example . com / sales"

    assert business_cards.normalize_ocr_contact_text(value) == (
        "이메일: contact@example.com\n사이트: example.com/sales"
    )


@pytest.mark.anyio
async def test_extract_does_not_mark_incomplete_ocr_as_ready(monkeypatch):
    async def _generate(**_kwargs):
        return BusinessCardFields(name="합성 담당자")

    monkeypatch.setattr(business_cards, "generate_structured", _generate)

    draft = await business_cards.extract(ocr_text="이름만 인식됨")

    assert draft.ready_for_contact_registration is False
    assert draft.missing_required_fields == ["company_name", "phone"]


def test_normalize_phone_only_removes_redundant_spaces():
    assert business_cards.normalize_phone("010-0000-0000  ") == "010-0000-0000"


def test_match_labels_reports_normalized_phone_email_and_name_company():
    contact = SimpleNamespace(
        name="홍길동",
        phone="010-1234-5678",
        email="sales@example.com",
    )
    fields = BusinessCardFields(
        name="홍길동",
        company_name="예시 회사",
        phone="010 1234 5678",
        email="SALES@example.com",
    )

    assert business_cards.match_labels(
        fields,
        contact=contact,
        company_name="예시 회사",
    ) == ["phone", "email", "name_company"]

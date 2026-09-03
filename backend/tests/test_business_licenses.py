import pytest

from app.schemas.business_licenses import BusinessLicenseFields
from app.services import business_licenses


@pytest.mark.anyio
async def test_extract_builds_company_registration_draft(monkeypatch):
    captured = {}

    async def _generate(**kwargs):
        captured.update(kwargs)
        return BusinessLicenseFields(
            company="합성 주식회사",
            business_no="123-45-67890",
            address="서울시 합성구",
        )

    monkeypatch.setattr(business_licenses, "generate_structured", _generate)

    draft = await business_licenses.extract(
        ocr_text="사업자등록증 OCR",
        file_name="license.pdf",
    )

    assert draft.ready_for_company_registration is True
    assert draft.missing_required_fields == []
    assert draft.fields.company == "합성 주식회사"
    assert captured["schema_name"] == "business_license_fields"


@pytest.mark.anyio
async def test_extract_marks_missing_company_or_number(monkeypatch):
    async def _generate(**_kwargs):
        return BusinessLicenseFields(address="주소만 확인")

    monkeypatch.setattr(business_licenses, "generate_structured", _generate)

    draft = await business_licenses.extract(ocr_text="주소만 확인")

    assert draft.ready_for_company_registration is False
    assert draft.missing_required_fields == ["company", "business_no"]


@pytest.mark.anyio
async def test_extract_falls_back_to_explicit_license_labels(monkeypatch):
    async def _generate(**_kwargs):
        # 모델이 번호만 반환하는 상황을 재현한다.
        return BusinessLicenseFields(business_no="123-45-67890")

    monkeypatch.setattr(business_licenses, "generate_structured", _generate)

    draft = await business_licenses.extract(
        ocr_text=(
            "사업자등록증\n"
            "법 인 명 ( 단 체 명 ) : 합성 주식회사\n"
            "사업장 소 재 지 : 서울시 합성구"
        )
    )

    assert draft.fields.company == "합성 주식회사"
    assert draft.fields.address == "서울시 합성구"
    assert draft.ready_for_company_registration is True

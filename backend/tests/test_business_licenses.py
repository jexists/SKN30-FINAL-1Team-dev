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
            "사업자등록증\n법 인 명 ( 단 체 명 ) : 합성 주식회사\n사업장 소 재 지 : 서울시 합성구"
        )
    )

    assert draft.fields.company == "합성 주식회사"
    assert draft.fields.address == "서울시 합성구"
    assert draft.ready_for_company_registration is True


@pytest.fixture
def number_only_llm(monkeypatch):
    """모델이 번호만 반환해 라벨 폴백에 기대는 상황을 재현한다."""

    async def _generate(**_kwargs):
        return BusinessLicenseFields(business_no="123-45-67890")

    monkeypatch.setattr(business_licenses, "generate_structured", _generate)


@pytest.mark.anyio
async def test_extract_reads_labels_from_markdown_table(number_only_llm):
    # MinerU와 pdf-inspector는 국세청 양식을 표로 낸다.
    draft = await business_licenses.extract(
        ocr_text=(
            "# 사업자등록증\n"
            "\n"
            "| 법 인 명 (단체명) | 합성 주식회사 |\n"
            "| --- | --- |\n"
            "| 대 표 자 | 합성 사람 |\n"
            "| 사 업 장 소 재 지 | 서울시 합성구 합성로 1 |"
        )
    )

    assert draft.fields.company == "합성 주식회사"
    assert draft.fields.address == "서울시 합성구 합성로 1"


@pytest.mark.anyio
async def test_extract_reads_labels_wrapped_in_bold(number_only_llm):
    draft = await business_licenses.extract(
        ocr_text="**법인명(단체명)** : 합성 주식회사\n**사업장 소재지** : 서울시 합성구"
    )

    assert draft.fields.company == "합성 주식회사"
    assert draft.fields.address == "서울시 합성구"


@pytest.mark.anyio
async def test_extract_stops_value_at_the_next_label_on_one_line(number_only_llm):
    # 2단 양식이 한 줄로 합쳐져도 옆 칸 값이 섞이지 않는다.
    draft = await business_licenses.extract(
        ocr_text=(
            "법 인 명 (단체명) : 합성 주식회사   대 표 자 : 합성 사람\n"
            "사업장 소재지 : 서울시 합성구 합성로 1   업태 : 제조"
        )
    )

    assert draft.fields.company == "합성 주식회사"
    assert draft.fields.address == "서울시 합성구 합성로 1"


@pytest.mark.anyio
async def test_extract_accepts_short_address_label_and_full_width_colon(number_only_llm):
    draft = await business_licenses.extract(ocr_text="상호： 합성 주식회사\n소재지： 서울시 합성구")

    assert draft.fields.company == "합성 주식회사"
    assert draft.fields.address == "서울시 합성구"


@pytest.mark.anyio
async def test_extract_keeps_values_that_merely_contain_a_label_word(number_only_llm):
    # "상호테크"의 "상호"는 라벨이 아니다. 콜론이 붙은 것만 라벨로 본다.
    draft = await business_licenses.extract(
        ocr_text="상호 : 주식회사 상호테크\n주소 : 서울시 합성구 상호로 5"
    )

    assert draft.fields.company == "주식회사 상호테크"
    assert draft.fields.address == "서울시 합성구 상호로 5"


@pytest.mark.anyio
async def test_extract_reads_the_representative(number_only_llm):
    # 등록증의 사람은 대표자뿐이다. 담당자 이름 칸의 첫 값으로 쓴다.
    draft = await business_licenses.extract(
        ocr_text=(
            "법 인 명 ( 단 체 명 ) : 합성 주식회사\n"
            "대  표  자 : 합성 사람\n"
            "사업장 소재지 : 서울시 합성구"
        )
    )

    assert draft.fields.representative == "합성 사람"
    assert draft.fields.company == "합성 주식회사"


@pytest.mark.anyio
async def test_extract_leaves_representative_blank_when_absent(number_only_llm):
    draft = await business_licenses.extract(ocr_text="상호 : 합성 주식회사")

    assert draft.fields.representative == ""
    # 대표자는 필수가 아니라 등록 가능 여부를 막지 않는다.
    assert draft.ready_for_company_registration is True


@pytest.mark.anyio
async def test_extract_reads_value_on_the_line_after_a_bare_label(number_only_llm):
    # 값이 다음 줄로 밀리면 OCR이 콜론을 그쪽으로 흘리기도 한다.
    draft = await business_licenses.extract(ocr_text="법인명(단체명)\n: 합성 주식회사")

    assert draft.fields.company == "합성 주식회사"

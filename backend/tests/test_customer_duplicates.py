"""등록 방식 넷이 함께 쓰는 중복 기준. DB 없이 판단 규칙만 확인한다."""

from types import SimpleNamespace

from app.services.customer_duplicates import (
    DuplicateProbe,
    duplicate_keys,
    match_labels,
    normalized_email,
    phone_digits,
)


def test_phone_ignores_hyphens_and_spaces():
    assert phone_digits("010-1234-5678") == phone_digits("010 1234 5678") == "01012345678"
    assert phone_digits(None) == ""


def test_email_ignores_case_and_padding():
    assert normalized_email("  Sales@Example.COM ") == "sales@example.com"
    assert normalized_email(None) == ""


def test_keys_cover_phone_email_and_name_with_company():
    keys = duplicate_keys(
        DuplicateProbe(
            company_name=" ABC회사 ",
            name=" 홍길동 ",
            phone="010-1234-5678",
            email="Hong@Test.com",
        )
    )
    assert keys == {
        "phone:01012345678",
        "email:hong@test.com",
        "name_company:홍길동|abc회사",
    }


def test_empty_values_make_no_keys():
    """빈 칸끼리 겹쳤다고 같은 사람으로 볼 수는 없다."""
    assert duplicate_keys(DuplicateProbe()) == set()
    assert duplicate_keys(DuplicateProbe(phone="  ", email="")) == set()


def test_name_alone_is_not_enough():
    """이름만 같은 두 사람은 중복이 아니다. 회사가 함께 같아야 한다."""
    assert duplicate_keys(DuplicateProbe(name="홍길동")) == set()
    only_name = duplicate_keys(DuplicateProbe(name="홍길동", company_name="ABC회사"))
    other_company = duplicate_keys(DuplicateProbe(name="홍길동", company_name="XYZ회사"))
    assert only_name & other_company == set()


def test_same_person_in_two_rows_shares_a_key_even_if_only_the_phone_matches():
    first = duplicate_keys(
        DuplicateProbe(company_name="ABC회사", name="홍길동", phone="01011112222")
    )
    second = duplicate_keys(
        DuplicateProbe(company_name="에이비씨", name="홍 길동", phone="010-1111-2222")
    )
    assert first & second == {"phone:01011112222"}


def test_match_labels_explain_which_values_overlapped():
    contact = SimpleNamespace(name="홍길동", phone="010-1234-5678", email="sales@example.com")
    probe = DuplicateProbe(
        company_name="예시 회사",
        name="홍길동",
        phone="010 1234 5678",
        email="SALES@example.com",
    )

    assert match_labels(probe, contact=contact, company_name="예시 회사") == [
        "phone",
        "email",
        "name_company",
    ]
    assert match_labels(probe, contact=contact, company_name="다른 회사") == ["phone", "email"]


def test_match_labels_ignore_contacts_without_the_compared_value():
    contact = SimpleNamespace(name="김철수", phone="02-000-0000", email=None)
    probe = DuplicateProbe(company_name="예시 회사", name="홍길동", phone="010-1234-5678", email="")

    assert match_labels(probe, contact=contact, company_name="예시 회사") == []

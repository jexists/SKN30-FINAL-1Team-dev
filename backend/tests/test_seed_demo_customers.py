from collections import Counter
from uuid import uuid5

from scripts.seed_demo_auth import FILLED_MEMBER2_ID, FILLED_MEMBER_ID, FILLED_TEAM_ID
from scripts.seed_demo_customers import (
    COMPANY_REGIONS,
    CONTACT_SEEDS,
    OWNER_IDS,
    ROSTER_MEMBERS,
    SOURCE_CODES,
    STATUS_CODES,
    company_id,
    contact_id,
    contact_rows,
)


def test_demo_customer_seed_shape_is_fixed_and_synthetic():
    assert len(CONTACT_SEEDS) == 32
    assert len({contact.mock_id for contact in CONTACT_SEEDS}) == 32
    assert len({contact_id(contact.mock_id) for contact in CONTACT_SEEDS}) == 32
    assert set(COMPANY_REGIONS) == {contact.company_name for contact in CONTACT_SEEDS}
    assert len({company_id(name) for name in COMPANY_REGIONS}) == 6
    assert Counter(contact.owner_name for contact in CONTACT_SEEDS) == {
        "김지훈": 11,
        "이수민": 10,
        "박도윤": 6,
        "최가은": 5,
    }
    assert OWNER_IDS["김지훈"] == FILLED_MEMBER_ID
    assert OWNER_IDS["이수민"] == FILLED_MEMBER2_ID
    assert set(OWNER_IDS) == {"김지훈", "이수민", "박도윤", "최가은"}
    assert all(contact.email.endswith("@demo.test") for contact in CONTACT_SEEDS)
    assert all(contact.phone.startswith("02-000-") for contact in CONTACT_SEEDS)
    assert all(contact.source in SOURCE_CODES for contact in CONTACT_SEEDS)
    assert all(contact.status in STATUS_CODES for contact in CONTACT_SEEDS)

    status_ids = {
        code: uuid5(FILLED_TEAM_ID, f"customer-contact-status:{code}")
        for code in STATUS_CODES.values()
    }
    rows = contact_rows(status_ids)
    assert len(rows) == 32
    for seed, row in zip(CONTACT_SEEDS, rows, strict=True):
        assert row["customer_contact_status_id"] == status_ids[STATUS_CODES[seed.status]]
        assert "status_code" not in row

    for member in ROSTER_MEMBERS:
        assert member["id"] == uuid5(FILLED_TEAM_ID, f"member:{member['display_name']}")
        assert member["login_id"].endswith("@example.invalid")

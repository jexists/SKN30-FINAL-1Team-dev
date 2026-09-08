import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.activities import _validate_delegated_approval
from app.models.agent import AgentRun
from app.models.crm import Activity
from app.models.sales import SalesDeal


def fixture():
    member = SimpleNamespace(id=uuid4(), team_id=uuid4())
    start = datetime.now(UTC) + timedelta(days=2)
    payload = SimpleNamespace(sales_deal_id=uuid4(), customer_company_id=uuid4(),
                              starts_at=start, ends_at=start + timedelta(hours=1), all_day=False)
    child = SimpleNamespace(id=uuid4(), parent_run_id=uuid4(), team_id=member.team_id,
        delegation_key="key", status_code="completed",
        source_refs={"sales_deal_id": str(payload.sales_deal_id)},
        output_snapshot={"schedule_candidates": [{"candidate_id": "test", "priority": 1,
            "starts_at": payload.starts_at.isoformat(), "ends_at": payload.ends_at.isoformat()}]})
    parent = SimpleNamespace(team_id=member.team_id, status_code="completed",
                             output_snapshot={"schedule_management_run_id": str(child.id)})
    deal = SimpleNamespace(id=payload.sales_deal_id, team_id=member.team_id,
        owner_member_id=member.id, deleted_at=None, customer_company_id=payload.customer_company_id)

    class Db:
        windows = []

        async def get(self, model, key):
            if model is SalesDeal:
                return deal
            assert model is AgentRun
            return child if key == child.id else parent

        async def execute(self, statement):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.windows))
    return Db(), member, payload, child, parent, deal


def test_current_candidate_approval_passes():
    db, member, payload, child, *_ = fixture()
    asyncio.run(_validate_delegated_approval(db, member, child.id, payload))


@pytest.mark.parametrize("case", ["team", "assignee", "time", "selected", "conflict", "all_day"])
def test_invalid_delegated_approval_is_rejected_before_insert(case):
    db, member, payload, child, parent, deal = fixture()
    if case == "team":
        child.team_id = uuid4()
    elif case == "assignee":
        deal.owner_member_id = uuid4()
    elif case == "time":
        payload.starts_at += timedelta(minutes=5)
    elif case == "selected":
        parent.output_snapshot["schedule_management_run_id"] = str(uuid4())
    elif case == "all_day":
        payload.all_day = True
    else:
        db.windows = [Activity(id=uuid4(), starts_at=payload.starts_at,
                               ends_at=payload.ends_at, all_day=False)]
    with pytest.raises(HTTPException) as error:
        asyncio.run(_validate_delegated_approval(db, member, child.id, payload))
    assert error.value.status_code in (404, 409)

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.sales import Product
from app.models.workspace import Member
from app.schemas.sales_deals import ProductCreate

ORIGIN = settings.cors_origin_list[0]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_MISSING = object()


class _Result:
    def __init__(self, *, scalar=_MISSING):
        self.scalar = scalar

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def storage_ready(monkeypatch):
    monkeypatch.setattr(type(settings), "storage_configured", property(lambda self: True))
    yield


def _member(*, role: str = "member") -> Member:
    return Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _product(member: Member, *, image_storage_key: str | None = None) -> Product:
    return Product(
        id=uuid4(),
        team_id=member.team_id,
        name="합성 초음파 시스템",
        active=True,
        category_code="system",
        unit_price=12_000_000,
        shelf_life_months=24,
        memo=None,
        image_storage_key=image_storage_key,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


PAYLOAD = {
    "name": "합성 초음파 시스템",
    "category_code": "system",
    "unit_price": 12_000_000,
    "shelf_life_months": 24,
    "memo": "데모 장비",
}


def test_product_request_rejects_unsafe_values():
    with pytest.raises(ValidationError):
        # 팀과 활성 여부는 요청으로 정할 수 없다.
        ProductCreate(**PAYLOAD, team_id=uuid4())
    with pytest.raises(ValidationError):
        ProductCreate(**{**PAYLOAD, "category_code": "probe_x"})
    with pytest.raises(ValidationError):
        ProductCreate(**{**PAYLOAD, "unit_price": -1})
    with pytest.raises(ValidationError):
        ProductCreate(**{**PAYLOAD, "shelf_life_months": 0})
    with pytest.raises(ValidationError):
        ProductCreate(**{**PAYLOAD, "name": ""})


def test_member_cannot_create_product():
    db = _Db()
    with _client(db, _member()) as client:
        response = client.post("/api/products", headers={"Origin": ORIGIN}, json=PAYLOAD)
    assert response.status_code == 403
    assert response.json()["detail"] == "manager_required"
    assert db.added == []
    assert db.commit_count == 0


def test_manager_creates_product_without_leaking_storage_key():
    member = _member(role="manager")
    db = _Db()
    with _client(db, member) as client:
        response = client.post("/api/products", headers={"Origin": ORIGIN}, json=PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "합성 초음파 시스템"
    assert body["unit_price"] == 12_000_000
    assert body["shelf_life_months"] == 24
    assert body["active"] is True
    assert body["has_image"] is False
    assert "image_storage_key" not in body
    assert response.headers["Location"] == f"/api/products/{body['id']}"

    assert db.commit_count == 1
    created = db.added[0]
    assert created.team_id == member.team_id


def test_member_cannot_upload_product_image(storage_ready):
    db = _Db()
    with _client(db, _member()) as client:
        response = client.put(
            f"/api/products/{uuid4()}/image",
            headers={"Origin": ORIGIN},
            files={"upload": ("제품.png", PNG, "image/png")},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "manager_required"
    assert db.commit_count == 0


def test_product_without_image_has_no_download_url(storage_ready):
    member = _member()
    db = _Db(_Result(scalar=_product(member)))
    with _client(db, member) as client:
        response = client.get(f"/api/products/{uuid4()}/image", headers={"Origin": ORIGIN})
    assert response.status_code == 404
    assert response.json()["detail"] == "product_image_not_found"


def test_other_team_product_image_is_not_found(storage_ready):
    db = _Db(_Result(scalar=None))
    with _client(db, _member()) as client:
        response = client.get(f"/api/products/{uuid4()}/image", headers={"Origin": ORIGIN})
    assert response.status_code == 404
    assert response.json()["detail"] == "product_not_found"

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import sales_deals as sales_api
from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.sales import Product
from app.models.workspace import Member
from app.schemas.sales_deals import ProductCreate, ProductPageParams

ORIGIN = settings.cors_origin_list[0]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_MISSING = object()


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalars(self):
        return _Scalars(self.rows)


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.added = []
        self.statements = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
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


def test_product_search_covers_memo_and_category_codes():
    """검색이 제품명·메모·분류 이름을 함께 훑던 동작을 서버가 그대로 해야 한다.

    분류 이름("소모품")은 화면(catalog.ts)만 알고 DB 에는 코드만 있으므로, 화면이 코드로
    풀어 보내고 서버가 q 와 OR 로 묶는다. AND 로 묶이면 이름이 걸린 제품이 사라진다.
    """
    member = _member(role="manager")
    product = _product(member)
    db = _Db(_Result(scalar=1), _Result(rows=[product]))

    page = asyncio.run(
        sales_api.list_products(
            ProductPageParams(q="소모", q_category_code=["consumable"]),
            member,
            db,
        )
    )

    assert page.total == 1
    # 개수 쿼리와 행 쿼리가 같은 조건이어야 총계와 목록이 어긋나지 않는다.
    for statement in db.statements:
        sql = str(statement)
        assert "lower(public.product.name) LIKE" in sql
        assert "lower(public.product.memo) LIKE" in sql
        # 세 조건은 OR 이어야 한다. AND 로 묶이면 이름만 걸린 제품이 사라진다.
        assert "OR lower(public.product.memo) LIKE" in sql
        assert "OR public.product.category_code IN" in sql

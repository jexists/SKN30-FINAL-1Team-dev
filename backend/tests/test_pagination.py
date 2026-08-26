"""쪽 조회 파라미터의 공통 경계.

목록은 한 번에 30건까지만 준다. 상한이 한 곳만 헐거우면 그 엔드포인트로 전건을 받아
갈 수 있어, 클래스마다 따로 선언된 limit 을 여기서 한꺼번에 붙잡는다.
"""

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.activities import ActivityPageParams
from app.schemas.customers import CustomerContactPageParams, CustomerPageParams
from app.schemas.documents import DocumentPageParams
from app.schemas.notices import NoticeManagePageParams, NoticePageParams
from app.schemas.orders import OrderPageParams
from app.schemas.reports import ReportPageParams
from app.schemas.sales_deals import ProductPageParams, SalesDealPageParams
from app.schemas.support import SupportRequestPageParams

PAGE_PARAMS: list[type[BaseModel]] = [
    ActivityPageParams,
    CustomerPageParams,
    CustomerContactPageParams,
    DocumentPageParams,
    NoticeManagePageParams,
    NoticePageParams,
    OrderPageParams,
    ProductPageParams,
    ReportPageParams,
    SalesDealPageParams,
    SupportRequestPageParams,
]

MAX_LIMIT = 30


@pytest.mark.parametrize("params", PAGE_PARAMS, ids=lambda cls: cls.__name__)
def test_limit_defaults_to_the_page_size(params: type[BaseModel]):
    assert params().limit == MAX_LIMIT
    assert params().skip == 0


@pytest.mark.parametrize("params", PAGE_PARAMS, ids=lambda cls: cls.__name__)
def test_limit_over_the_page_size_is_rejected(params: type[BaseModel]):
    assert params(limit=MAX_LIMIT).limit == MAX_LIMIT
    with pytest.raises(ValidationError):
        params(limit=MAX_LIMIT + 1)
    with pytest.raises(ValidationError):
        params(limit=0)


@pytest.mark.parametrize("params", PAGE_PARAMS, ids=lambda cls: cls.__name__)
def test_skip_is_bounded_to_int64(params: type[BaseModel]):
    """offset 으로 바로 들어가므로 bigint 를 넘으면 DB 에러가 아니라 422 여야 한다."""
    with pytest.raises(ValidationError):
        params(skip=-1)
    with pytest.raises(ValidationError):
        params(skip=2**63)

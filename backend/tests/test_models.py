import asyncio

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import configure_mappers

from app.core.config import settings
from app.db.base import Base
from app.models.agent import AgentRun

EXPECTED_COLUMN_COUNTS = {
    # 20260823_0002 로 team 에 company_name/department/business_no, member 에 email 이 늘었다.
    "team": 6,
    "member": 8,
    # 20260824_0003 으로 customer_company 에 business_no,
    # customer_contact 에 created_by_member_id 가 늘고 customer_contact_assignee 가 생겼다.
    # 20260826_0009 로 customer_company 에 postcode/address/address_detail 이 늘었다.
    "customer_company": 9,
    # 20260824_0004 로 customer_contact 에 visited 가 늘었다.
    "customer_contact": 14,
    "customer_contact_assignee": 3,
    "customer_contact_status": 9,
    # 20260824_0004 로 product 에 category_code/unit_price/shelf_life_months/memo/
    # image_storage_key 가 늘었다.
    "product": 9,
    # 20260825_0005 로 notice 에 type/display_start_date/display_end_date/is_hidden/
    # sort_order/updated_at/deleted_at 이 늘고 recipient_member_id 가 빠졌다.
    # 수신자는 notice_target 으로 옮겼고, 본문 사진은 notice_image 가 가리킨다.
    "notice": 19,
    "notice_target": 3,
    "notice_image": 6,
    # 20260827_0010 으로 세 표에서 activity_type 이 빠졌다. 활동은 늘 미팅이다.
    "activity": 21,
    "activity_category": 9,
    "activity_action_tag": 9,
    "activity_companion": 2,
    # 20260825_0006 으로 support_request 에 customer_company_id/sales_deal_id/occurred_at 이
    # 늘고 customer_contact_id 가 빠졌다. 불만은 담당자 대신 회사와 계약건에 맨다.
    "support_request": 11,
    "support_response": 5,
    "sales_pipeline": 10,
    "sales_pipeline_stage": 10,
    "sales_deal_type": 8,
    # 20260826_0007 로 sales_deal 에 견적·계약의 자기 값(상태 2, 금액 2, 납품문구 1)이,
    # purchase_order 에 요청·협조부서와 작성자·납품예상 거래처가 늘었다.
    # 견적/계약 상태 룩업과 견적 품목·미팅 대상자 표도 이때 생겼다.
    # 20260826_0008 이 계약서 양식의 물품대금 지급기일·대금연체 이자율을 더했다.
    "sales_deal": 35,
    "sales_deal_item": 6,
    "sales_deal_participant": 3,
    "quote_status": 10,
    "contract_status": 10,
    "purchase_order_status": 10,
    "purchase_order": 17,
    "purchase_order_item": 6,
    "sales_target": 5,
    "report": 20,
    "report_activity": 2,
    # 20260825_0006 으로 명함 원본을 담당자와 연결하는 customer_contact_id 가 늘었다.
    "document": 13,
    "file": 19,
    "document_chunk": 12,
    "agent_run": 17,
}


def test_all_database_tables_are_mapped():
    configure_mappers()

    assert AgentRun.__tablename__ == "agent_run"
    assert {
        table.name: len(table.columns) for table in Base.metadata.sorted_tables
    } == EXPECTED_COLUMN_COUNTS
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 356

    foreign_key_constraints = [
        foreign_key
        for table in Base.metadata.tables.values()
        for foreign_key in table.foreign_key_constraints
    ]
    assert len(foreign_key_constraints) == 85
    assert all(
        element.column.table.schema == "public"
        for foreign_key in foreign_key_constraints
        for element in foreign_key.elements
    )


@pytest.mark.skipif(not settings.database_url, reason="DATABASE_URL 미설정")
def test_models_match_configured_database():
    asyncio.run(_assert_models_match_database())


async def _assert_models_match_database():
    engine = create_async_engine(settings.async_database_url)

    def compare(connection):
        inspector = inspect(connection)
        database_tables = set(inspector.get_table_names(schema="public"))
        model_tables = {table.name for table in Base.metadata.tables.values()}
        assert database_tables == model_tables

        for table in Base.metadata.tables.values():
            database_columns = {
                column["name"]: column
                for column in inspector.get_columns(table.name, schema="public")
            }
            assert set(database_columns) == set(table.columns.keys())

            for column in table.columns:
                database_column = database_columns[column.name]
                assert database_column["nullable"] == column.nullable
                assert database_column["type"].compile(
                    dialect=connection.dialect
                ) == column.type.compile(dialect=connection.dialect)
                model_default = (
                    None if column.server_default is None else str(column.server_default.arg)
                )
                assert database_column["default"] == model_default

            database_primary_key = set(
                inspector.get_pk_constraint(table.name, schema="public")["constrained_columns"]
            )
            assert database_primary_key == {column.name for column in table.primary_key}
            assert _database_foreign_keys(inspector, table.name) == _model_foreign_keys(table)

    try:
        async with engine.connect() as connection:
            await connection.run_sync(compare)
    finally:
        await engine.dispose()


def _database_foreign_keys(inspector, table_name):
    # member.id 는 Supabase 가 관리하는 auth.users 를 가리킨다.
    # 그 스키마는 ORM 에 매핑하지 않으므로 모델 쪽에는 대응하는 FK 가 없다.
    return {
        (
            column,
            foreign_key["referred_schema"],
            foreign_key["referred_table"],
            referred_column,
            foreign_key["options"].get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys(table_name, schema="public")
        if foreign_key["referred_schema"] != "auth"
        for column, referred_column in zip(
            foreign_key["constrained_columns"],
            foreign_key["referred_columns"],
            strict=True,
        )
    }


def _model_foreign_keys(table):
    return {
        (
            foreign_key.parent.name,
            foreign_key.column.table.schema,
            foreign_key.column.table.name,
            foreign_key.column.name,
            foreign_key.ondelete,
        )
        for foreign_key in table.foreign_keys
    }

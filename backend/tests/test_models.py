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
    "customer_company": 6,
    # 20260824_0004 로 customer_contact 에 visited 가 늘었다.
    "customer_contact": 14,
    "customer_contact_assignee": 3,
    "customer_contact_status": 9,
    "product": 4,
    "notice": 12,
    "activity": 22,
    "activity_category": 10,
    "activity_action_tag": 10,
    "activity_companion": 2,
    "support_request": 9,
    "support_response": 5,
    "sales_pipeline": 10,
    "sales_pipeline_stage": 10,
    "sales_deal_type": 8,
    "sales_deal": 28,
    "purchase_order_status": 10,
    "purchase_order": 13,
    "purchase_order_item": 6,
    "sales_target": 5,
    "report": 20,
    "report_activity": 2,
    "document": 12,
    "file": 13,
    "agent_run": 17,
}


def test_all_database_tables_are_mapped():
    configure_mappers()

    assert AgentRun.__tablename__ == "agent_run"
    assert {
        table.name: len(table.columns) for table in Base.metadata.sorted_tables
    } == EXPECTED_COLUMN_COUNTS
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 274

    foreign_key_constraints = [
        foreign_key
        for table in Base.metadata.tables.values()
        for foreign_key in table.foreign_key_constraints
    ]
    assert len(foreign_key_constraints) == 67
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

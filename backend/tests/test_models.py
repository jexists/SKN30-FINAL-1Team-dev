import asyncio

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import configure_mappers

from app.core.config import settings
from app.db.base import Base
from app.models.agent import AgentRun

EXPECTED_COLUMN_COUNTS = {
    "team": 3,
    "member": 9,
    "customer_company": 5,
    "customer_contact": 12,
    "product": 4,
    "notice": 12,
    "activity": 22,
    "activity_companion": 2,
    "support_request": 9,
    "support_response": 5,
    "pipeline_stage": 6,
    "contract": 21,
    "purchase_order": 15,
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
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 200

    foreign_keys = [
        foreign_key for table in Base.metadata.tables.values() for foreign_key in table.foreign_keys
    ]
    assert len(foreign_keys) == 55
    assert all(foreign_key.column.table.schema == "public" for foreign_key in foreign_keys)


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
    return {
        (
            column,
            foreign_key["referred_schema"],
            foreign_key["referred_table"],
            referred_column,
            foreign_key["options"].get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys(table_name, schema="public")
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

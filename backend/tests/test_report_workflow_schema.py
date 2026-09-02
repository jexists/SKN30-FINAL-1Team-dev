from pathlib import Path

from sqlalchemy.dialects.postgresql import dialect

from app.models.content import (
    DocumentChunk,
    DocumentFileAudit,
    File,
    Report,
    ReportDeal,
    ReportSource,
    ReportSubmission,
)

MIGRATION = Path(__file__).parents[1] / "sql/20260901_0017_report_workflow_v2_foundation.sql"
TRANSIENT_MIGRATION = (
    Path(__file__).parents[1] / "sql/20260902_0019_transient_report_generation.sql"
)


def test_report_workflow_v2_models_expose_the_additive_contract():
    assert set(Report.__table__.columns.keys()) >= {
        "customer_company_id",
        "title",
        "body",
        "common_body",
        "unassigned_body",
        "structured_values",
        "version",
        "generation_input_version",
        "current_submission_id",
    }
    assert set(ReportDeal.__table__.columns.keys()) >= {
        "position",
        "deal_no_snapshot",
        "deal_title_snapshot",
        "title",
        "body",
        "structured_values",
    }
    assert set(ReportSubmission.__table__.columns.keys()) == {
        "id",
        "report_id",
        "revision_no",
        "report_version",
        "team_id",
        "submitted_by_member_id",
        "agent_run_id",
        "idempotency_key",
        "request_hash",
        "snapshot",
        "snapshot_sha256",
        "review_status",
        "reviewed_by_member_id",
        "reviewed_at",
        "review_note",
        "submitted_at",
    }
    assert set(ReportSource.__table__.columns.keys()) == {
        "report_id",
        "position",
        "source_activity_id",
        "source_report_submission_id",
    }
    assert str(Report.__table__.c.structured_values.server_default.arg) == "'{}'::jsonb"
    assert str(Report.__table__.c.version.server_default.arg) == "1"
    assert str(Report.__table__.c.generation_input_version.server_default.arg) == "1"


def test_report_workflow_v2_foreign_keys_keep_aggregate_membership():
    report_current = next(
        constraint
        for constraint in Report.__table__.foreign_key_constraints
        if constraint.name == "report_current_submission_fkey"
    )
    assert [element.parent.name for element in report_current.elements] == [
        "id",
        "current_submission_id",
    ]
    assert [element.target_fullname for element in report_current.elements] == [
        "public.report_submission.report_id",
        "public.report_submission.id",
    ]
    assert report_current.deferrable is True


def test_nullable_jsonb_uses_sql_null_instead_of_json_null():
    nullable_json_columns = [
        Report.__table__.c.source_snapshot,
        Report.__table__.c.ai_evidence,
        File.__table__.c.extracted_payload,
        File.__table__.c.summary_payload,
        DocumentChunk.__table__.c.embedding,
        DocumentFileAudit.__table__.c.before_snapshot,
        DocumentFileAudit.__table__.c.after_snapshot,
    ]
    postgres = dialect()
    for column in nullable_json_columns:
        assert column.type.none_as_null is True
        assert column.type.bind_processor(postgres)(None) is None


def test_report_workflow_v2_migration_preserves_legacy_and_history_boundaries():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE public.report_submission" in sql
    assert "CREATE TABLE public.report_source" in sql
    assert "CREATE TABLE public.meeting_deal_analysis" in sql
    assert "FOREIGN KEY (id, current_submission_id)" in sql
    assert "report_id uuid NOT NULL REFERENCES public.report (id) ON DELETE CASCADE" in sql
    assert "meeting_deal_analysis_report_deal_fkey" not in sql
    assert "num_nonnulls(source_activity_id, source_report_submission_id) = 1" in sql
    assert "report submission snapshot is immutable" in sql
    assert "INSERT INTO public.report_submission" not in sql
    assert "SET status_code = 'changes_requested' WHERE status_code = 'rejected'" in sql
    assert "DROP COLUMN" not in sql
    assert "DROP TABLE" not in sql
    assert "structured_values = CASE" in sql
    assert sql.count("(content -> 'values') - 'body'") == 2
    assert "count(DISTINCT customer_company_id) = 1" in sql
    assert "UPDATE public.report_deal SET ai_evidence = NULL" in sql


def test_transient_generation_migration_is_additive_and_guards_provenance():
    sql = TRANSIENT_MIGRATION.read_text(encoding="utf-8")

    assert "agent_run_active_generation_scope_key" in sql
    assert "payload_expires_at" in sql
    assert "report_submission_submitter_idempotency_key" in sql
    assert "CREATE OR REPLACE FUNCTION public.guard_report_submission_update()" in sql
    assert "NEW.agent_run_id" in sql
    assert "NEW.idempotency_key" in sql
    assert "NEW.request_hash" in sql
    assert "DROP COLUMN" not in sql
    assert "DROP TABLE" not in sql

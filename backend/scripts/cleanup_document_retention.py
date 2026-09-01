"""자료실 보관 정책 정리 명령.

운영 스케줄러에서 다음처럼 하루 한 번 호출합니다.
    uv run python -m scripts.cleanup_document_retention

삭제 전 대상만 확인할 때:
    uv run python -m scripts.cleanup_document_retention --dry-run
"""

import argparse
import asyncio

from app.services.document_retention import cleanup_expired


async def main(*, dry_run: bool) -> None:
    result = await cleanup_expired(dry_run=dry_run)
    print(
        "document retention cleanup: "
        f"dry_run={dry_run}, "
        f"review_drafts={result.expired_review_drafts}, "
        f"unapproved_files={result.expired_unapproved_files}, "
        f"audit_logs={result.deleted_audit_logs}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SalesLuv 자료실 만료 데이터 정리")
    parser.add_argument("--dry-run", action="store_true", help="삭제하지 않고 대상 건수만 출력")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))

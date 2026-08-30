"""이미 있는 딜에 대해 "다음 미팅 제안 → 일정 후보"를 한 번씩 미리 계산해 둔다.

캘린더 "AI 추천 일정" 패널은 트리거(보고서 확정·일정 수동 등록·영업 딜 생성/이동·CS 처리
시작)가 미리 계산해 둔 결과만 조회한다. 그래서 이 방식으로 바꾼 직후에는, 아직 아무 트리거도
걸리지 않은 기존 딜의 카드가 하나도 뜨지 않는다. 이 스크립트가 그 빈자리를 한 번 채운다.

대상은 0차 선별 스냅샷이 고른 딜이다 — 위험 신호가 하나도 없거나 이미 앞으로 잡힌 일정이
있는 딜은 애초에 제외된다(contract_schedule_snapshots.build_candidate_selection_snapshot).

딜 하나에 LLM 호출이 두 번 든다. 먼저 --dry-run 으로 대상 수를 확인하고 실행하는 것을
권한다.

    uv run python scripts/backfill_contract_next_meeting_suggestions.py --dry-run
    uv run python scripts/backfill_contract_next_meeting_suggestions.py

화면을 확인하거나 데모를 준비할 때는 전체를 돌릴 필요가 없다. 카드는 로그인한 사람 소유의
딜만 뜨므로 그 계정으로 몇 건만 채운다.

    uv run python scripts/backfill_contract_next_meeting_suggestions.py --owner 김팀원 --limit 3
"""

import argparse
import asyncio
import os
import sys
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.models.workspace import Member  # noqa: E402
from app.services import contract_next_meeting_pipeline as pipeline  # noqa: E402
from app.services import contract_schedule_snapshots  # noqa: E402


async def _targets(owner_name: str | None, limit: int | None) -> list[tuple[str, UUID]]:
    """(담당자 이름, 딜 id) 목록. 0차 선별과 같은 규칙으로 고른다.

    카드는 로그인한 사람 소유의 딜만 뜨므로(팀원 기준), 화면을 확인할 때는 --owner 로 그
    계정만 좁히고 --limit 로 몇 건만 채우는 것으로 충분하다.
    """
    sessionmaker = get_sessionmaker()
    targets: list[tuple[str, UUID]] = []
    async with sessionmaker() as session:
        members = (await session.execute(select(Member))).scalars().all()
        if owner_name is not None:
            members = [m for m in members if m.display_name == owner_name]
            if not members:
                raise SystemExit(f"'{owner_name}' 담당자를 찾지 못했다.")
        for member in members:
            snapshot = await contract_schedule_snapshots.build_candidate_selection_snapshot(
                session, member
            )
            for candidate in snapshot.get("candidates") or []:
                targets.append((member.display_name, UUID(candidate["sales_deal_id"])))
                if limit is not None and len(targets) >= limit:
                    return targets
    return targets


async def main(dry_run: bool, owner_name: str | None, limit: int | None) -> int:
    if not settings.llm_configured:
        print("LLM 설정이 없어 아무것도 하지 않는다. .env 의 LLM_* 값을 확인하라.")
        return 1

    targets = await _targets(owner_name, limit)
    print(f"대상 딜 {len(targets)}건 (LLM 호출 예상 {len(targets) * 2}회)")
    for owner, sales_deal_id in targets:
        print(f"  {owner} · {sales_deal_id}")
    if dry_run:
        print("\n--dry-run 이라 실행하지 않았다.")
        return 0

    done = 0
    for owner, sales_deal_id in targets:
        print(f"\n[{done + 1}/{len(targets)}] {owner} · {sales_deal_id}")
        # 파이프라인은 실패를 스스로 삼킨다(백그라운드에서 도는 코드라서). 한 건이
        # 실패해도 나머지는 그대로 이어 간다.
        await pipeline._run_pipeline(sales_deal_id, {"backfill": "true"})
        done += 1
    print(f"\n{done}건 처리했다. 캘린더에서 결과를 확인하라.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="대상만 세고 실행하지 않는다")
    parser.add_argument("--owner", help="이 담당자(표시 이름)의 딜만 채운다")
    parser.add_argument("--limit", type=int, help="앞에서 N건만 채운다")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.dry_run, args.owner, args.limit)))

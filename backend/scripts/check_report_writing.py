"""합성 업무 입력으로 실제 기간 보고서 작성 에이전트를 확인한다."""

import asyncio
import json
import os
import sys

TEMPLATE = {
    "fields": [
        {"id": "body", "label": "보고서 본문"},
    ]
}


async def check() -> None:
    os.environ["DEBUG"] = "false"

    from app.agents import report_writing
    from app.core.config import settings

    if not settings.llm_configured:
        raise RuntimeError("LLM_API_URL, LLM_API_KEY, LLM_MODEL 설정이 필요합니다.")

    output = await report_writing.run(
        {
            "report_kind": "daily",
            "report_date": "2026-08-21",
            "template_snapshot": TEMPLATE,
            "content": {
                "values": {
                    "body": (
                        "합성 테스트 업무다. 영업 담당자 박민수와 고객 담당자 김영희가 "
                        "미팅했고, 고객은 제품 도입에 긍정적이며 견적서를 검토하기로 했다. "
                        "다음 주 수요일까지 견적서를 전달하고 후속 미팅을 잡기로 했다."
                    )
                }
            },
            "transcript": None,
            "guidance": "확정된 사실과 예정된 후속 조치를 구분해 자연스러운 줄글로 정리하세요.",
        }
    )

    print("[실제 보고서 작성 응답]")
    print(json.dumps(output.model_dump(), ensure_ascii=False, indent=2))

    actual_ids = [field.field_id for field in output.fields]
    if actual_ids != ["body"]:
        raise ValueError(f"body 하나가 아닌 field_id: {actual_ids}")
    if not output.fields[0].value.strip():
        raise ValueError("body가 비어 있습니다.")


def main() -> int:
    try:
        asyncio.run(check())
    except Exception as error:
        print(f"[실패] {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print("[성공] 실제 보고서 작성 에이전트 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

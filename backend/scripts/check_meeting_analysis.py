"""합성 미팅 입력으로 실제 미팅분석 에이전트와 기준 분류기를 확인한다."""

import asyncio
import json
import os
import sys


async def check() -> None:
    os.environ["DEBUG"] = "false"

    from app.agents import meeting_analysis
    from app.core.config import settings
    from app.ml import deal_baseline

    if not settings.llm_configured:
        raise RuntimeError("LLM_API_URL, LLM_API_KEY, LLM_MODEL 설정이 필요합니다.")

    transcript = (
        "합성 테스트 미팅입니다. 최종 의사결정권자가 참석했고 구매부서도 참여했습니다. "
        "예산은 승인되었으며 공식 입찰과 경쟁 제품 검토는 진행하지 않습니다. "
        "고객은 도입에 긍정적이고 도입 범위와 요구사항은 명확합니다."
    )
    output = await meeting_analysis.run(meeting_analysis.input_snapshot(transcript))

    print("[실제 미팅분석 응답]")
    print(json.dumps(output.model_dump(), ensure_ascii=False, indent=2))

    assessment = output.deal_assessment
    features = assessment.features.model_dump()
    if len(features) != len(deal_baseline.FEATURE_NAMES) or len(features) != 10:
        raise ValueError(f"딜 특성 개수가 10개가 아닙니다: {len(features)}")
    if set(features) != set(deal_baseline.FEATURE_NAMES):
        raise ValueError(f"딜 특성 10개가 일치하지 않습니다: {list(features)}")
    actual = (assessment.label, assessment.high_probability, assessment.model_version)
    expected = ("watch", 0.5, deal_baseline.MODEL_VERSION)
    if actual != expected:
        raise ValueError(f"기준 분류 결과가 다릅니다: {actual}")


def main() -> int:
    try:
        asyncio.run(check())
    except Exception as error:
        print(f"[실패] {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print("[성공] 실제 미팅분석 에이전트와 기준 분류기 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

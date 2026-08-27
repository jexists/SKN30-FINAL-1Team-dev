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
    if tuple(features) != deal_baseline.FEATURE_NAMES:
        raise ValueError(f"딜 특성 13개의 순서가 일치하지 않습니다: {list(features)}")
    if not 0 <= assessment.high_probability <= 1:
        raise ValueError(f"성사 확률 범위가 잘못되었습니다: {assessment.high_probability}")
    expected_label = "high" if assessment.high_probability >= 0.5 else "watch"
    if assessment.label != expected_label:
        raise ValueError(f"임계값과 라벨이 일치하지 않습니다: {assessment.label}")
    if assessment.model_version != deal_baseline.MODEL_VERSION:
        raise ValueError(f"모델 버전이 일치하지 않습니다: {assessment.model_version}")


def main() -> int:
    try:
        asyncio.run(check())
    except Exception as error:
        print(f"[실패] {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print("[성공] 실제 미팅분석 에이전트와 최종 앙상블 모델 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""문서요약 1차·2차 평가 결과를 비교하는 PDF 보고서 생성기."""

# 보고서용 한글 문장은 표 가독성을 위해 한 줄 길이 검사를 제외한다.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from statistics import mean

from build_document_summary_pdfs import (
    NumberedDocTemplate,
    callout,
    configure_font,
    make_styles,
    safe,
    section_title,
    table,
)
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle

METRICS = (
    ("overall", "Overall"),
    ("completeness", "Completeness"),
    ("hallucination", "Hallucination 품질점수"),
    ("irrelevance", "Irrelevance 품질점수"),
    ("groundedness", "Groundedness"),
    ("retrieval_relevance", "Retrieval relevance"),
)
PRODUCT_FILES = {"EU-ME2.pdf", "Quick Clip2.pdf", "URF-V2.pdf"}


def nfc(value: object) -> str:
    return unicodedata.normalize("NFC", str(value))


def category(row: dict) -> str:
    names = row.get("source_files") or row.get("expected_source_files") or [""]
    name = nfc(names[0])
    if name in PRODUCT_FILES:
        return "상품설명서"
    return nfc(name.split("_")[0])


def case_key(row: dict) -> str:
    return nfc(row["case_id"]).removesuffix("_001")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def average_by_category(rows: list[dict]) -> dict[str, float]:
    grouped: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[category(row)].append(float(row["judge"]["overall"]))
    return {name: mean(values) for name, values in grouped.items()}


def score_delta(current: dict, previous: dict, key: str) -> float:
    return float(current["judge"][key]) - float(previous["judge"][key])


def fmt(value: float) -> str:
    return f"{value:.4f}"


def delta(value: float) -> str:
    return f"{value:+.4f}"


def case_changes(previous: dict, current: dict, result_key: str) -> list[dict]:
    old = {case_key(row): row for row in previous[result_key]}
    new = {case_key(row): row for row in current[result_key]}
    changes: list[dict] = []
    for key in sorted(old.keys() & new.keys()):
        changes.append(
            {
                "case_id": key,
                "category": category(new[key]),
                "first": float(old[key]["judge"]["overall"]),
                "second": float(new[key]["judge"]["overall"]),
                "delta": score_delta(new[key], old[key], "overall"),
                "issues": new[key]["judge"].get("issues") or [],
            }
        )
    return changes


def decision_card(
    *,
    overall_delta: float,
    styles: dict,
) -> Table:
    """첫 페이지에서 결론·해석·우선 조치를 한눈에 보여주는 요약 카드."""
    if overall_delta < 0:
        conclusion = "2차 점수는 1차보다 낮아졌으며, 추가 개선과 재검증이 필요하다."
    else:
        conclusion = "2차 점수는 1차보다 높아졌으며, 개선 방향을 유지할 수 있다."
    rows = [
        [Paragraph("결론", styles["cell_head"]), Paragraph(safe(conclusion), styles["callout"])],
        [
            Paragraph("해석", styles["cell_head"]),
            Paragraph(
                safe("검색 관련성은 개선됐지만 답변 완결성은 낮아졌다. 2차 점수만으로 구조 변경의 순수 효과를 단정하지 않는다."),
                styles["callout"],
            ),
        ],
        [
            Paragraph("우선 조치", styles["cell_head"]),
            Paragraph(
                safe("계약서 금액·당사자·날짜 검증과 상품설명서 사양·사용 제한 검색 보완을 먼저 진행한다."),
                styles["callout"],
            ),
        ],
    ]
    result = Table(rows, colWidths=[27 * mm, 147 * mm], hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#344054")),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#F2F4F7")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D5DD")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return result


def build_report(
    output: Path,
    first: dict,
    second: dict,
    first_dir: Path,
    second_dir: Path,
    styles: dict,
) -> None:
    first_aggregate = first["aggregate"]
    second_aggregate = second["aggregate"]
    overall_delta = float(second_aggregate["overall"]) - float(first_aggregate["overall"])
    summary_changes = case_changes(first, second, "summary_results")
    rag_changes = case_changes(first, second, "rag_results")
    summary_first = average_by_category(first["summary_results"])
    summary_second = average_by_category(second["summary_results"])
    rag_first = average_by_category(first["rag_results"])
    rag_second = average_by_category(second["rag_results"])

    story: list[object] = [
        Paragraph("문서요약 에이전트·RAG 1차·2차 비교보고서", styles["title"]),
        Paragraph("작성일: 2026-09-15 | 비교 범위: 4개 유형 각 3개, 총 24개 평가 케이스", styles["subtitle"]),
        decision_card(overall_delta=overall_delta, styles=styles),
        Spacer(1, 4 * mm),
        Paragraph(
            f"[검증] 1차 Overall {fmt(float(first_aggregate['overall']))}에서 2차 Overall {fmt(float(second_aggregate['overall']))}로 {delta(overall_delta)} 변화했다.",
            styles["body"],
        ),
        section_title("1. 비교 대상과 방법", styles),
        table(
            [
                ["항목", "1차", "2차"],
                ["평가 결과 위치", f"[검증] {first_dir}", f"[검증] {second_dir}"],
                ["문서 범위", "[검증] 견적서·계약서·발주서·상품설명서 각 3개", "[검증] 동일 파일명 기준 각 3개"],
                ["평가 케이스", "[검증] 요약 12건 + RAG 12건", "[검증] 요약 12건 + RAG 12건"],
                ["평가 방식", "[검증] RAGEval 적응형 골든셋 + LLM-as-a-Judge", "[검증] RAGEval 적응형 골든셋 + LLM-as-a-Judge"],
                ["검색 방식", "[검증] 평가 스크립트 로컬 키워드 검색", "[검증] 평가 스크립트 로컬 키워드 검색; 임베딩 검색 미측정"],
            ],
            [35 *  mm, 69 * mm, 70 * mm],
            styles,
        ),
        section_title("2. 전체 지표 비교", styles),
    ]

    metric_rows = [["지표", "1차", "2차", "변화"]]
    for key, label in METRICS:
        old = float(first_aggregate[key])
        new = float(second_aggregate[key])
        metric_rows.append([label, fmt(old), fmt(new), delta(new - old)])
    story.append(table(metric_rows, [71 * mm, 34 * mm, 34 * mm, 35 * mm], styles))
    story.append(
        Paragraph(
            "[검증] 2차에서 Retrieval relevance는 상승했지만 Completeness와 Groundedness는 하락했다. "
            "[추론] 검색된 문맥의 관련성 개선이 답변에 필요한 사실을 빠짐없이 반영하는 것과 동일하지 않다.",
            styles["body"],
        )
    )
    story.append(PageBreak())
    story.append(section_title("3. 문서 유형별 비교", styles))

    type_rows = [["문서 유형", "요약 1차", "요약 2차", "변화", "RAG 1차", "RAG 2차", "변화"]]
    for name in ("견적서", "계약서", "발주서", "상품설명서"):
        type_rows.append(
            [
                name,
                fmt(summary_first[name]),
                fmt(summary_second[name]),
                delta(summary_second[name] - summary_first[name]),
                fmt(rag_first[name]),
                fmt(rag_second[name]),
                delta(rag_second[name] - rag_first[name]),
            ]
        )
    story.append(table(type_rows, [28 * mm, 24 * mm, 24 * mm, 22 * mm, 24 * mm, 24 * mm, 24 * mm], styles))
    story += [
        Paragraph("[검증] 계약서 요약 평균은 0.3400에서 0.3533으로 소폭 상승했지만 낮은 수준을 유지했다.", styles["body"]),
        Paragraph("[검증] 상품설명서 RAG 평균은 0.4500에서 0.4467로 거의 동일하며, EU-ME2·Quick Clip2의 핵심 사양 누락이 반복됐다.", styles["body"]),
        Paragraph("[추론] 발주서 요약·RAG의 상승은 긍정적 신호지만 유형별 표본이 3개이므로 전체 문서군 성능으로 일반화할 수 없다.", styles["body"]),
        section_title("유형별 해석", styles),
        table(
            [
                ["유형", "현재 판단", "우선 개선"],
                ["견적서", "[검증] 요약·RAG 모두 안정적", "[추론] 합계·통화·문서 메타데이터 보존"],
                ["계약서", "[검증] 요약과 RAG 모두 케이스 편차가 큼", "[추론] 당사자·날짜·금액 의미 검증"],
                ["발주서", "[검증] 2차에서 요약·RAG 모두 상승", "[추론] 공급자·납품장소·지급조건 고정"],
                ["상품설명서", "[검증] 요약은 높고 RAG는 낮음", "[추론] 사양·사용 제한·주의사항 검색 강화"],
            ],
            [30 * mm, 69 * mm, 75 * mm],
            styles,
        ),
        PageBreak(),
        section_title("4. 케이스별 변화", styles),
        Paragraph("[검증] Overall 변화 폭이 큰 대표 케이스를 상승·하락으로 나누어 정리했다.", styles["body"]),
    ]

    improvements = sorted(summary_changes + rag_changes, key=lambda row: row["delta"], reverse=True)[:5]
    regressions = sorted(summary_changes + rag_changes, key=lambda row: row["delta"])[:5]
    def change_table(title: str, rows: list[dict]) -> list[object]:
        data = [["케이스", "작업", "1차 -> 2차", "변화", "2차 확인사항"]]
        for row in rows:
            task = "RAG" if row["case_id"].startswith("rag_") else "요약"
            issues = " | ".join(row["issues"][:2]) or "구체적 오류 없음"
            data.append([row["case_id"], task, f"{fmt(row['first'])} -> {fmt(row['second'])}", delta(row["delta"]), f"[검증] {issues}"])
        return [
            Paragraph(title, styles["h2"]),
            table(data, [34 * mm, 18 * mm, 31 * mm, 22 * mm, 69 * mm], styles),
            Spacer(1, 3 * mm),
        ]

    story.extend(change_table("상승 케이스", improvements))
    story.extend(change_table("하락 케이스", regressions))
    story += [
        PageBreak(),
        section_title("변화 요약", styles),
        callout(
            "[검증] 최대 하락: rag_계약서_1, 1.0000 -> 0.0500. LR-PRO 수량·금액 오답이 확인됐다.\n"
            "[검증] 최대 상승: summary_발주서_1, 0.3600 -> 0.5800. 다만 공급자·납품장소·지급조건 누락이 남아 있다.",
            styles,
        ),
        Spacer(1, 3 * mm),
        section_title("5. 종합 판단", styles),
        Paragraph("[추론] 2차는 검색 관련성 지표는 개선됐으나, 계약서 핵심 필드와 상품설명서 사양 답변의 완결성은 아직 안정화되지 않았다.", styles["body"]),
        Paragraph("[추론] 현재 우선순위는 ① 계약서 금액·당사자·날짜 필드 검증, ② 상품설명서 사양·사용 제한 chunk 검색, ③ 사람검수 기준 고정 순서다.", styles["body"]),
        Paragraph("[검증] 두 실행 모두 유형별 3개 샘플만 사용했으므로 50개 전체 데이터셋의 성능 결론으로 사용할 수 없다.", styles["body"]),
        Paragraph("[검증] 사람검수 상태는 2차 결과 기준 pending이며, 자동 Judge 점수는 최종 합격 판정이 아니다.", styles["body"]),
        section_title("6. 다음 실행안과 폐기 조건", styles),
        table(
            [
                ["담당 단위", "실행안", "측정지표", "폐기·전환 조건"],
                ["문서요약 Agent", "[추론] 계약서 필수 필드와 계약금·잔금·VAT 의미를 필수 출력값으로 검증", "필드 누락·역할 혼동 건수", "[가정] 허용 누락률을 정한 뒤 초과 시 프롬프트·후처리 전환"],
                ["RAG 검색", "[추론] 상품설명서 사양표·사용목적·주의사항을 페이지·섹션 우선순위로 검색", "retrieval relevance·답변 completeness", "[가정] Vector DB 임계값과 키워드 fallback 비교 후 낮은 쪽 폐기"],
                ["품질관리", "[추론] 사람검수 승인값을 고정하고 동일 골든셋으로 재평가", "Judge-사람 판정 불일치율", "[가정] 불일치 허용 범위 초과 시 Judge 기준 재설계"],
            ],
            [27 * mm, 68 * mm, 34 * mm, 45 * mm],
            styles,
        ),
    ]
    NumberedDocTemplate(str(output), styles=styles).build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-dir", type=Path, required=True)
    parser.add_argument("--second-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    font = configure_font()
    styles = make_styles(font)
    first = load(args.first_dir / "llm_judge_results.json")
    second = load(args.second_dir / "llm_judge_results.json")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_report(args.output, first, second, args.first_dir, args.second_dir, styles)
    print(json.dumps({"created": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""문서요약·RAG 사람검수용 단일 HTML 비교 화면 생성기."""

# HTML 템플릿의 한 줄 CSS/마크업은 가독성보다 생성물의 단일 파일 구성을 우선한다.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import unicodedata
from pathlib import Path
from typing import Any


def _json_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _pre(value: Any) -> str:
    return f"<pre>{html.escape(_text(value))}</pre>"


def _list(value: Any) -> str:
    items = value if isinstance(value, list) else []
    if not items:
        return "<span class='muted'>없음</span>"
    return "<ul>" + "".join(f"<li>{html.escape(_text(item))}</li>" for item in items) + "</ul>"


def _score(value: Any) -> str:
    return "-" if value is None else f"{float(value):.4f}"


def _source_paths(golden: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in golden.get("sample_selection", {}).get("source_paths", []):
        name = Path(path).name
        result[name] = path
        result[unicodedata.normalize("NFC", name)] = path
    return result


def _field_rows(row: dict[str, Any]) -> str:
    expected = row.get("reference_fields") or {}
    actual = (row.get("output") or {}).get("extracted_fields") or {}
    keys = list(dict.fromkeys([*expected.keys(), *actual.keys()]))
    if not keys:
        return "<p class='muted'>비교 가능한 구조화 필드가 없습니다.</p>"
    body = []
    for key in keys:
        expected_value = _text(expected.get(key, ""))
        actual_value = _text(actual.get(key, ""))
        normalized_expected = " ".join(expected_value.split()).lower()
        normalized_actual = " ".join(actual_value.split()).lower()
        state = "일치" if normalized_expected == normalized_actual else "확인 필요"
        state_class = "ok" if state == "일치" else "warn"
        body.append(
            "<tr>"
            f"<td>{html.escape(key)}</td>"
            f"<td>{html.escape(expected_value)}</td>"
            f"<td>{html.escape(actual_value)}</td>"
            f"<td class='{state_class}'>{state}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>필드</th><th>기준값</th><th>결과값</th><th>자동 비교</th></tr></thead>"
        "<tbody>" + "".join(body) + "</tbody></table>"
    )


def _summary_card(row: dict[str, Any], source_paths: dict[str, str]) -> str:
    output = row.get("output") or {}
    source = (row.get("source_files") or [""])[0]
    source_path = source_paths.get(source) or source_paths.get(unicodedata.normalize("NFC", source), "")
    judge = row.get("judge") or {}
    return f"""
    <article class='card' data-case-id='{html.escape(row['case_id'])}' data-type='summary'>
      <div class='card-head'><h3>{html.escape(row['case_id'])}</h3><span class='badge'>문서요약</span></div>
      <p class='source'><b>원본:</b> {html.escape(source)} <code>{html.escape(source_path)}</code></p>
      <div class='compare'>
        <section><h4>기준값</h4><p><b>질문</b></p>{_pre(row.get('question', ''))}<p><b>reference_answer</b></p>{_pre(row.get('reference_answer', ''))}<p><b>핵심 사실</b></p>{_list(row.get('key_facts'))}</section>
        <section><h4>결과값</h4><p><b>summary</b></p>{_pre(output.get('summary', ''))}<p><b>key_points</b></p>{_list(output.get('key_points'))}<p><b>risk_flags</b></p>{_list(output.get('risk_flags'))}<p><b>extracted_fields</b></p>{_pre(output.get('extracted_fields', {}))}</section>
      </div>
      <details><summary>필드별 기준값·결과값 비교</summary>{_field_rows(row)}</details>
      <details><summary>LLM Judge</summary><p class='scores'>Overall {_score(judge.get('overall'))} · Completeness {_score(judge.get('completeness'))} · Groundedness {_score(judge.get('groundedness'))} · Hallucination 품질 {_score(judge.get('hallucination'))}</p>{_pre(judge.get('rationale', ''))}<p><b>issues</b></p>{_list(judge.get('issues'))}</details>
      <div class='decision'><label>사람 판정 <select class='decision-select'><option value='pending'>검수 전</option><option value='pass'>통과</option><option value='revise'>수정 필요</option><option value='hold'>보류</option></select></label><label>메모 <textarea class='review-note' placeholder='수정할 사실, 근거, 확인 내용을 적으세요.'></textarea></label></div>
    </article>"""


def _rag_card(row: dict[str, Any], source_paths: dict[str, str]) -> str:
    output = row.get("output") or {}
    judge = row.get("judge") or {}
    expected = row.get("expected_source_files") or []
    retrieved = row.get("retrieved_source_files") or []
    paths = [source_paths.get(name) or source_paths.get(unicodedata.normalize("NFC", name), "") for name in expected]
    return f"""
    <article class='card' data-case-id='{html.escape(row['case_id'])}' data-type='rag'>
      <div class='card-head'><h3>{html.escape(row['case_id'])}</h3><span class='badge rag'>RAG</span></div>
      <div class='compare'>
        <section><h4>기준값</h4><p><b>질문</b></p>{_pre(row.get('question', ''))}<p><b>reference_answer</b></p>{_pre(row.get('reference_answer', ''))}<p><b>expected_source_files</b></p>{_list(expected)}<p><b>원본 경로</b></p>{_list(paths)}</section>
        <section><h4>결과값</h4><p><b>answer</b></p>{_pre(output.get('answer', ''))}<p><b>cited_source_files</b></p>{_list(output.get('cited_source_files'))}<p><b>retrieved_source_files</b></p>{_list(retrieved)}</section>
      </div>
      <details><summary>LLM Judge</summary><p class='scores'>Overall {_score(judge.get('overall'))} · Retrieval relevance {_score(judge.get('retrieval_relevance'))} · Groundedness {_score(judge.get('groundedness'))}</p>{_pre(judge.get('rationale', ''))}<p><b>issues</b></p>{_list(judge.get('issues'))}</details>
      <div class='decision'><label>사람 판정 <select class='decision-select'><option value='pending'>검수 전</option><option value='pass'>통과</option><option value='revise'>수정 필요</option><option value='hold'>보류</option></select></label><label>메모 <textarea class='review-note' placeholder='검색 근거, 누락 사실, 잘못 섞인 문서를 적으세요.'></textarea></label></div>
    </article>"""


def build_review(golden: dict[str, Any], results: dict[str, Any]) -> str:
    source_paths = _source_paths(golden)
    summary_rows = results.get("summary_results", [])
    rag_rows = results.get("rag_results", [])
    cases = [*summary_rows, *rag_rows]
    cards = "".join(
        _summary_card(row, source_paths) if row.get("task_type") == "document_summary" else _rag_card(row, source_paths)
        for row in cases
    )
    payload = {"golden": golden, "results": results}
    aggregate = results.get("aggregate", {})
    return f"""<!doctype html>
<html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>문서요약·RAG 사람검수</title>
<style>
:root {{ color-scheme: light; font-family: -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif; color:#202124; background:#f6f7f9; }}
body {{ margin:0; }} main {{ max-width:1400px; margin:0 auto; padding:28px; }}
h1 {{ margin:0 0 8px; }} h2 {{ margin-top:36px; }} h3 {{ margin:0; font-size:17px; }} h4 {{ margin:0 0 12px; color:#334155; }}
.muted {{ color:#6b7280; }} .toolbar {{ position:sticky; top:0; z-index:2; background:rgba(246,247,249,.96); padding:12px 0; border-bottom:1px solid #d9dde5; }}
.toolbar button,.toolbar select {{ padding:8px 12px; margin-right:8px; border:1px solid #b8c0cc; border-radius:6px; background:white; cursor:pointer; }}
.summary {{ display:flex; gap:16px; flex-wrap:wrap; margin:20px 0; }} .metric {{ background:white; border:1px solid #dfe3ea; border-radius:8px; padding:12px 16px; min-width:130px; }} .metric b {{ display:block; font-size:20px; margin-top:4px; }}
.card {{ background:white; border:1px solid #dfe3ea; border-radius:10px; padding:18px; margin:14px 0; box-shadow:0 1px 2px rgba(0,0,0,.04); }} .card-head {{ display:flex; align-items:center; gap:10px; }}
.badge {{ background:#e8f0fe; color:#174ea6; border-radius:12px; padding:4px 9px; font-size:12px; }} .badge.rag {{ background:#e6f4ea; color:#137333; }} .source {{ color:#4b5563; }} code {{ font-size:11px; color:#6b7280; word-break:break-all; }}
.compare {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }} .compare section {{ border:1px solid #e5e7eb; border-radius:8px; padding:14px; min-width:0; }}
pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:#f8fafc; border:1px solid #eef0f4; border-radius:6px; padding:10px; line-height:1.5; font-size:13px; }} ul {{ padding-left:20px; line-height:1.55; }}
details {{ margin-top:14px; }} summary {{ cursor:pointer; color:#374151; font-weight:600; }} .scores {{ color:#374151; font-variant-numeric:tabular-nums; }}
table {{ width:100%; border-collapse:collapse; margin-top:12px; font-size:13px; }} th,td {{ border:1px solid #e2e8f0; padding:8px; vertical-align:top; text-align:left; }} th {{ background:#f8fafc; }} td.ok {{ color:#137333; font-weight:600; }} td.warn {{ color:#b45309; font-weight:600; }}
.decision {{ margin-top:16px; display:grid; grid-template-columns:180px 1fr; gap:12px; align-items:start; }} .decision label {{ display:grid; gap:6px; font-size:13px; font-weight:600; }} select,textarea {{ font:inherit; border:1px solid #b8c0cc; border-radius:6px; padding:8px; background:white; }} textarea {{ min-height:54px; resize:vertical; font-weight:400; }}
.hidden {{ display:none; }} @media(max-width:800px) {{ main {{ padding:16px; }} .compare {{ grid-template-columns:1fr; }} .decision {{ grid-template-columns:1fr; }} }}
</style></head><body><main>
<h1>문서요약·RAG 사람검수</h1><p class='muted'>기준값과 결과값을 비교한 뒤 사람 판정과 메모를 입력하세요. 판정과 메모는 이 브라우저의 localStorage에 자동 저장됩니다.</p>
<div class='summary'><div class='metric'>문서 수<b>{len(golden.get('source_files', []))}</b></div><div class='metric'>요약 케이스<b>{len(summary_rows)}</b></div><div class='metric'>RAG 케이스<b>{len(rag_rows)}</b></div><div class='metric'>자동 Overall<b>{_score(aggregate.get('overall'))}</b></div></div>
<div class='toolbar'><button id='save'>검수 JSON 다운로드</button><button id='clear'>이 화면의 입력 초기화</button><label>필터 <select id='filter'><option value='all'>전체</option><option value='summary'>문서요약</option><option value='rag'>RAG</option><option value='pending'>검수 전</option><option value='revise'>수정 필요</option></select></label><span id='progress' class='muted'></span></div>
<section id='cards'>{cards}</section>
<script>
const reviewKey='document-summary-review-v1';
const payload={_json_script(payload)};
const cards=[...document.querySelectorAll('.card')];
let review=JSON.parse(localStorage.getItem(reviewKey)||'{{}}');
function applyState(){{ cards.forEach(card=>{{ const id=card.dataset.caseId; const state=review[id]||{{decision:'pending',note:''}}; card.querySelector('.decision-select').value=state.decision; card.querySelector('.review-note').value=state.note||''; }}); updateProgress(); filterCards(); }}
function updateProgress(){{ const done=cards.filter(c=>(review[c.dataset.caseId]||{{}}).decision&&review[c.dataset.caseId].decision!=='pending').length; document.querySelector('#progress').textContent=`검수 완료 ${{done}}/${{cards.length}}`; }}
function saveCard(card){{ const id=card.dataset.caseId; review[id]={{decision:card.querySelector('.decision-select').value,note:card.querySelector('.review-note').value}}; localStorage.setItem(reviewKey,JSON.stringify(review)); updateProgress(); }}
cards.forEach(card=>{{ card.querySelector('.decision-select').addEventListener('change',()=>saveCard(card)); card.querySelector('.review-note').addEventListener('input',()=>saveCard(card)); }});
function filterCards(){{ const value=document.querySelector('#filter').value; cards.forEach(card=>{{ const state=(review[card.dataset.caseId]||{{decision:'pending'}}).decision; card.classList.toggle('hidden',!(value==='all'||value===card.dataset.type||value===state)); }}); }}
document.querySelector('#filter').addEventListener('change',filterCards);
document.querySelector('#clear').addEventListener('click',()=>{{ if(confirm('이 브라우저에 저장된 판정과 메모를 지울까요?')){{ localStorage.removeItem(reviewKey); review={{}}; applyState(); }} }});
document.querySelector('#save').addEventListener('click',()=>{{ const output={{generated_payload:payload, human_review:review, exported_at:new Date().toISOString()}}; const blob=new Blob([JSON.stringify(output,null,2)],{{type:'application/json'}}); const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download='document-summary-human-review.json'; a.click(); URL.revokeObjectURL(url); }});
applyState();
</script></main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    golden = json.loads((args.results_dir / "rageval_golden_set.json").read_text(encoding="utf-8"))
    results = json.loads((args.results_dir / "llm_judge_results.json").read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_review(golden, results), encoding="utf-8")
    print(json.dumps({"status": "created", "path": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

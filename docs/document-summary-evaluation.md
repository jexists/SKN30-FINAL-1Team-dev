# 문서요약·RAG 평가 실행

이 평가기는 RAGEval의 `schema summary → QRA` 흐름을 SalesLuv 자료요약 도메인에 맞게
적용하고, 생성된 케이스를 기존 문서요약 에이전트와 검색 문맥 기반 RAG 응답에 넣은 뒤
LLM-as-a-Judge로 평가한다.

기본 입력은 `test-data/briefing-rag-lite`의 합성 문서다. 생성 결과는 자동 골든셋이므로
`rageval_golden_set.json`의 원문·reference_answer·expected_source_files를 사람이 검수한
뒤 `human_review.status`를 `approved`로 바꾸고 재평가한다.

## 실행

```bash
cd backend
UV_CACHE_DIR=/private/tmp/salesluv-uv-cache uv run python scripts/document_summary_rageval.py all
```

골든셋만 먼저 만들려면:

```bash
UV_CACHE_DIR=/private/tmp/salesluv-uv-cache uv run python scripts/document_summary_rageval.py golden
```

사람 검수 후 `rageval_golden_set.json`의 `human_review.status`를 `approved`로 바꾸면,
골든셋을 다시 생성하지 않고 평가만 재실행할 수 있다.

```bash
UV_CACHE_DIR=/private/tmp/salesluv-uv-cache uv run python scripts/document_summary_rageval.py evaluate
```

생성 파일:

- `output/evals/document-summary-rageval/rageval_golden_set.json`
- `output/evals/document-summary-rageval/llm_judge_results.json`

실제 문서를 넣을 때는 파일 경로를 명시한다. 실제 문서 원문이 외부 LLM으로 전송되므로
개인정보·영업기밀의 전송 허용 여부를 먼저 확인해야 한다.

## 평가 해석

`overall`, `completeness`, `groundedness`, `retrieval_relevance`, `hallucination`,
`irrelevance`는 모두 품질 점수다. 따라서 hallucination과 irrelevance도 높을수록 좋으며,
각 점수는 모델 출력의 자동 평가 결과일 뿐 최종 사람 판정이 아니다.

문서요약은 원문 전체와 reference_answer를 비교한다. RAG는 질문, 허용된 source 파일,
검색된 청크, 생성 답변을 함께 비교한다. 특히 다른 고객사 자료와 다른 담당자 비공개
자료가 검색 근거에 섞이는지 별도로 확인한다.

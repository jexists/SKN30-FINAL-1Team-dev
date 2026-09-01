# 문서

| 문서 | 내용 |
|---|---|
| [getting-started.md](getting-started.md) | 로컬 실행과 환경 설정 |
| [technical/deploy/deployment.md](technical/deploy/deployment.md) | AWS 프론트엔드·백엔드 배포 현황, 결정 이유, 구축·운영·복구 순서 |
| [project-overview.md](project-overview.md) | 문제·시장 근거·시나리오·MVP 완료 기준을 정리한 프로젝트 개요 |
| [tech-stack.md](tech-stack.md) | 현재 사용·도입 예정 기술과 선정 이유 |
| [project-structure.md](project-structure.md) | 폴더 역할과 파일 배치 |
| [planning/](planning/) | 프로젝트 기획·요구사항 등 현재 기준본 |
| [planning/프로젝트기획서_260817.pdf](planning/프로젝트기획서_260817.pdf) | MVP 범위·완료 기준·KPI를 담은 프로젝트 기획서 |
| [planning/요구사항_정의서_260817.xlsx](planning/요구사항_정의서_260817.xlsx) | 현재 구현 범위와 후속 범위를 구분한 요구사항 정의서 |
| [planning/wbs_20260818.xlsx](planning/wbs_20260818.xlsx) | 주차별 추진 일정 WBS |
| [presentation/](presentation/) | 발표자료 작업본 |
| [presentation/SalesLuv_CassTerra_기획발표_완료.pptx](presentation/SalesLuv_CassTerra_기획발표_완료.pptx) | 기획 발표 기준본 |
| [database/](database/) | 실제 DB 구조 정리 — 테이블 목록·ERD·FK·테이블별 컬럼 |
| [database/erd.html](database/erd.html) | 브라우저로 여는 Interactive ERD (검색·확대·클릭 상세) |
| [technical/](technical/) | ERD·아키텍처 등 기술 설계 |
| [technical/머신러닝_딥러닝_학습결과서.md](technical/머신러닝_딥러닝_학습결과서.md) | 로더 연결 전 13컬럼 전처리·RF 기준선·튜닝·앙상블 학습 기록과 현재 연결 상태의 구분 |
| [technical/학습한_ML_DL_모델_산출물.md](technical/학습한_ML_DL_모델_산출물.md) | 학습 후보의 입력·저장 계약·검증 기록과 후속 연결·배포 범위 |
| [submission/](submission/) | 위 ML 보고서 두 건의 DOCX·PDF 출력본. 내용 수정 원본은 `technical/`의 MD |
| [../backend/notebooks/README.md](../backend/notebooks/README.md) | 현재 ML 노트북 실행 순서와 이전 실험 구분 |
| [../deploy/backend/README.md](../deploy/backend/README.md) | 최신 모델 연결·Linux 검증·AWS 파일 배치와 미완료 배포 범위의 기준 |
| [technical/SalesLuv_ERD.md](technical/SalesLuv_ERD.md) | 실제 테이블·컬럼 이름을 기준으로 한 SalesLuv ERD |
| [technical/데이터베이스_저장소_설계_문서_260817.docx](technical/데이터베이스_저장소_설계_문서_260817.docx) | 타입·NULL·FK·제약·적용 이력을 포함한 상세 DB 설계서 |
| [technical/multiagent/](technical/multiagent/) | 멀티에이전트 운영 문서 모음 |
| [technical/multiagent/SalesLuv_멀티에이전트_운영_플로우.html](technical/multiagent/SalesLuv_멀티에이전트_운영_플로우.html) | SalesLuv 멀티에이전트 운영 흐름 다이어그램 |
| [technical/multiagent/SalesLuv_멀티에이전트_운영_설명서.docx](technical/multiagent/SalesLuv_멀티에이전트_운영_설명서.docx) | 5개 에이전트의 역할과 상호작용 설명서 |
| [technical/multiagent/미팅_보고서_계약_일정_Agent_흐름.md](technical/multiagent/미팅_보고서_계약_일정_Agent_흐름.md) | 미팅분석부터 계약관리 재진입까지 단계별 흐름 |
| [technical/multiagent/계약에이전트_설계.md](technical/multiagent/계약에이전트_설계.md) | 계약관리 에이전트의 목표·지침·1차 실행/재진입 실행 설계 |
| [technical/multiagent/일정관리에이전트_설계.md](technical/multiagent/일정관리에이전트_설계.md) | 일정관리 에이전트의 입력·출력·서버 재검증. 계약관리 실행을 `parent_run_id`로 이어받는 단방향 인계 |
| [technical/backend/api-conventions.md](technical/backend/api-conventions.md) | SalesLuv 최종 API 공통 규약 |
| [technical/영업_파이프라인_프론트_연동_제안서.md](technical/영업_파이프라인_프론트_연동_제안서.md) | 프론트에 전달할 기능 역할·데이터·API 계약 |
| [research/](research/) | 실험·비교·검토 결과 |
| [research/crm/README.md](research/crm/README.md) | CRM 시장·경쟁사·제품 결정·사용자 의견 문서 안내 |
| [meetings/](meetings/) | 날짜별 회의록 |
| [references/](references/) | 외부 제공 원본과 제출 양식 안내 |
| [../final/](../final/) | 제출이 끝난 발표자료·보고서 |
| [../backend/sql/README.md](../backend/sql/README.md) | DB 스키마 변경 절차 |
| [../AGENTS.md](../AGENTS.md) | 개발 규칙 단일 원본 |

실제 DB 구조의 최신 기준은 `docs/database/` 입니다. `technical/SalesLuv_ERD.md` 와
`데이터베이스_저장소_설계_문서_260817.docx` 는 2026-08-19 baseline(26테이블) 시점의 문서로 남겨 둡니다. 같은 내용을 여러 문서에 복사하지 않습니다. 외부 원본은 수정하지 않고, 작업본은 목적에 맞는 폴더에 둡니다. 진행 중 문서는 `docs/`, 제출 완료본은 `final/`에만 둡니다.

회의록 파일명은 `YYYY-MM-DD-topic.md`를 사용합니다. 외부 제공 파일은 공개 재배포 허가와 개인정보·메타데이터 검토가 끝난 뒤에만 Git에 추가합니다.

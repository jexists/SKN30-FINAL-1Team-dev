# SalesLuv AI 업무 여정 데모 영상 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 고객 등록부터 AI 문서 요약·미팅 브리핑·AI 보고서 초안까지의 실제 SalesLuv 업무 흐름을 60초 미만 QHD MP4 데모 영상으로 제작한다.

**Architecture:** 실제 로컬 SalesLuv 앱을 Playwright CLI로 QHD 뷰포트에서 조작·캡처한다. 편집 단계에서 제목 카드, spotlight·바운딩 박스·라벨, 중앙 하단 한국어 자막, 안전한 배경음악을 합성하고, MP4 메타데이터와 시청 검수로 결과를 검증한다.

**Tech Stack:** React/Vite/FastAPI 로컬 앱, Playwright CLI, FFmpeg/FFprobe(영상 합성·검증), H.264 MP4.

---

## 산출물 구조

- Create: `output/playwright/salesluv-ai-workflow/raw/scene-01.png` … `scene-06.png` — 원본 브라우저 캡처 및 스크린샷
- Create: `output/playwright/salesluv-ai-workflow/assets/` — 제목 카드·자막·강조 레이어·음악의 편집 입력물
- Create: `output/playwright/salesluv-ai-workflow/final/salesluv-ai-workflow-demo-qhd.mp4` — 최종 제출 영상
- Create: `output/playwright/salesluv-ai-workflow/verification.txt` — 길이·해상도·코덱 확인 결과
- Modify: 없음. 기존 제품 코드와 사용자의 미커밋 변경은 수정하지 않는다.

### Task 1: 녹화 환경과 안전한 데모 상태 확인

**Files:**
- Create: `output/playwright/salesluv-ai-workflow/verification.txt`
- Read: `frontend/src/constants/routes.ts`
- Read: `scripts/dev.sh`, `scripts/frontend.sh`, `scripts/backend.sh`

- [ ] **Step 1: 영상 도구와 로컬 서비스 상태를 확인한다.**

Run:

```bash
command -v npx
command -v ffmpeg
command -v ffprobe
curl -fsS -o /dev/null -w 'frontend %{http_code}\n' http://localhost:5173/
curl -fsS -o /dev/null -w 'backend %{http_code}\n' http://localhost:8000/api/health
```

Expected: `npx`, `ffmpeg`, `ffprobe`가 각각 발견되고 프론트·백엔드가 모두 `200`이다. 누락된 비디오 도구나 서버는 이후 단계를 시작하지 않고, 설치·기동의 영향 범위를 사용자에게 알린다.

- [ ] **Step 2: 기존 변경과 비밀 노출 위험을 확인한다.**

Run:

```bash
git status --short
rg -n --hidden -g '!node_modules' -g '!.git' '(API_KEY|SECRET|PASSWORD|TOKEN)' frontend backend | head -80
```

Expected: 기존 변경을 목록으로만 확인한다. 화면·영상·로그에 비밀값을 기록하지 않으며, 실제 고객 개인정보 또는 미승인 원본 데이터가 보이면 데모 시드를 사용하거나 화면에서 제외한다.

- [ ] **Step 3: 촬영용 디렉터리를 만든다.**

Run:

```bash
mkdir -p output/playwright/salesluv-ai-workflow/{raw,assets,final}
```

Expected: 산출물이 `output/playwright/salesluv-ai-workflow/` 내부에만 생성된다.

### Task 2: 실제 화면과 기록 가능한 흐름 확정

**Files:**
- Read: `frontend/src/App.tsx`
- Read: `frontend/src/pages/Customers/Customers.tsx`
- Read: `frontend/src/pages/Documents/Documents.tsx`
- Read: `frontend/src/pages/Meetings/Compose.tsx`
- Read: `frontend/src/pages/Daily/Compose.tsx`
- Create: `output/playwright/salesluv-ai-workflow/raw/shot-list.md`

- [ ] **Step 1: QHD Playwright 세션을 시작하고 로그인 화면을 확인한다.**

Run:

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export PWCLI="$CODEX_HOME/skills/playwright/scripts/playwright_cli.sh"
"$PWCLI" --session salesluv-demo open http://localhost:5173 --headed
"$PWCLI" --session salesluv-demo resize 2560 1440
"$PWCLI" --session salesluv-demo snapshot
```

Expected: 최신 snapshot에서 로그인 또는 첫 화면의 안정된 요소 참조를 확인한다. 이후 click/fill은 바로 직전 snapshot의 참조만 사용한다.

- [ ] **Step 2: 데모 계정으로 로그인하고 4개 화면의 데이터 준비 상태를 확인한다.**

Run:

```bash
"$PWCLI" --session salesluv-demo snapshot
```

최신 snapshot에서 `팀장으로 로그인` 버튼에 할당된 참조를 찾아 그 참조로 한 번 클릭한다. 이 로컬 빠른 로그인은 소스에 정의된 `jungia21@naver.com` 계정과 고정 개발 비밀번호를 앱 내부에서 사용하므로, 비밀번호를 명령줄·로그·영상에 노출하지 않는다. 클릭 직후 다시 snapshot을 만든다.

Expected: 고객 등록, 자료실 요약, 미팅 브리핑, 보고서 초안의 실제 화면에 도달한다. 로그인 자격 증명은 터미널 출력·영상·문서에 저장하지 않는다.

- [ ] **Step 3: 위험 없는 데이터로 시연 가능 여부를 결정하고 촬영 목록을 작성한다.**

`raw/shot-list.md`에 아래 6개 컷과 대응 라우트·클릭 대상·예상 길이를 기록한다.

```markdown
| 컷 | 목표 길이 | 화면 목적 | 실제 조작 |
| --- | ---: | --- | --- |
| 01 | 0–10초 | 프로젝트 동기 | 제목 카드 |
| 02 | 10–18초 | 해결 흐름 | 고객 → 요약 → 브리핑 → 보고서 오버레이 |
| 03 | 18–30초 | 고객 등록 | 고객 목록에서 등록 폼을 열어 필수 항목을 채우고 저장 전까지 표시 |
| 04 | 30–41초 | AI 문서 요약 | 자료실에서 데모 문서를 열고 AI 요약 결과를 표시 |
| 05 | 41–51초 | AI 브리핑 | 미팅 화면에서 목표·확인 질문·과거 이력을 표시 |
| 06 | 51–59초 | AI 보고서 | 보고서 초안·검토 가능한 수정 영역을 표시 |
```

Expected: 실제 새 고객·문서·보고서를 영구 저장하는 동작은 피한다. 기존에 안전한 데모 데이터가 없고 생성이 필요한 경우, 정확한 대상과 생성 범위를 사용자에게 확인받는다.

### Task 3: QHD 원본 캡처

**Files:**
- Create: `output/playwright/salesluv-ai-workflow/raw/scene-01.png`
- Create: `output/playwright/salesluv-ai-workflow/raw/scene-02.png`
- Create: `output/playwright/salesluv-ai-workflow/raw/scene-03.png`
- Create: `output/playwright/salesluv-ai-workflow/raw/scene-04.png`
- Create: `output/playwright/salesluv-ai-workflow/raw/scene-05.png`
- Create: `output/playwright/salesluv-ai-workflow/raw/scene-06.png`

- [ ] **Step 1: 각 화면의 정지 검수용 QHD 스크린샷을 저장한다.**

Run:

```bash
"$PWCLI" --session salesluv-demo screenshot
mv screenshot.png output/playwright/salesluv-ai-workflow/raw/scene-03.png
```

Expected: 고객 등록 장면을 `scene-03.png`로 저장한다. 같은 명령을 문서 요약·브리핑·보고서·전체 흐름의 최신 화면마다 반복해 `scene-01.png`부터 `scene-06.png`까지 채운다. 메뉴·브라우저 크롬·로딩 오류가 화면을 가리지 않아야 한다.

- [ ] **Step 2: 실제 UI 동작을 컷별로 캡처한다.**

각 컷에서 snapshot → 최신 참조로 클릭·입력 → snapshot 순서를 지키며 다음 변화만 기록한다: 고객 등록 폼 열기·필수 정보 채우기, 문서와 요약 패널 열기, 브리핑의 세 섹션 표시, 보고서 초안·검토 영역 표시.

Expected: AI 처리 시간은 영상에서 대기시키지 않는다. 이미 생성된 안전한 결과를 표시하거나, 2–4배속으로 잘라 낸다.

- [ ] **Step 3: 원본 화면의 내용·해상도를 검수한다.**

Run:

```bash
find output/playwright/salesluv-ai-workflow/raw -maxdepth 1 -type f -print
```

Expected: 4개 핵심 기능 각각에 사용할 수 있는 선명한 QHD 원본이 있고, 개인정보·비밀·오류 토스트가 없다.

### Task 4: 자막·spotlight·라벨 편집 레이어 제작 및 합성

**Files:**
- Create: `output/playwright/salesluv-ai-workflow/assets/edit-decision-list.md`
- Create: `output/playwright/salesluv-ai-workflow/assets/subtitles.ass`
- Create: `output/playwright/salesluv-ai-workflow/assets/overlay-01.png` … `overlay-06.png`
- Create: `output/playwright/salesluv-ai-workflow/assets/concat.txt`
- Create: `output/playwright/salesluv-ai-workflow/final/salesluv-ai-workflow-demo-qhd.mp4`

- [ ] **Step 1: 컷별 시간·자막·강조 위치를 EDL에 고정한다.**

`assets/edit-decision-list.md`에 다음 텍스트를 사용한다.

```markdown
00:00–00:10 고객 정보와 영업 기록이 여러 도구에 흩어져 있습니다.
00:10–00:18 SalesLuv는 고객 맥락을 연결하고, AI 초안을 사람의 검토로 업무에 반영합니다.
00:18–00:30 신규 고객 정보는 팀이 함께 쓰는 영업 맥락으로 저장됩니다.
00:30–00:41 AI가 핵심 제품 정보와 영업 포인트를 빠르게 정리합니다.
00:41–00:51 미팅 전에는 고객 이력과 자료를 바탕으로 준비할 내용을 제안합니다.
00:51–00:59 미팅 후에는 근거 기반 초안을 검토해 다음 업무로 연결합니다.
```

Expected: 총 재생 시간은 59초 이하다. 모든 자막은 중앙 하단 안전 영역에 1~2줄로 제한한다.

- [ ] **Step 2: 스포트라이트와 설명 라벨을 각 핵심 컷에 배치한다.**

각 장면에 어두운 반투명 마스크, 청록색(예: `#21D4C2`) 3px 바운딩 박스, 짧은 한국어 라벨을 넣는다.

```markdown
고객 등록: "고객 기본 정보" / "팀 공유 맥락"
문서 요약: "원본 문서" / "AI 핵심 요약"
브리핑: "미팅 목표" / "확인 질문" / "과거 이력"
보고서: "AI 초안" / "검토·수정 후 확정"
```

Expected: 라벨이 강조 대상 또는 중앙 하단 자막을 가리지 않는다.

- [ ] **Step 3: 2560×1440 H.264 MP4로 합성한다.**

Run:

```bash
ffmpeg -y -loop 1 -t 10 -i output/playwright/salesluv-ai-workflow/raw/scene-01.png -r 30 -pix_fmt yuv420p output/playwright/salesluv-ai-workflow/raw/scene-01.mp4
ffmpeg -y -loop 1 -t 8  -i output/playwright/salesluv-ai-workflow/raw/scene-02.png -r 30 -pix_fmt yuv420p output/playwright/salesluv-ai-workflow/raw/scene-02.mp4
ffmpeg -y -loop 1 -t 12 -i output/playwright/salesluv-ai-workflow/raw/scene-03.png -r 30 -pix_fmt yuv420p output/playwright/salesluv-ai-workflow/raw/scene-03.mp4
ffmpeg -y -loop 1 -t 11 -i output/playwright/salesluv-ai-workflow/raw/scene-04.png -r 30 -pix_fmt yuv420p output/playwright/salesluv-ai-workflow/raw/scene-04.mp4
ffmpeg -y -loop 1 -t 10 -i output/playwright/salesluv-ai-workflow/raw/scene-05.png -r 30 -pix_fmt yuv420p output/playwright/salesluv-ai-workflow/raw/scene-05.mp4
ffmpeg -y -loop 1 -t 8  -i output/playwright/salesluv-ai-workflow/raw/scene-06.png -r 30 -pix_fmt yuv420p output/playwright/salesluv-ai-workflow/raw/scene-06.mp4
printf "file 'raw/scene-01.mp4'\nfile 'raw/scene-02.mp4'\nfile 'raw/scene-03.mp4'\nfile 'raw/scene-04.mp4'\nfile 'raw/scene-05.mp4'\nfile 'raw/scene-06.mp4'\n" > output/playwright/salesluv-ai-workflow/assets/concat.txt
(cd output/playwright/salesluv-ai-workflow && ffmpeg -y -f concat -safe 0 -i assets/concat.txt -vf "subtitles=assets/subtitles.ass" -r 30 -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart -an final/assembled.mp4)
ffmpeg -y -i output/playwright/salesluv-ai-workflow/final/assembled.mp4 \
  -vf "scale=2560:1440:force_original_aspect_ratio=decrease,pad=2560:1440:(ow-iw)/2:(oh-ih)/2" \
  -r 30 -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart -an \
  output/playwright/salesluv-ai-workflow/final/salesluv-ai-workflow-demo-qhd.mp4
```

Expected: 2560×1440, 30fps, H.264 MP4가 생성된다. 배경음악은 사용 권리가 분명한 파일만 포함한다; 확보하지 못하면 무음으로 제출한다.

### Task 5: 재생·메타데이터·시각 품질 검증

**Files:**
- Create: `output/playwright/salesluv-ai-workflow/verification.txt`
- Read: `output/playwright/salesluv-ai-workflow/final/salesluv-ai-workflow-demo-qhd.mp4`

- [ ] **Step 1: 길이·해상도·코덱을 기록한다.**

Run:

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name,codec_type,width,height,r_frame_rate \
  -of default=noprint_wrappers=1 \
  output/playwright/salesluv-ai-workflow/final/salesluv-ai-workflow-demo-qhd.mp4 \
  | tee output/playwright/salesluv-ai-workflow/verification.txt
```

Expected: duration `< 60`, video `h264`, width `2560`, height `1440`, frame rate `30/1` 또는 동등 값이 확인된다. 이 계획의 기본 산출물은 무음이다.

- [ ] **Step 2: 6개 시점의 프레임을 추출해 눈으로 검수한다.**

Run:

```bash
for t in 3 13 23 35 45 55; do
  ffmpeg -y -ss "$t" -i output/playwright/salesluv-ai-workflow/final/salesluv-ai-workflow-demo-qhd.mp4 \
    -frames:v 1 "output/playwright/salesluv-ai-workflow/final/frame-${t}.png"
done
```

Expected: 0–10초 동기, 10–18초 해결, 18–59초 실제 데모 4장면이 모두 나타나며 spotlight·바운딩 박스·라벨·한국어 자막이 겹치지 않고 읽힌다.

- [ ] **Step 3: 최종 재생을 확인하고 전달한다.**

Run:

```bash
ls -lh output/playwright/salesluv-ai-workflow/final/salesluv-ai-workflow-demo-qhd.mp4
cat output/playwright/salesluv-ai-workflow/verification.txt
```

Expected: 재생 가능한 최종 MP4 한 개와 검증 기록이 남는다. 미디어 링크와 파일 경로, 미실행 검사 또는 승인 대기 사항을 사용자에게 간결히 전달한다.

# SalesLuv 프론트엔드·백엔드 배포 정리

> 기준: 2026-08-23 21:07 KST
>
> 운영 브랜치: `develop`
>
> 현재 배포 커밋: `7659b9d03b3c08cafd40ca285a445461ca691c30`

## 1. 현재 상태

| 구분 | 상태 | 주소·방식 |
|---|---|---|
| 프론트엔드 | 배포 성공 | <https://d3m90og33enu6v.cloudfront.net> |
| 백엔드 | 배포 성공 | 같은 주소의 `/api/*` |
| 데이터베이스 | 연결 정상 | `/api/health/db` HTTP 200 |
| 배포 방식 | 수동 | GitHub Actions의 Frontend·Backend 버튼 분리 |
| 배포 브랜치 | 제한 | `develop`만 production 배포 가능 |
| 커스텀 도메인 | 미적용 | CloudFront 기본 도메인 사용 |

최종 확인 결과:

- `/` → HTTP 200
- `/login` → HTTP 200, SPA 직접 진입 정상
- `/api/health` → `{"status":"ok"}`
- `/api/health/db` → `{"status":"ok","database":"connected"}`

## 2. 전체 구조

```text
사용자
  └─ HTTPS
      └─ CloudFront
          ├─ 일반 경로 ──> Private S3 ──> React/Vite
          └─ /api/* ────> EC2:80 ──> Nginx
                                      ├─ Docker :8000
                                      └─ Docker :18000
                                             └─ Supabase DB/Auth/Storage

GitHub Actions
  └─ OIDC ──> AWS IAM Role
      ├─ Frontend: SSM 조회 → build → S3 업로드 → CloudFront 무효화
      └─ Backend : SSM 명령 → EC2 build → 새 슬롯 검사 → Nginx 전환
```

### 요청 경로

| 요청 | 처리 |
|---|---|
| `/`, `/login`, `/customers` 등 | CloudFront → S3 |
| 확장자 없는 화면 경로 | CloudFront Function → `/index.html` |
| `/assets/*` | S3 정적 자산 |
| `/api/*` | CloudFront → EC2 HTTP 80 → Nginx → FastAPI |

브라우저에서 CloudFront까지는 HTTPS다. CloudFront에서 EC2까지는 현재 HTTP 80이다.

## 3. 구성 선택 이유

| 선택 | 이유 |
|---|---|
| S3 + CloudFront 프론트엔드 | 정적 Vite 결과물의 단순한 배포, CDN·HTTPS 사용 |
| 단일 EC2 + Docker 백엔드 | 첫 운영 배포의 비용과 구성 복잡도 최소화 |
| Frontend·Backend 수동 버튼 분리 | 변경된 영역만 배포하고 배포 순서를 직접 통제 |
| `develop` 전용 배포 | 임의 브랜치의 production 배포 방지 |
| GitHub OIDC | 장기 AWS Access Key 저장 방지 |
| 동일 CloudFront 주소의 `/api/*` | CORS, mixed content, Secure/SameSite cookie 문제 단순화 |
| Backend 두 슬롯 | 새 버전 검사 후 트래픽 전환, 전환 실패 시 이전 버전 복구 |
| Frontend 최근 3세대 자산 보존 | 열린 브라우저의 이전 JS/CSS 요청 보호 |
| Backend 우선 배포 | 새 frontend가 아직 없는 API를 먼저 호출하는 상황 방지 |
| Redis·Celery·별도 AI 인프라 후순위 | 첫 배포 범위와 장애 지점 최소화 |

## 4. 운영 리소스

### 공통

| 항목 | 값 |
|---|---|
| AWS 리전 | `ap-northeast-2` |
| AWS 계정 | `816008167575` |
| GitHub 환경 | `production` |
| 허용 브랜치 | `develop` |
| 인증 | GitHub OIDC |
| OIDC subject | `repo:jexists/SKN30-FINAL-1Team-dev:environment:production` |
| 배포 알림 | Discord `DISCORD_WEBHOOK_URL` |

### 프론트엔드

| 항목 | 값·설정 |
|---|---|
| S3 버킷 | `salesluv-frontend-prod-816008167575-ap-northeast-2-an` |
| S3 접근 | Public 차단, ACL 비활성화, CloudFront OAC |
| S3 보호 | Versioning, SSE-S3 |
| S3 Lifecycle | 이전 version 14일, 최근 3개 유지, delete marker 정리, multipart 7일 정리 |
| CloudFront | `salesluv-frontend-prod` |
| Distribution ID | `E27EQ7X9F57Z1P` |
| 기본 도메인 | `d3m90og33enu6v.cloudfront.net` |
| 기본 origin | Private S3 |
| API origin | `salesluv-backend-ec2`, EC2 public DNS, HTTP 80 |
| API behavior | `/api/*`, cache 비활성화, 모든 API 메서드 허용 |
| SPA Function | `salesluv-spa-rewrite` |
| Frontend IAM Role | `SalesLuvFrontendDeployRole` |
| Frontend IAM Policy | `SalesLuvFrontendDeployPolicy` |
| Frontend SSM | `/salesluv/production/frontend/env` |
| WAF | 미적용 |

### 백엔드

| 항목 | 값·설정 |
|---|---|
| EC2 이름 | `salesluv-backend` |
| Instance ID | `i-0464d8283887dd6f5` |
| Elastic IP | `15.165.218.167` |
| Public DNS | `ec2-15-165-218-167.ap-northeast-2.compute.amazonaws.com` |
| Security Group | `sg-05a683084c82f8eb0` |
| CloudFront Prefix List | `pl-22a6434b`, HTTP 80 허용 |
| Backend IAM Role | `salesluv-github-actions-deploy-role` |
| Backend SSM | `/salesluv/production/backend/env` |
| EC2 저장소 | `/opt/salesluv` |
| Runtime env | `/opt/salesluv/runtime/backend.env`, `0600` |
| Release 경로 | `/opt/salesluv-releases` |
| Deploy lock | `/var/lock/salesluv-backend-deploy.lock` |
| Nginx upstream | `/etc/nginx/conf.d/salesluv-backend-upstream.conf` |
| 슬롯 | `127.0.0.1:8000`, `127.0.0.1:18000` |
| 컨테이너 | `salesluv-backend-8000`, `salesluv-backend-18000` |

## 5. 최초 설정 순서

### 5.1 배포 범위

1. React frontend, FastAPI backend, Supabase 연결만 우선 배포.
2. 수동 배포, `develop` 제한, Backend 우선 순서 결정.
3. Redis/Celery, 별도 OCR·AI 서버, custom domain, origin TLS 제외.

### 5.2 Backend Docker

1. Python 3.13·uv `0.12.5` 기반 image 구성.
2. `uv sync --frozen --no-dev`로 lockfile 의존성 설치.
3. 앱 코드만 복사, UID/GID `10001` non-root 실행.
4. Uvicorn 단일 worker, 내부 port 8000 설정.
5. `.env`, 테스트, SQL, script를 image context에서 제외.

### 5.3 EC2·Nginx

1. Docker, Nginx, Git, AWS CLI, curl, SSM Agent 준비.
2. `/opt/salesluv` 저장소와 `origin/develop` 준비.
3. Nginx `proxy_pass`를 `http://salesluv_backend`로 변경.
4. upstream 파일에 `127.0.0.1:8000` 또는 `:18000` 하나만 지정.
5. 파일 권한 설정 후 `nginx -t`, reload, local health 확인.
6. CloudFront origin-facing Prefix List를 Security Group HTTP 80에 추가.

### 5.4 S3·CloudFront

1. Private S3, Public 차단, OAC, Versioning, SSE-S3 설정.
2. 오래된 object version lifecycle 설정.
3. CloudFront 기본 S3 origin과 root object `index.html` 설정.
4. `salesluv-spa-rewrite` Function 생성·게시·기본 behavior 연결.
5. EC2 public DNS를 API origin으로 추가.
6. `/api/*` behavior를 cache 없이 API origin에 연결.
7. Frontend·Backend CORS/API 주소를 같은 CloudFront origin으로 통일.

### 5.5 IAM·GitHub

1. GitHub OIDC Provider 연결.
2. Frontend·Backend 배포 Role 분리.
3. Frontend Role에 S3, CloudFront invalidation, Frontend SSM 최소 권한 부여.
4. Role trust를 저장소와 `production` environment subject로 제한.
5. GitHub `production` environment와 `develop` 보호 설정.
6. Frontend·Backend workflow 생성 후 PR #58로 병합.

## 6. 일반 배포 순서

### 6.1 배포 전 확인

- [ ] 변경사항 `develop` 병합
- [ ] 배포 SHA 확인
- [ ] Frontend·Backend CI 통과 확인
- [ ] DB schema 변경 시 production SQL 선적용
- [ ] SSM 설정 변경 시 이전 값 백업
- [ ] `VITE_API_BASE_URL`과 `CORS_ORIGINS` 동일 origin 확인
- [ ] 딜 승산 모델 교체 시 [단일 파일·해시·권한·로더 배포 전제](../../../deploy/backend/README.md) 확인

배포 workflow는 CI 성공을 자동 확인하지 않는다. 운영자가 먼저 확인해야 한다.

### 6.2 Backend 배포

GitHub → **Actions → Deploy Backend → Run workflow → develop**

```bash
gh workflow run deploy-backend.yml --ref develop
```

내부 처리 순서:

1. `develop` 검사.
2. OIDC로 Backend IAM Role 획득.
3. SSM `AWS-RunShellScript`를 EC2에 전달.
4. EC2의 `origin/develop`과 `GITHUB_SHA` 정확 일치 검사.
5. 해당 SHA의 `deploy/backend/deploy.sh`만 추출.
6. GitHub concurrency와 host `flock`으로 중복 배포 차단.
7. 현재 Nginx port와 활성 컨테이너 판별.
8. Backend SSM env 복호화·검증·원자 교체.
9. 해당 SHA의 backend만 `git archive`로 분리.
10. EC2 BuildKit으로 `salesluv-backend:<SHA>` 로컬 빌드.
11. 비활성 port에 새 컨테이너 실행.
12. `/api/health`, `/api/health/db` 최대 30회 확인.
13. 성공 시 Nginx upstream port 변경.
14. `nginx -t`, reload, 새 upstream 재확인.
15. 이전 슬롯 10초 drain, 30초 stop, 컨테이너 삭제.
16. 현재·직전 image 보존, 오래된 image 정리.
17. Discord 성공·실패 알림.

Backend 확인:

```bash
curl -fsS https://d3m90og33enu6v.cloudfront.net/api/health
curl -fsS https://d3m90og33enu6v.cloudfront.net/api/health/db
```

### 6.3 Frontend 배포

GitHub → **Actions → Deploy Frontend → Run workflow → develop**

```bash
gh workflow run deploy-frontend.yml --ref develop
```

내부 처리 순서:

1. `develop` 검사.
2. OIDC로 Frontend IAM Role 획득.
3. Frontend SSM env 복호화·검증.
4. `VITE_*`만 허용, `VITE_API_BASE_URL` 필수 확인.
5. Node 24, `npm ci`, `tsc -b && vite build`.
6. `frontend/dist` artifact 업로드·다운로드, 보존 1일.
7. `dist/index.html`, `dist/assets` 구조 확인.
8. `assets/`를 먼저 업로드, `1년 immutable` cache 적용.
9. root 파일 `sync --delete`, `no-cache/no-store` 적용.
10. CloudFront `/*` invalidation 생성.
11. release marker 생성.
12. 최신 3세대보다 오래된 asset·marker만 안전한 prefix에서 삭제.
13. Discord 성공·실패 알림.

### 6.4 통합 확인

- [ ] `/` HTTP 200
- [ ] `/login` 직접 진입·새로고침 HTTP 200
- [ ] JS/CSS chunk 오류 없음
- [ ] 로그인·API 호출 정상
- [ ] 새로고침 후 session 복원
- [ ] 변경 화면·API 최소 1건 실행
- [ ] GitHub Actions deploy job 성공

## 7. 환경변수

### Frontend SSM

| 이름 | 구분 |
|---|---|
| `VITE_API_BASE_URL` | 필수, 현재 CloudFront origin |
| 기타 `VITE_*` | 선택, browser 공개값만 허용 |

`VITE_*`는 build 결과에 포함된다. API Key·비밀번호·Token 저장 금지.

### Backend SSM

| 구분 | 이름 |
|---|---|
| 필수 | `APP_ENV`, `DEBUG`, `CORS_ORIGINS`, `DATABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` |
| Login | `LOGIN_MAX_ATTEMPTS`, `LOGIN_WINDOW_SECONDS`, `REFRESH_COOKIE_MAX_AGE_SECONDS` |
| Storage | `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_STORAGE_BUCKET`, `UPLOAD_MAX_BYTES` |
| LLM | `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS` |
| STT | `STT_API_KEY`, `STT_MODEL`, `STT_TIMEOUT_SECONDS`, `STT_MAX_BYTES` |

운영 필수값은 `APP_ENV=production`, `DEBUG=false`, HTTPS `CORS_ORIGINS`다. Storage·LLM·STT 값은 배포 필수가 아니므로 누락 상태에서도 기본 health는 성공할 수 있다.

## 8. 복구 순서

### Backend 배포 도중 실패

1. 후보 health 전 실패 → production upstream 유지.
2. env 교체 후 실패 → 이전 env 복원.
3. Nginx 전환 중 실패 → 이전 upstream·env 복원.
4. 이전 슬롯 health 재확인.
5. 후보 컨테이너·새 image 정리.
6. 원인 수정 commit 생성 후 재배포.

### Backend 성공 후 장애

과거 SHA 선택과 one-click rollback은 없다.

1. 추가 배포 중단.
2. 문제 commit을 `develop`에서 revert하는 새 commit 생성.
3. CI 확인.
4. Backend 재배포.
5. API·DB·로그인 확인.
6. API 계약 변경 시 Frontend 재배포.

### Frontend 장애

1. 정상 commit을 `develop`에 revert.
2. Frontend 재배포.
3. 긴급 S3 복원 시 정상 `index.html`·root object version 복원.
4. CloudFront `/*` invalidation.
5. 화면·deep link·chunk·로그인 확인.

최근 3세대 asset 보존은 rollback 기능이 아니다. 이전 `index.html` 복원이 함께 필요하다.

## 9. 현재 제한사항

| 항목 | 현재 상태 |
|---|---|
| Custom domain·ACM | 없음 |
| CloudFront → EC2 TLS | 없음, HTTP 80 |
| WAF | 없음 |
| DB migration | 수동, deploy에 포함되지 않음 |
| Production migration 기록 | 저장소에 없음 |
| Post-deploy smoke | 자동화 없음 |
| CloudFront invalidation 완료 대기 | 없음 |
| CI 성공 강제 | 없음 |
| 과거 SHA rollback | 없음 |
| IaC | 없음 |
| 중앙 로그·APM·외부 uptime | 없음 |
| Docker resource limit·HEALTHCHECK | 없음 |
| HA | 단일 EC2이므로 없음 |
| Background job 복구 | process 내부 작업이므로 재시작 시 유실 가능 |
| 실제 사용자 IP 전달 | Nginx·Uvicorn proxy 설정 확인 필요 |
| Storage·LLM·STT | 기능별 smoke 필요 |

## 10. 다음 우선순위

1. 배포 후 `/`, `/login`, API, DB, 로그인 자동 확인.
2. CloudFront invalidation 완료 대기.
3. 동일 SHA CI 성공을 배포 조건으로 연결.
4. Production DB migration 기록·RLS 검증.
5. Custom domain·ACM·origin HTTPS.
6. 표준 rollback workflow.
7. CloudWatch/APM·외부 uptime 경보.
8. Terraform 또는 CloudFormation 기반 IaC.

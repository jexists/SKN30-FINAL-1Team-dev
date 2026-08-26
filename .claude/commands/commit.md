---
description: 현재 브랜치에서 변경을 기능별로 나눠 커밋 (push·PR 없음)
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git add:*), Bash(git commit:*), Bash(git ls-files:*), Bash(cd:*), Bash(uv run:*), Bash(npm run:*), Bash(npx prettier:*), Read, Edit
---

# 커밋

현재 브랜치의 변경을 기능별로 나눠 커밋한다. **커밋까지만.**
인자 `$ARGUMENTS`: 커밋 범위·의도 힌트 (없어도 됨)

> 이 파일이 `.agent-rules/git.md`의 커밋 절차 요약이다. 그 문서는 읽지 않는다.

## 1. 파악

```bash
git status --short --branch
git diff --stat && git diff && git diff --cached
git ls-files --others --exclude-standard
```

## 2. 분리 · staging

- 커밋 하나 = 독립적으로 리뷰·되돌릴 수 있는 의도 하나
- `git add -- <명시 경로>`만. `git add .` / `-A` 금지
- 한 hunk에 다른 작업이 섞여 분리 불가 → **중단하고 확인**
- 관련 없는 변경은 그대로 두고 5단계 보고에 남긴다
- 제외: `.env*`, `settings.local.json`, `__pycache__/`, `.venv/`, `node_modules/`,
  `.ruff_cache/`, `.pytest_cache/`, `dist/`, 실제 고객·영업 데이터
  (`.claude/commands/`, `.claude/settings.json`은 추적 대상 → 포함)

## 3. 검사 (해당 범위만)

```bash
cd backend && uv run ruff check . && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm run format:check
git diff --cached --check
```

포맷은 편집 직후 hook이 파일 단위로 처리한다. `npm run format`은 `src` 전체를 다시 쓰므로
**쓰지 않는다.** check 실패 시 그 파일만 `npx prettier --write`.
못 돌린 검사·실패한 검사는 숨기지 않고 보고.

## 4. 커밋

```bash
git commit -m "$(cat <<'EOF'
<type>[(scope)]: <한글 요약>

바뀌기 전 동작과 문제를 먼저, 그다음 해결.

- 파일·모듈 단위 세부 변경
- 이번 변경으로 지운 것

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

type: `feat` `fix` `docs` `refactor` `test` `perf` `build` `ci` `chore`
(호환성 파괴는 `!` + `BREAKING CHANGE:` footer)
본문 분량은 `git show 6621b87` 참고. 빈 커밋 금지.

## 5. 확인 · 보고

`git show --stat --oneline HEAD`, `git status --short --branch`
→ 커밋 해시·메시지 / 검사 결과 / 남겨 둔 변경

## 금지

- push, PR, 머지, 브랜치 생성·삭제, 태그 → 필요하면 `/pr`
- `--amend`, rebase, squash, force push
- 정리 목적의 `reset` `restore` `checkout` `clean` `stash`
- 현재 브랜치가 `develop`이어도 그대로 커밋한다 (push는 안 하므로 안전)

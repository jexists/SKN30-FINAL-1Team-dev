---
description: 변경 내용을 보고 브랜치 생성 → 기능별 커밋 → push → PR 생성
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git add:*), Bash(git commit:*), Bash(git branch:*), Bash(git checkout:*), Bash(git fetch:*), Bash(git push:*), Bash(git rev-parse:*), Bash(git ls-remote:*), Bash(git ls-files:*), Bash(gh pr create:*), Bash(gh pr list:*), Bash(gh api user:*), Bash(cd:*), Bash(uv run:*), Bash(npm run:*), Bash(npx prettier:*), Read, Edit
---

# 브랜치 · 커밋 · PR

브랜치 1개 + 기능별 커밋 N개 + `develop` 대상 PR 1개.
인자 `$ARGUMENTS`: 작업 배경 (없어도 됨)

> 이 파일이 `.agent-rules/git.md`·`branching.md`의 요약이다. 두 문서는 읽지 않는다.

## 1. 파악

`/commit` 1단계와 동일. diff를 실제로 읽고 **하나의 작업 목적**인지 판단한다.
목적이 다른 변경이 섞였으면 멈추고 PR 범위를 확인. 커밋할 게 없으면 중단.

## 2. 브랜치

`develop`/`main` 위일 때만 새로 만든다. 이미 작업 브랜치면 그대로 쓴다.

```bash
gh api user --jq .login       # 브랜치 prefix. 추측 금지
git fetch origin develop
git checkout -b <login>/<작업명> origin/develop
```

`<login>/<영문 kebab-case>` — 예: `jexists/report-schema-fix`
미커밋 변경은 `checkout -b`로 따라온다. **stash 금지.**

## 3. 커밋

[`commit.md`](commit.md)의 2~5단계(staging·검사·메시지·확인)를 그대로 따른다.

## 4. push

> ⚠️ `push.default` 미설정 + 과거 새 브랜치 첫 push가 `develop`에 반영된 사례.
> refspec을 명시하고 push 후 원격을 확인한다.

```bash
BR=$(git rev-parse --abbrev-ref HEAD)
case "$BR" in develop|main) echo "중단: 보호 브랜치"; exit 1 ;; esac

git push -u origin "$BR:$BR"
git ls-remote --heads origin "$BR"       # 브랜치가 생겼는지
git fetch origin develop
git log -1 --oneline origin/develop      # develop이 안 밀렸는지
```

non-fast-forward 거절 → **중단.** pull·merge·rebase·force push 금지.

## 5. PR

```bash
gh pr list --head "$BR" --state open     # 중복 방지

gh pr create --base develop --head "$BR" --title "<type>: <한글 요약>" --body "$(cat <<'EOF'
## 변경 요약

- 변경 사항과 목적

## 검증

- 실행한 검사와 결과
- 미실행 검사가 있다면 사유

## 영향 및 주의 사항

- 영향 범위, 수동 작업, 후속 작업 또는 없음
EOF
)"
```

한국어. body는 HEREDOC. **안 돌린 검사를 통과로, 진행 중 CI를 완료로 쓰지 않는다.**
관련 이슈가 있을 때만 `## 관련 이슈` 추가.

## 6. 보고

PR URL / head·base / `git log origin/develop..HEAD --oneline` / 검사 결과 /
남겨 둔 변경 / "머지는 GitHub 웹에서 직접"

## 금지

`gh pr merge`, `main`으로 직접 PR, 리뷰어·라벨 자동 지정, PR 닫기·리뷰 상태 변경,
브랜치 삭제, 태그, force push. 충돌·divergence는 자동 해결 말고 중단.

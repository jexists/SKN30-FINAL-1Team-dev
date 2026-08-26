#!/bin/sh
# Edit/Write PostToolUse hook: 방금 고친 frontend 소스 한 파일만 prettier로 정리한다.
# npm run format(= prettier --write src)은 무관한 파일까지 다시 써서 커밋 범위를 깨므로 쓰지 않는다.
f=$(jq -r '.tool_input.file_path // empty')
case "$f" in
  */frontend/src/*.ts|*/frontend/src/*.tsx|*/frontend/src/*.css|*/frontend/src/*.scss|*/frontend/src/*.json)
    cd "${CLAUDE_PROJECT_DIR:-.}/frontend" 2>/dev/null || exit 0
    npx --no-install prettier --write "$f" >/dev/null 2>&1
    ;;
esac
exit 0

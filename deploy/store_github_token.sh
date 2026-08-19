#!/bin/bash
# 把 GitHub Personal Access Token 存入 macOS 钥匙串（osxkeychain），
# 供 Terminal/launchd 的 git 推送自动使用。
# 用法: bash deploy/store_github_token.sh <GitHub用户名> <Personal Access Token>
set -euo pipefail

USER_NAME="${1:-}"
TOKEN="${2:-}"
if [ -z "$USER_NAME" ] || [ -z "$TOKEN" ]; then
  echo "用法: bash deploy/store_github_token.sh <GitHub用户名> <Personal Access Token>"
  exit 1
fi

printf 'protocol=https\nhost=github.com\nusername=%s\npassword=%s\n' "$USER_NAME" "$TOKEN" \
  | git credential-osxkeychain store
echo "已存入钥匙串。验证："
git ls-remote https://github.com/yonglongl630-ops/opagg-report.git gh-pages | head -1

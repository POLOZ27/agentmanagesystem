#!/bin/bash
# 从 GitHub 拉取最新代码并重新部署（在服务器上运行）：bash ~/agent-portal/deploy/server/update.sh
# 只做快进更新：服务器上的代码如果被手工改过，会停下来提示，不会覆盖。
set -euo pipefail
cd "$(dirname "$0")/../.."
before=$(git rev-parse --short HEAD)
git fetch --quiet origin main
if ! git merge --ff-only --quiet origin/main; then
  echo "更新失败：服务器上的代码和仓库不一致（可能被手工改过），请把这段输出发给 Claude。"
  git status --short
  exit 1
fi
after=$(git rev-parse --short HEAD)
if [ "$before" = "$after" ]; then
  echo "已经是最新版本（$after），不用部署。加 --force 可以强制重新部署。"
  [ "${1:-}" = "--force" ] || exit 0
else
  echo "更新：$before → $after"
  git log --oneline "$before..$after"
fi
exec bash deploy/server/install.sh

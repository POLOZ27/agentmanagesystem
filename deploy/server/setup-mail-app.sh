#!/bin/bash
# 一次性设置：让代理系统和官网发信系统 ja-mail 用同一个 Entra 应用发信（应用权限 Mail.Send）。
# 从 ja-mail 容器读出应用 ID 和密钥，写进本机 .env.mail（权限 600），不会显示出来。
# 在服务器上运行：bash ~/agent-portal/deploy/server/setup-mail-app.sh，然后重新部署。
set -euo pipefail
cd "$(dirname "$0")"
SRC=${1:-ja-mail}
get() { docker exec "$SRC" printenv "$1" 2>/dev/null || true; }
T=$(get MS_TENANT_ID); C=$(get MS_CLIENT_ID); S=$(get MS_CLIENT_SECRET)
if [ -z "$T" ] || [ -z "$C" ] || [ -z "$S" ]; then
  echo "在容器 $SRC 里没找到 MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET，什么都没写"; exit 1
fi
umask 077
printf 'MS_APP_TENANT_ID=%s\nMS_APP_CLIENT_ID=%s\nMS_APP_CLIENT_SECRET=%s\n' "$T" "$C" "$S" > .env.mail
echo "已写入 .env.mail（权限 600）。ja-mail 允许的发件人设置：SENDERS 有 $(get SENDERS | tr ',' '\n' | grep -c @ || true) 个地址，SENDERS_GROUP $( [ -n "$(get SENDERS_GROUP)" ] && echo 已设置 || echo 未设置 )"

#!/bin/bash
# 在服务器上运行（polo 在 docker 组，不需要 sudo）：bash ~/agent-portal/deploy/server/install.sh
set -euo pipefail
cd "$(dirname "$0")"
echo "部署包版本：2026-11-01r2"
DATA_DIR=${DATA_DIR:-$HOME/agent-portal-data}
mkdir -p "$DATA_DIR"; chmod 700 "$DATA_DIR"
export DATA_DIR
# 证书覆盖服务器所有内网 IP 和主机名（有线 .71/.72、Wi-Fi .73 都能打开）
SITES=$(for ip in $(hostname -I) ; do case $ip in *:*) ;; *) printf 'https://%s:8443, ' "$ip";; esac; done)
SITES="${SITES}https://$(hostname):8443, https://localhost:8443"
# 用 IP 打开时浏览器不发 SNI，要指定默认证书
IP=$(hostname -I | tr ' ' '\n' | grep '^192\.168\.' | head -1)
# SearXNG：生成自己的密钥
[ -f searxng-settings.yml ] || sed "s|CHANGE-ME-run-openssl-rand-hex-32|$(openssl rand -hex 32)|" ../searxng/settings.yml > searxng-settings.yml
# 找到服务器上已在运行的 llama-server（本地模型）
LLM=llama-server-vl; LLM_NET=""
if docker inspect "$LLM" >/dev/null 2>&1; then
  NETMODE=$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$LLM")
  ARGS=$(docker inspect -f '{{join .Args " "}} {{join .Config.Cmd " "}}' "$LLM")
  LPORT=$(echo "$ARGS" | grep -oE -- '--port[ =][0-9]+' | grep -oE '[0-9]+' | head -1); LPORT=${LPORT:-8080}
  export AI_LOCAL_LLM_KEY=$(echo "$ARGS" | grep -oE -- '--api-key[ =][^ ]+' | head -1 | sed -E 's/--api-key[ =]//')
  export AI_LOCAL_MODEL=$(echo "$ARGS" | grep -oE -- '--alias[ =][^ ]+' | head -1 | sed -E 's/--alias[ =]//')
  if [ "$NETMODE" = host ]; then
    export AI_LOCAL_LLM_URL="http://host.docker.internal:$LPORT/v1"
  else
    LLM_NET=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$LLM" | awk '{print $1}')
    export AI_LOCAL_LLM_URL="http://$LLM:$LPORT/v1"
  fi
  echo "本地模型：$AI_LOCAL_LLM_URL（网络 ${LLM_NET:-host}）"
else
  # 本地模型换了容器（例如 strata），但在 llm_llm-network 上仍叫 llama-server-vl：沿用正在运行的设置
  if docker network inspect llm_llm-network >/dev/null 2>&1 && docker inspect agent-portal >/dev/null 2>&1; then
    LLM_NET=llm_llm-network
    for v in AI_LOCAL_LLM_URL AI_LOCAL_LLM_KEY AI_LOCAL_MODEL; do
      val=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' agent-portal | grep "^$v=" | cut -d= -f2-)
      [ -n "$val" ] && export "$v=$val"
    done
    export AI_LOCAL_LLM_URL=${AI_LOCAL_LLM_URL:-http://$LLM:8080/v1}
    # 模型名以服务器现在实际提供的为准（技术换模型后自动跟上）
    M=$(docker exec agent-portal python -c 'import os,httpx;u=os.environ["AI_LOCAL_LLM_URL"];k=os.environ.get("AI_LOCAL_LLM_KEY");print(httpx.get(u+"/models",headers={"Authorization":"Bearer "+k} if k else {},timeout=10).json()["data"][0]["id"])' 2>/dev/null) && [ -n "$M" ] && export AI_LOCAL_MODEL="$M"
    echo "本地模型：沿用现有设置 $AI_LOCAL_LLM_URL（网络 $LLM_NET）"
  else
    echo "没找到 $LLM 容器，本地模型地址请在设置页手动填"
  fi
fi
# 官网入学申请（只读账号，由 setup-admissions.sh 生成）
if [ -f .env.admissions ]; then set -a; . ./.env.admissions; set +a; echo "官网入学申请：已配置只读连接"; fi
if [ -f .env.mail ]; then set -a; . ./.env.mail; set +a; echo "应用权限发信：已配置"; fi
if [ -f .env.apfeed ]; then set -a; . ./.env.apfeed; set +a; echo "AP 学分课程名单：已配置"; fi
sed -e "s|SITES|$SITES|" -e "s|DEFAULT_IP|${IP:-localhost}|" Caddyfile.tmpl > Caddyfile
echo "这次要装合同预览组件（LibreOffice），第一次构建会多花几分钟……"
docker compose up -d --build
docker compose up -d --force-recreate caddy   # 让 Caddyfile 修改生效
if [ -n "$LLM_NET" ]; then
  docker network connect "$LLM_NET" agent-portal 2>/dev/null || true
  sleep 3   # 刚重建的容器接入网络后，DNS 要一会儿才生效
fi
if [ -n "${ADMISSIONS_DB_URL:-}" ]; then
  docker network connect ja-internal agent-portal 2>/dev/null || true
  sleep 2
  docker exec agent-portal python -c "import admissions;print('官网申请连接：', len(admissions.fetch()), '份')" 2>&1 | tail -1 || true
fi
docker exec agent-portal python -c "import os,httpx;u=os.environ.get('AI_LOCAL_LLM_URL');k=os.environ.get('AI_LOCAL_LLM_KEY');print('本地模型连接：', httpx.get(u+'/models',headers={'Authorization':'Bearer '+k} if k else {},timeout=10).status_code if u else '未设置')" 2>&1 | tail -1 || true
docker exec agent-portal python -c "import httpx;r=httpx.get('http://searxng:8080/search',params={'q':'study abroad agency Prague','format':'json'},timeout=30);print('搜索连接：',r.status_code,len(r.json().get('results',[])),'条')" 2>&1 | tail -1 || true
sleep 5
docker compose ps
# 自检：登录页内容正常 + 能生成测试合同和预览图。任何一项失败都明确报「部署失败」
FAIL=0
sleep 5
if curl -sk --max-time 20 "https://${IP:-localhost}:8443/login" | grep -q 'name="password"'; then
  echo "登录页自检：通过（https://${IP:-localhost}:8443/login）"
else
  echo "登录页自检：失败 —— 打不开登录页或内容不对"; FAIL=1
fi
docker exec -w /app agent-portal python tools/selfcheck.py || FAIL=1
if [ "$FAIL" != 0 ]; then
  echo
  echo "部署失败：上面有自检没通过，请把这段输出发给 Claude。"
  docker logs --tail 30 agent-portal 2>&1 | grep -iv "password\|key\|secret" || true
  exit 1
fi
echo
echo "部署完成。在学校网络里用浏览器打开： https://${IP:-服务器IP}:8443"
echo "第一次会提示证书不受信任（自建证书），点“高级 → 继续访问”即可。"
LINK=$(docker logs agent-portal 2>&1 | grep -o 'SETUP_LINK [^ ]*' | tail -1 | cut -d' ' -f2)
if [ -n "$LINK" ]; then
  echo
  echo "首次设置请只用这个链接（别人没有这个链接就无法抢先设置主密码）："
  echo "   https://${IP:-服务器IP}:8443$LINK"
  echo "设置主密码和手机验证器后，会显示恢复密钥，请离线保存。"
fi
exit 0

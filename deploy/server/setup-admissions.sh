#!/bin/bash
# 一次性设置：让代理系统只读官网的入学申请（在服务器上运行：bash ~/agent-portal/deploy/server/setup-admissions.sh）
# 在官网数据库 ja-db 里建一个只读账号 agent_portal_ro，它只能看 agent_portal.applications 这个视图
# （申请号、姓名、年级、入学学期、状态、代理字段），看不到官网的付款、家长、成绩等其他数据。
# 密码随机生成，只写进本机 .env.admissions（权限 600），不会显示出来。重复运行会换一个新密码。
set -euo pipefail
cd "$(dirname "$0")"
DB=$(docker exec ja-db printenv POSTGRES_DB)
PW=$(openssl rand -hex 24)
docker exec -i ja-db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<SQL
CREATE SCHEMA IF NOT EXISTS agent_portal;
CREATE OR REPLACE VIEW agent_portal.applications AS
  SELECT "applicationNo" AS application_no, "legalFirstName" AS first_name, "legalLastName" AS last_name,
         "gradeApplying" AS grade, "formData"->>'startYear' AS start_year, "startTerm" AS start_term,
         "isInternational" AS is_international, status::text AS status, "createdAt" AS created_at,
         "formData"->>'usesAgent' AS uses_agent, "formData"->>'agentCompany' AS agent_company,
         "formData"->>'agentName' AS agent_name, "formData"->>'agentEmail' AS agent_email
  FROM public.admission_applications;
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_portal_ro') THEN
    CREATE ROLE agent_portal_ro LOGIN;
  END IF;
END \$\$;
ALTER ROLE agent_portal_ro WITH LOGIN PASSWORD '$PW' NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 3;
GRANT CONNECT ON DATABASE "$DB" TO agent_portal_ro;
GRANT USAGE ON SCHEMA agent_portal TO agent_portal_ro;
GRANT SELECT ON agent_portal.applications TO agent_portal_ro;
SQL
umask 077
echo "ADMISSIONS_DB_URL=postgresql://agent_portal_ro:$PW@ja-db:5432/$DB" > .env.admissions
chmod 600 .env.admissions
echo "只读账号已设置。只读视图里现在有 $(docker exec ja-db sh -c 'psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM agent_portal.applications"') 份申请。"
echo "接下来运行 install.sh（或 update.sh --force）让代理系统接上。"

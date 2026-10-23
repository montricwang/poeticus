#!/usr/bin/env bash
# Opt-in local Poeticus private-memory preview, isolated from existing dev ports.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="$ROOT/../poeticus/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "缺少 Poeticus Python 虚拟环境：$PYTHON" >&2
  exit 1
fi
if [[ ! -f "$ROOT/.env" || ! -f "$ROOT/frontend/.env.local" ]]; then
  echo "请先配置私有后端 .env 和前端 frontend/.env.local" >&2
  exit 1
fi
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "请先在 frontend/ 执行 npm ci" >&2
  exit 1
fi
(
  cd "$ROOT"
  CLERK_AUTHORIZED_PARTIES="http://localhost:5175,http://127.0.0.1:5175" \
  POETICUS_USER_MEMORY_ENABLED=true \
  "$PYTHON" -m uvicorn backend.app:app --host 127.0.0.1 --port 8012
) &
backend_pid=$!
cleanup() { kill "$backend_pid" 2>/dev/null || true; }
trap cleanup EXIT
cd "$ROOT/frontend"
echo "集成测试站点：http://localhost:5175 （Ctrl+C 结束本地服务）"
POETICUS_API_PROXY_TARGET="http://127.0.0.1:8012" \
  npm run dev -- --host 127.0.0.1 --port 5175 --strictPort

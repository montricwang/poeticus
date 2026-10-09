#!/usr/bin/env bash
set -euo pipefail

KEY="${1:-}"
HOST="${2:-}"
PUBLIC_URL="${3:-}"

if [[ -z "$KEY" || -z "$HOST" ]]; then
  echo "Usage: bash scripts/retrieval/deploy_vps.sh <ssh-key> <user@host> [public-url]" >&2
  exit 2
fi

if [[ ! -f "$KEY" ]]; then
  echo "SSH key not found: $KEY" >&2
  exit 2
fi

if [[ -z "$PUBLIC_URL" ]]; then
  PUBLIC_URL="https://${HOST#*@}"
fi

REMOTE_ROOT="${POETICUS_RETRIEVAL_REMOTE_ROOT:-/opt/poeticus}"
REMOTE_DATA_ROOT="${POETICUS_RETRIEVAL_REMOTE_DATA_ROOT:-/opt/poeticus-data}"
REMOTE_PYTHON="$REMOTE_ROOT/.venv/bin/python"
SSH_OPTS=(
  -i "$KEY"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=accept-new
)

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "Deploying Retrieval code to $HOST"

# 运行期资产尚未迁移时，不允许替换正在运行的服务。
# 远程安装和重启前，先检查新目录布局是否齐备。
ssh "${SSH_OPTS[@]}" "$HOST" "
    set -euo pipefail
    test -f '$REMOTE_DATA_ROOT/retrieval/embeddings/qwen3_0.6b_sentence_1024/manifest.json' || {
      echo 'Missing migrated Retrieval artifacts at $REMOTE_DATA_ROOT/retrieval; refusing deployment' >&2
      exit 1
    }
"

tar -czf -   backend/retrieval   backend/data_paths.py   scripts/retrieval   requirements-retrieval.txt | ssh "${SSH_OPTS[@]}" "$HOST" "
    set -euo pipefail
    sudo tar -xzf - -C '$REMOTE_ROOT'
    cd '$REMOTE_ROOT'
    '$REMOTE_PYTHON' -m compileall -q backend/data_paths.py backend/retrieval scripts/retrieval
    sudo systemctl restart poeticus-retrieval

    ready=false
    for attempt in \$(seq 1 60); do
      if curl -fsS http://127.0.0.1:8787/health >/tmp/poeticus-retrieval-health.json 2>/dev/null; then
        ready=true
        break
      fi
      sleep 2
    done

    if [[ \$ready != true ]]; then
      echo 'Retrieval did not become ready within 120 seconds' >&2
      sudo systemctl status poeticus-retrieval --no-pager >&2 || true
      sudo journalctl -u poeticus-retrieval -n 80 --no-pager >&2 || true
      exit 1
    fi

    echo 'Remote localhost health:'
    cat /tmp/poeticus-retrieval-health.json
    echo
"

echo "Public health:"
curl -fsS --retry 3 --retry-delay 2 "$PUBLIC_URL/health"
echo

echo "Deployment ready."

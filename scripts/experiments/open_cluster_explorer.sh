#!/usr/bin/env bash
set -euo pipefail
HTML="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/poeticus-data/reports/recommendations/cluster_full/cluster-explorer.html"
if [[ ! -f "$HTML" ]]; then
  printf '聚类图尚未生成：%s\n' "$HTML" >&2
  exit 1
fi
if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$HTML")"
else
  printf '请用浏览器打开：%s\n' "$HTML"
fi

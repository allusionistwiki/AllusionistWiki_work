#!/usr/bin/env bash
set -euo pipefail
cd /c/Users/d5dx/Downloads/Code/AllusionistWiki_work
echo "[chain] P4 判定起動（Strata 直列 workers=1・10件/呼）"
YJ_CANDS="data/yuragi_works_candidates_p4.json" \
YJ_PROG="data/yuragi_worksjudge_p4_progress.txt" \
YJ_OUTJ="data/yuragi_works_judged_p4.jsonl" \
python scripts/judge_yuragi_works_candidates.py >> data/log_p4judge.txt 2>&1
echo "[chain] P4 判定完走"

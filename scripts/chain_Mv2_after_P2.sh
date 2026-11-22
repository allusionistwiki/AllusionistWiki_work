#!/usr/bin/env bash
set -u
cd /c/Users/d5dx/Downloads/Code/AllusionistWiki_work || exit 1
P2P="data/yuragi_p2_progress.txt"
for i in $(seq 1 360); do
  n=0; [ -f "$P2P" ] && n=$(wc -l < "$P2P")
  if [ -f data/yuragi_p2_progress.txt ] && [ "$n" -ge 118 ]; then
    echo "[chain] P2 完了（${n} 行）検知 → Lane M v2 抽出起動"; break
  fi
  sleep 300
done
if [ "$n" -lt 118 ]; then echo "[chain] watch timeout — M v2 未起動"; exit 2; fi
nohup python scripts/extract_yuragi_intra_entities.py >> data/log_yuragi_Mv2.txt 2>&1 &
echo "[chain] M v2 pid=$!"

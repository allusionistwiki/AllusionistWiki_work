#!/usr/bin/env bash
# Lane M（作中侧抽出 185 篇）完了検知 → Lane P2（創作候補 LLM 判定 1189 件）起動。
cd /c/Users/d5dx/Downloads/Code/AllusionistWiki_work || exit 1
P=data/yuragi_intra_progress.txt
last=$(wc -l < "$P" 2>/dev/null | tr -d ' '); last=${last:-0}
stall=0
for i in $(seq 1 1200); do
  n=$(wc -l < "$P" 2>/dev/null | tr -d ' '); n=${n:-0}
  if [ "$n" = "$last" ]; then
    stall=$((stall+1))
    if [ "$stall" -ge 9 ]; then
      echo "[chain] Lane M 完了検知（progress=$n）。Lane P2 起動"
      exec python scripts/judge_yuragi_works_candidates.py
    fi
  else
    stall=0; last=$n
  fi
  sleep 20
done
echo "[chain] watch timeout（400 分）"
exit 2

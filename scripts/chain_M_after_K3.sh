#!/usr/bin/env bash
# K3（作中概念 20 語生成）完了検知 → Lane M（作中侧抽出 185 篇）起動。
cd /c/Users/d5dx/Downloads/Code/AllusionistWiki_work || exit 1
P=data/yuragi_entitygen_progress.txt
last=$(wc -l < "$P" 2>/dev/null | tr -d ' '); last=${last:-0}
stall=0
for i in $(seq 1 90); do
  n=$(wc -l < "$P" 2>/dev/null | tr -d ' '); n=${n:-0}
  if [ "$n" = "$last" ]; then
    stall=$((stall+1))
    if [ "$stall" -ge 9 ]; then
      echo "[chain] K3 完了検知（progress=$n）。Lane M 起動"
      exec python scripts/extract_yuragi_intra_entities.py
    fi
  else
    stall=0; last=$n
  fi
  sleep 20
done
echo "[chain] watch timeout（30 分）"
exit 2

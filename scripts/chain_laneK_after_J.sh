#!/usr/bin/env bash
# Lane K launcher: Lane J（520 再裁定）の Strata 直列完了を待ってから起動する。
# J の progress ファイルが 240 秒伸びなかったら完了とみなし K を実行する。
cd /c/Users/d5dx/Downloads/Code/AllusionistWiki_work || exit 1
P=data/yuragi_reaudit_progress.txt
last=-1
stall=0
for i in $(seq 1 120); do
  n=$(wc -l < "$P" 2>/dev/null | tr -d ' ')
  n=${n:-0}
  if [ "$n" = "$last" ]; then
    stall=$((stall+1))
    if [ "$stall" -ge 12 ]; then
      echo "[chain] Lane J 完了検知（progress=$n・240s 不変）。Lane K 起動"
      exec python scripts/gen_yuragi_entity_articles.py
    fi
  else
    stall=0
    last=$n
  fi
  sleep 20
done
echo "[chain] watch timeout（120 分）— Lane K 未起動"
exit 2

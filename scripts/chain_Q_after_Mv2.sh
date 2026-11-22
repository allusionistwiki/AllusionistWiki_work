#!/usr/bin/env bash
set -u
cd /c/Users/d5dx/Downloads/Code/AllusionistWiki_work || exit 1
# M v2 完走（185 行到達）検知 → Q 再走 → 索引再生成 → publish（すべて非 LLM）
for i in $(seq 1 240); do
  n=0; [ -f data/yuragi_intra2_progress.txt ] && n=$(wc -l < data/yuragi_intra2_progress.txt)
  if [ "$n" -ge 185 ]; then echo "[chain] M v2 完走検知（${n}）→ Q/publish 統合"; break; fi
  sleep 120
done
if [ "$n" -lt 185 ]; then echo "[chain] watch timeout — 未起動"; exit 2; fi
sleep 60
echo "[chain] Q 決定論組立"; python scripts/gen_yuragi_intra_pages.py >> data/log_chainQ.txt 2>&1
echo "[chain] 索引再生成 R/S"; python scripts/gen_yuragi_works_index_r.py >> data/log_chainQ.txt 2>&1; python scripts/gen_yuragi_widx_s.py >> data/log_chainQ.txt 2>&1
echo "[chain] publish"; python scripts/publish_yuragi_site.py >> data/log_chainQ.txt 2>&1
echo "[chain] linkfix"; python scripts/linkfix_yuragi.py >> data/log_chainQ.txt 2>&1
cd /c/Users/d5dx/Downloads/Code/YuragiWiki && git add -A && git commit -q -m "M v2 完走統合: 作中实体 厳格台帳（引用逐語検証+NFKC+CN_CHAR 通過分）索引込み" && git push -q origin HEAD && echo "[chain] site pushed $(git log --oneline -1)"

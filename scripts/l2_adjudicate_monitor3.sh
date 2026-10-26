#!/bin/sh
# v2 完了監視: 起動時点の DONE 行数を baseline 化し、増分でのみ発火する。
LOG="data/adjudicate_v2_20261024T1608_fc8d.log"
BASE=$(grep -c "=== L2 ADJUDICATE V2 DONE" "$LOG" 2>/dev/null || echo 0)
echo "monitor3 baseline=$BASE"
while true; do
  NOW=$(grep -c "=== L2 ADJUDICATE V2 DONE" "$LOG" 2>/dev/null || echo 0)
  if [ "$NOW" -gt "$BASE" ]; then
    echo "L2-ADJ-V2-DONE-TRUE"
    grep "finished" "$LOG" | tail -1
    exit 0
  fi
  sleep 600
done

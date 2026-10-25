#!/bin/sh
RUN=20261024T1608_fc8d
DATA="C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/data"
for i in 0 1 2; do
  wc -l < "$DATA/adjudicate_$RUN.shard$i.log" > "$DATA/base_$i.txt"
done
while true; do
  tot=0
  for i in 0 1 2; do
    b=$(cat "$DATA/base_$i.txt")
    c=$(tail -n +$((b+1)) "$DATA/adjudicate_$RUN.shard$i.log" 2>/dev/null | grep -c "ADJUDICATE DONE")
    tot=$((tot+c))
  done
  if [ "$tot" -ge 3 ]; then
    echo "L2-ADJ-RESUME-DONE rounds=$tot"
    exit 0
  fi
  sleep 120
done

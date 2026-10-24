#!/bin/sh
RUN=20261024T1608_fc8d
DATA="C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/data"
while true; do
  cnt=$(cat "$DATA"/adjudicate_"$RUN".shard*.log 2>/dev/null | grep -c "ADJUDICATE DONE")
  done3=$(cat "$DATA"/adjudicate_"$RUN".shard*.log 2>/dev/null | grep -c "finished done=")
  if [ "$done3" -ge 3 ]; then
    echo "L2-ADJ-ALL-DONE finished=$done3"
    exit 0
  fi
  sleep 120
done

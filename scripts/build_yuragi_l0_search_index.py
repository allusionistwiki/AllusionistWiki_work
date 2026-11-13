#!/usr/bin/env python3
"""Yuragi L0 検索索引生成器（v3・raw 5 層対応・派生 run）。

台帳 latest.txt の現行 run（units.jsonl / units/*.jsonl / chunks/*.jsonl）から:
  search/posts.jsonl      1 投稿 1 行マスタ（ref・著者・ISO 日時・60 字スニペット・chain_id）
  search/by-author.jsonl  著者 → 投稿 ref 一覧（件数順）
  search/by-date.jsonl    JST 時系列（無日付＝削除投稿は除外）
  search/terms.jsonl      【…】表記 → 語彙索引（count・units・refs）
派生 run: latest.txt は更新しない（本体台帳チェーンを汚染しない）。
座標: 台帳 body_start/body_end は raw_group_path ファイルの raw バイト座標。
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
JST = timezone(timedelta(hours=9))
TERM_RE = re.compile(r"【([^】\n]{2,40})】")

def norm_term(s: str) -> str:
    s = re.sub(r"[【】\s]+", "", s).strip()
    return s[:40]

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def main():
    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    if not latest:
        raise SystemExit("latest.txt 空")
    src = L0 / "runs" / latest
    if not (src / "units.jsonl").exists():
        raise SystemExit(f"latest run {latest} に units.jsonl なし")
    rid = datetime.now(JST).strftime("%Y%m%dT%H%M") + "_l0si"
    run = L0 / "runs" / rid
    (run / "search").mkdir(parents=True, exist_ok=True)
    units = {u["unit_id"]: u for u in map(json.loads, rd(src / "units.jsonl").splitlines())}

    posts = []
    tc = {}
    terms = {}
    authors = {}
    for uid, u in units.items():
        lpath = src / "units" / f"{uid}.jsonl"
        for line in rd(lpath).splitlines():
            if not line.strip():
                continue
            p = json.loads(line)
            rp = p["raw_group_path"]
            if isinstance(rp, list):
                rp = rp[0]
            if rp not in tc:
                tc[rp] = rd(RAW / rp)
            body = tc[rp][p["body_start"]:p["body_end"]]
            assert body == body.strip(), f"{p['ref']} body 前後空白"
            ref = p["ref"]
            posts.append({
                "ref": ref, "unit_id": uid, "title": u["title"], "source": u["source"],
                "url": u["url"], "post_no": p["post_no"], "author": p["author"],
                "date_iso": p["date_iso"], "epoch": p["epoch"],
                "snippet": body[:60].replace("\n", " "),
                "chain_id": p["chain_id"], "raw_group_path": rp, "chars": p["chars"],
            })
            authors.setdefault(p["author"], []).append(ref)
            if p["epoch"] is not None:
                for t in {norm_term(x) for x in TERM_RE.findall(body)}:
                    e = terms.setdefault(t, {"count": 0, "units": set(), "refs": []})
                    e["count"] += 1
                    e["units"].add(uid)
                    e["refs"].append(ref)

    run_s = run / "search"
    (run_s / "posts.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in posts), encoding="utf-8", newline="\n")
    (run_s / "by-author.jsonl").write_text(
        "".join(json.dumps({"author": a, "n": len(v), "refs": v}, ensure_ascii=False) + "\n"
                for a, v in sorted(authors.items(), key=lambda kv: -len(kv[1]))),
        encoding="utf-8", newline="\n")
    dated = sorted((x for x in posts if x["epoch"] is not None), key=lambda x: x["epoch"])
    (run_s / "by-date.jsonl").write_text(
        "".join(json.dumps({"ref": x["ref"], "epoch": x["epoch"], "date_iso": x["date_iso"]},
                           ensure_ascii=False) + "\n" for x in dated),
        encoding="utf-8", newline="\n")
    (run_s / "terms.jsonl").write_text(
        "".join(json.dumps({"term": t, "count": e["count"], "units_touched": sorted(e["units"]),
                            "refs": e["refs"]}, ensure_ascii=False) + "\n"
                for t, e in sorted(terms.items(), key=lambda kv: -kv[1]["count"])),
        encoding="utf-8", newline="\n")
    stats = {"posts": len(posts), "authors": len(authors), "terms": len(terms),
             "term_occurrences": sum(e["count"] for e in terms.values()),
             "iso_dates": len(dated), "no_date": len(posts) - len(dated)}
    (run / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "run.json").write_text(json.dumps({
        "run_id": rid, "kind": "l0-search-index",
        "derived_from": {"l0_run": latest}, "created": datetime.now(JST).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    idx_p = W / "work" / "yuragi" / "index" / "runs-index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8")) if idx_p.exists() else {"L0": {}}
    idx["L0"][rid] = {"status": "current", "kind": "l0-search-index",
                      "path": "work/yuragi/L0/runs/" + rid, "derived_from": latest}
    idx_p.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))

if __name__ == "__main__":
    main()

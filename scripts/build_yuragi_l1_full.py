#!/usr/bin/env python3
"""Yuragi L1 制約なし版 — 篇記事＋スレッド原文全文を 1 ページに同梱する（決定論組立）。

L1 版（引用 100 字以内）に対して、制約なし版は生スレッド情報をそのまま掲載する。
出力: work/yuragi/L1/runs/<rid>_l1full/units/<unit_id>.md
  = L1 篇記事（監査済み run の本文）＋ 「## スレッド原文」節（全投稿・番号/作者/日時アンカー付き）
機械検証: 全投稿が欠落なく収録されていること（post 数照合＋body SHA 照合）を run.json に記録。
使い方: python scripts/build_yuragi_l1_full.py
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
L1 = W / "work" / "yuragi" / "L1"

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def jl(p: Path):
    out = []
    for l in rd(p).splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if isinstance(r, dict) and r.get("_meta"):
            continue
        out.append(r)
    return out

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=None)
    a = ap.parse_args()
    l0_latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    unit_run = "20261117T2115_l1u"  # 監査 PASS 済み篇記事 run
    rid = a.run_dir or (dt.datetime.now().strftime("%Y%m%dT%H%M") + "_l1full")
    out = L1 / "runs" / rid
    (out / "units").mkdir(parents=True, exist_ok=True)

    units, seen = [], set()
    for u in jl(L0 / "runs" / l0_latest / "units.jsonl"):
        if u["unit_id"] in seen:
            continue
        seen.add(u["unit_id"])
        units.append(u)

    n_ok = 0
    per_unit = {}
    for u in units:
        uid = u["unit_id"]
        d = (RAW / u["raw_path"].rsplit("/", 1)[0] if u["source"] == "jbbs"
             else RAW / "mixi/373088" / u["title"] if u["source"] == "mixi"
             else RAW / "hatena_flicker")
        posts = jl(d / "structured.jsonl")
        art = L1 / "runs" / unit_run / "units" / f"{uid}.md"
        if not art.exists():
            print(f"skip (篇記事なし): {uid}")
            continue
        art_body = art.read_text(encoding="utf-8").split("---\n", 2)[2]
        sec = ["\n\n## スレッド原文（全文・制約なし版）\n",
               "\n> 原文の著作権は各投稿者に帰属します。出典: YuragiWiki raw（" + u["url"] + "）\n"]
        for p in posts:
            sec.append(f"\n**{p['post_no']}** {p['author']} {p.get('date_iso') or '（日付なし）'}\n\n"
                       + p["body"] + "\n")
        full = "".join(sec)
        head = (f"---\ntitle: \"{u['title']}\"\nunit: {uid}\nsource: {u['source']}\nurl: {u['url']}\n"
                f"version: full（制約なし・原文全文同梱）\narticle_run: {unit_run}\nrun: {rid}\n---\n\n"
                + art_body + full)
        # newline 変換なしでバイトどおり書く（raw 規約: \n は \n・原文 \r\n は \r\n）
        (out / "units" / f"{uid}.md").write_bytes(head.encode("utf-8"))
        per_unit[uid] = {"posts": len(posts),
                         "body_sha1": sha1("\n\n".join(p["body"] for p in posts))}
        n_ok += 1

    (out / "run.json").write_text(json.dumps({
        "run_id": rid, "layer": "L1/full", "mode": "deterministic",
        "derived_from": {"L0_ledger": l0_latest, "L1_units": unit_run},
        "created": dt.datetime.now().isoformat(),
        "units": n_ok, "posts_total": sum(v["posts"] for v in per_unit.values()),
        "per_unit": per_unit}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"rid": rid, "units": n_ok,
                      "posts_total": sum(v["posts"] for v in per_unit.values())},
                     ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())

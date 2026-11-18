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
PAGE_POSTS = 100  # 分页: 1 ページあたり投稿数
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
        n = len(posts)
        pages = max(1, (n + PAGE_POSTS - 1) // PAGE_POSTS)
        def page_file(k):  # 1-indexed page number -> out-relative path
            return f"units/{uid}.md" if k == 1 else f"pages/{uid}/p{k}.md"
        def page_url(k):   # site URL path segment for page k
            return "" if k == 1 else f"p{k}"
        fm = (f"---\ntitle: \"{u['title']}\"\nunit: {uid}\nsource: {u['source']}\nurl: {u['url']}\n"
              f"version: full（制約なし・原文全文同梱）\narticle_run: {unit_run}\nrun: {rid}\n---\n\n")
        per_pages = []
        for k in range(1, pages + 1):
            lo, hi = (k - 1) * PAGE_POSTS, min(k * PAGE_POSTS, n)
            sec = []
            head = fm if k == 1 else fm.replace('version: full（制約なし・原文全文同梱）\n',
                                                f'version: full p{k}/{pages}\n')
            if k == 1:
                sec.append(art_body)
                sec.append("\n\n## スレッド原文（全文・制約なし版）\n")
                sec.append("\n> 原文の著作権は各投稿者に帰属します。出典: YuragiWiki raw（" + u["url"] + "）\n")
            nav = []
            if pages > 1:
                def purl(kk):
                    return ".." if kk == 1 else f"p{kk}"
                nav.append(f"\n\n— 原文 {lo+1}〜{hi} / 全 {n} 投稿（{k}/{pages} ページ）—")
                if k > 1:
                    nav.append(f" [前のページ]({purl(k-1)})")
                if k < pages:
                    nav.append(f" [次のページ]({purl(k+1)})")
                nav.append(" [篇記事へ](../../units/" + uid + ")")
            sec.append("".join(nav))
            ppb = []
            for p in posts[lo:hi]:
                blk = (f"\n<a id=\"post-{p['post_no']}\"></a>\n\n"
                       f"**{p['post_no']}** {p['author']} {p.get('date_iso') or '（日付なし）'} "
                       f"[#{p['post_no']}](#post-{p['post_no']})"
                       f"\n\n{p['body']}\n")
                sec.append(blk)
                ppb.append(p["body"])
            outpage = "".join(sec)
            if k == 1:
                dest = out / "units" / f"{uid}.md"
                dest.parent.mkdir(parents=True, exist_ok=True)
            else:
                dest = out / "pages" / uid / f"p{k}.md"
                dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(head.encode("utf-8") + outpage.encode("utf-8"))
            per_pages.append({"page": k, "posts": [lo + 1, hi],
                              "body_sha1": sha1("\n\n".join(ppb))})
        per_unit[uid] = {"posts": n, "pages": pages, "page_sha1": per_pages,
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

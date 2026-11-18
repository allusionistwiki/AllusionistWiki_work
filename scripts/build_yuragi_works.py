#!/usr/bin/env python3
"""Yuragi 創作記述ページ生成（決定論）— works.jsonl 台帳にもとづく作品ページ群。

「創作的記述をすべてたどれる形で公開」= 収録投稿の原文全文（逐語・投稿 permalink 付き）
＋ 掲載文脈（篇・群索引・作者・日時）を機械組立で 1 作品ページに集約する。
名寄せは行わない（work 表記が違えば別ページ）。グループ化キーは (work, author)。
無題作品は (無題, author) 単位。
出力: work/yuragi/L1/runs/<rid>_l1works/works/<slug>.md ＋ index/works_index_<type>.md
検証: verify_yuragi_works.py（収録 body バイト一致・群収容網羅）
使い方: python scripts/build_yuragi_works.py [--min-chains 1]
"""
import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from unicodedata import normalize

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
L1 = W / "work" / "yuragi" / "L1"
FULLSITE = "https://allusionistwiki.github.io/YuragiWiki/full/"

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

def slugify(s: str) -> str:
    t = re.sub(r"[^\w]+", "_", normalize("NFKC", s), flags=re.U).strip("_")
    return (t or "a")[:50]

def unique_slug(base: str, used: set) -> str:
    sl, i = base, 2
    while sl.casefold() in used:
        sl = f"{base}_{i}"
        i += 1
    used.add(sl.casefold())
    return sl

def permalink(uid: str, post_no: int, post_index: dict) -> str:
    k = post_index.get(uid, {}).get(post_no)
    if k is None:
        return ""
    seg = "" if k == 1 else f"p{k}"
    return f"{FULLSITE}{uid}/{seg}#post-{post_no}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=None)
    a = ap.parse_args()
    rid = a.run_dir or (dt.datetime.now().strftime("%Y%m%dT%H%M") + "_l1works")
    out = L1 / "runs" / rid
    (out / "works").mkdir(parents=True, exist_ok=True)
    (out / "index").mkdir(parents=True, exist_ok=True)

    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    units = {}
    for u in jl(L0 / "runs" / latest / "units.jsonl"):
        units.setdefault(u["unit_id"], u)
    # 篇データ: 投稿本文＋post_no→ページ番号
    unit_data = {}
    for uid, u in units.items():
        d = (RAW / u["raw_path"].rsplit("/", 1)[0] if u["source"] == "jbbs"
             else RAW / "mixi/373088" / u["title"] if u["source"] == "mixi"
             else RAW / "hatena_flicker")
        posts = jl(d / "structured.jsonl")
        unit_data[uid] = {
            "by_no": {p["post_no"]: p for p in posts},
            "page_of": {p["post_no"]: i // 100 + 1 for i, p in enumerate(posts)},
            "chains": {c["chain_id"]: c for c in jl(d / "chains.jsonl")},
            "title": u.get("title", uid),
        }

    works_ledger = [json.loads(l) for l in (L1 / "works.jsonl").read_bytes().decode("utf-8").splitlines() if l.strip()]
    groups = defaultdict(list)
    for r in works_ledger:
        if not r.get("creative"):
            continue
        work = (r.get("work") or "無題").strip()
        groups[(work, r.get("author", ""))].append(r)

    used = set()
    entries = []
    n_pages = 0
    for (work, author), rows in sorted(groups.items()):
        base = slugify(work) if work != "無題" else f"無題_{slugify(author) or 'anon'}"
        slug = unique_slug(base, used)
        # 类型は最頻
        types = defaultdict(int)
        for r in rows:
            types[r.get("type", "その他創作")] += 1
        wtype = max(types.items(), key=lambda x: x[1])[0]
        lines = ["---", f'title: "{work}"', f"work: \"{work}\"", f"author: \"{author}\"",
                 f"type: \"{wtype}\"", f"chains: {len(rows)}", f"run: {rid}", "---", "",
                 f"# {work}", ""]
        lines.append(f"（作者: {author} ／ 类型: {wtype} ／ 収録群: {len(rows)}）")
        lines.append("")
        for r in sorted(rows, key=lambda x: (x["uid"], x["post_range"][0])):
            uid = r["uid"]
            ud = unit_data.get(uid)
            if not ud:
                continue
            cid = r["chain_id"]
            c = ud["chains"].get(cid, {})
            nos = c.get("post_nos") or list(range(r["post_range"][0], r["post_range"][1] + 1))
            t = "、".join(c.get("topics", [])) or "—"
            lines.append(f"## {ud['title']}（{uid}） 群 {cid.split('#')[1]}")
            lines.append("")
            lines.append(f"- 話題: {t}")
            if c.get("summary"):
                lines.append(f"- 掲載文脈: {c['summary']}")
            lines.append("")
            for n in nos:
                p = ud["by_no"].get(n)
                if not p:
                    continue
                pl = permalink(uid, n, ud["page_of"])
                lines.append(f"**{n}** {p.get('author','')} {p.get('date_iso') or ''} [#{n}]({pl})")
                lines.append("")
                lines.append(p["body"])
                lines.append("")
        content = "\n".join(lines)
        (out / "works" / f"{slug}.md").write_bytes(content.encode("utf-8"))
        entries.append({"slug": slug, "work": work, "author": author, "type": wtype,
                        "chains": len(rows), "units": sorted({r["uid"] for r in rows})})
        n_pages += 1

    # 类型別索引（1 索引ページ 400 件上限で分页）
    by_type = defaultdict(list)
    for e in entries:
        by_type[e["type"]].append(e)
    index_pages = []
    for wtype, es in by_type.items():
        es = sorted(es, key=lambda x: (-x["chains"], x["work"]))
        for pgi in range(0, len(es), 400):
            chunk = es[pgi:pgi + 400]
            pg = pgi // 400 + 1
            sl = slugify(wtype) + ("" if pg == 1 else f"_{pg}")
            lines = ["---", f'title: "創作索引: {wtype}（{pg}）"', f"run: {rid}", "---", "",
                     f"# 創作索引: {wtype}（{len(es)} 作品・{pg} ページ目）", ""]
            for e in chunk:
                lines.append(f"- [[works/{e['slug']}|{e['work']}]]（{e['author']}・{e['chains']} 群）")
            (out / "index" / f"{sl}.md").write_bytes("\n".join(lines).encode("utf-8"))
            index_pages.append({"slug": sl, "type": wtype, "page": pg, "count": len(chunk)})
    (out / "run.json").write_text(json.dumps({
        "run_id": rid, "layer": "L1/works", "mode": "deterministic",
        "derived_from": {"L0_ledger": latest, "works_ledger": "work/yuragi/L1/works.jsonl"},
        "created": dt.datetime.now().isoformat(),
        "works_pages": n_pages, "index_pages": len(index_pages)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"rid": rid, "works_pages": n_pages, "index_pages": len(index_pages)}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())

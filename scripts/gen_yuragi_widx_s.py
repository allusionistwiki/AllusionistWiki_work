# -*- coding: utf-8 -*-
"""Lane S: 創作作者索引・篇収容索引の site works 全件走査再生成（run *_l1widx）。

正 = site content/works/*.md frontmatter（title/work/author/type）＋本文の収録 ref 行。
出力: work/yuragi/L1/runs/20261122T2310_l1widx/author_index/*.md と unit_index/*.md
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
SITE_WORKS = W.parent / "YuragiWiki" / "content" / "works"
SITE_UNITS = W.parent / "YuragiWiki" / "content" / "units"
OUT = W / "work/yuragi/L1/runs/20261122T2310_l1widx"


def fm_get(t: str, key: str) -> str:
    m = re.search(rf'^{key}:\s*"([^"]*)"', t, re.M)
    return m.group(1) if m else ""


def slug(s: str) -> str:
    s = ex.norm(s)
    return re.sub(r'[\\/:*?"<>|&#+%\[\]]', "_", s)[:120]


def main():
    (OUT / "author_index").mkdir(parents=True, exist_ok=True)
    (OUT / "unit_index").mkdir(parents=True, exist_ok=True)
    by_author: dict = defaultdict(list)
    by_unit: dict = defaultdict(list)
    n = 0
    for p in sorted(SITE_WORKS.glob("*.md")):
        if p.stem == "index":
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        title = fm_get(t, "title") or fm_get(t, "work") or p.stem
        author = (fm_get(t, "author") or "（作者不明）").strip()
        by_author[author].append((title, p.stem))
        for m in re.finditer(r"\[\[full/([^#\|\]]+)", t):
            uid = m.group(1)
            if (title, uid) not in by_unit[uid]:
                by_unit[uid].append((title, p.stem))
        n += 1
    # 作者索引: 掲載数順・400 件/頁
    authors = sorted(by_author.items(), key=lambda kv: -len(kv[1]))
    pages = defaultdict(list)
    for author, items in authors:
        pages[slug(author)].append((author, items))
    emitted_a = 0
    for sl, group in pages.items():
        lines = ["---", f'title: "{group[0][0]}"', 'run: 20261122T2310_l1widx', "---", "",
                 f"# 作者: {group[0][0]}（掲載 {sum(len(i) for _, i in group)} 作品）", ""]
        for author, items in group:
            for tt, ws in items:
                lines.append(f"- [[works/{ws}|{tt}]]")
        lines.append("")
        (OUT / "author_index" / f"{sl}.md").write_text("\n".join(lines), encoding="utf-8")
        emitted_a += 1
    # 篇収容索引: 篇ごとの掲載作品一覧（units 実在ページのみにリンク・M 型等は原文層へ）
    units_exist = {q.stem for q in SITE_UNITS.glob("*.md")}
    emitted_u = 0
    for uid, items in sorted(by_unit.items()):
        if uid in units_exist:
            ulink = f"→ 篇ページ: [[units/{uid}|{uid}]]"
        else:
            ulink = f"（篇 {uid} は mobile 由来・篇ページ未生成 → 創作ページ内の投稿リンクから辿れます）"
        lines = ["---", f'title: "{uid}"', 'run: 20261122T2310_l1widx', "---", "",
                 f"# 篇 {uid}（掲載 {len(items)} 作品）", "",
                 ulink, ""]
        lines += [f"- [[works/{ws}|{tt}]]" for tt, ws in sorted(items)]
        lines.append("")
        (OUT / "unit_index" / f"{slug(uid)}.md").write_text("\n".join(lines), encoding="utf-8")
        emitted_u += 1
    print(f"[laneS] works={n} authors={len(by_author)} author_pages={emitted_a} unit_pages={emitted_u}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

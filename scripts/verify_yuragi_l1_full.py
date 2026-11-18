#!/usr/bin/env python3
"""制約なし版 v2（分页・投稿アンカー）の機械検証 — builder と同一再構成とのバイト一致。

p1 = units/<uid>.md の「## スレッド原文」節以降、pK = pages/<uid>/pK.md の冒頭本文。
投稿単位: 全 48,891 件の body が該当ページに逐語収録されていることを SHA ではなく
全文再構成一致で検証する（収容数・頁境界・ permalink アンカー含む）。
"""
import json
import sys
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
L1 = W / "work" / "yuragi" / "L1"
PAGE_POSTS = 100

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

def main():
    rid = max(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1full"))
    run = L1 / "runs" / rid
    l0_latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    units, seen = [], set()
    for u in jl(L0 / "runs" / l0_latest / "units.jsonl"):
        if u["unit_id"] not in seen:
            seen.add(u["unit_id"])
            units.append(u)
    issues, posts_ok = [], 0
    for u in units:
        uid = u["unit_id"]
        d = (RAW / u["raw_path"].rsplit("/", 1)[0] if u["source"] == "jbbs"
             else RAW / "mixi/373088" / u["title"] if u["source"] == "mixi"
             else RAW / "hatena_flicker")
        posts = jl(d / "structured.jsonl")
        n = len(posts)
        pages = max(1, (n + PAGE_POSTS - 1) // PAGE_POSTS)
        for k in range(1, pages + 1):
            lo, hi = (k - 1) * PAGE_POSTS, min(k * PAGE_POSTS, n)
            sec = []
            if k == 1:
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
            for p in posts[lo:hi]:
                sec.append(f"\n<a id=\"post-{p['post_no']}\"></a>\n\n"
                           f"**{p['post_no']}** {p['author']} {p.get('date_iso') or '（日付なし）'} "
                           f"[#{p['post_no']}](#post-{p['post_no']})"
                           f"\n\n{p['body']}\n")
            expected = "".join(sec)
            md = run / "units" / f"{uid}.md" if k == 1 else run / "pages" / uid / f"p{k}.md"
            if not md.exists():
                issues.append(f"{uid}:p{k}:PAGE_MISSING")
                continue
            t = rd(md)
            if k == 1:
                i = t.find("## スレッド原文（全文・制約なし版）")
                if i < 0:
                    issues.append(f"{uid}:p1:SECTION_MISSING")
                    continue
                got = t[i - 2:] if t[i - 2:i] == "\n\n" else t[i:]
            else:
                # ページ冒頭 frontmatter を除いた本文
                parts = t.split("---\n", 2)
                if len(parts) < 3:
                    issues.append(f"{uid}:p{k}:FM_BROKEN")
                    continue
                got = parts[2]
                # pK 本文は nav から始まる（frontmatter 直後）
                got = got[1:] if got.startswith("\n") else got
            if got != expected:
                issues.append(f"{uid}:p{k}:DIFF len {len(got)}!={len(expected)}")
                continue
            posts_ok += hi - lo
    print(json.dumps({"rid": rid, "units": len(units), "posts_ok": posts_ok,
                      "issues": len(issues), "sample": issues[:8]}, ensure_ascii=False))
    return 0 if not issues else 1

if __name__ == "__main__":
    sys.exit(main())

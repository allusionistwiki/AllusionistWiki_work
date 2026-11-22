# -*- coding: utf-8 -*-
"""Lane R: 创作索引 完全再生成（site content/works 全ページを正とし、类型別索引を決定論再生成）。

正 = site content/works/*.md（frontmatter title/type/author/work）。
出力: work/yuragi/L1/runs/20261122T2300_l1works/index/<类型>.md（publish の works_index 統合に供給）
publish 側の works_index 供給を「run 全部併合」へ patch する前提の生成物。
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
SITE_WORKS = W.parent / "YuragiWiki" / "content" / "works"
OUT = W / "work/yuragi/L1/runs/20261122T2300_l1works/index"


def fm_get(t: str, key: str) -> str:
    m = re.search(rf'^{key}:\s*"([^"]*)"', t, re.M)
    return m.group(1) if m else ""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    by_type = defaultdict(list)
    n = 0
    for p in sorted(SITE_WORKS.glob("*.md")):
        if p.stem == "index":
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        title = fm_get(t, "title") or fm_get(t, "work") or p.stem
        wtype = fm_get(t, "type") or "その他創作"
        by_type[wtype].append((title, p.stem))
        n += 1
    # 类型ごとに 400 件/頁 へ分割
    emitted = 0
    for wtype, items in sorted(by_type.items()):
        items.sort()
        pages = (len(items) + 399) // 400
        for i in range(pages):
            chunk = items[i * 400:(i + 1) * 400]
            sfx = "" if pages == 1 else f"_{i + 1}"
            slug = re.sub(r'[\\/:*?"<>|&#+%]', "_", wtype)[:80] + sfx
            lines = ["---", f'title: "{wtype}{sfx}"', 'run: 20261122T2300_l1works',
                     "---", "", f"# 創作索引 — {wtype}{sfx}", "",
                     f"（{len(items)} 件中 {len(chunk)} 件表示・全 {n} 作品は [[works_top|創作索引トップ]]）", ""]
            lines += [f"- [[works/{sl}|{tt}]]" for tt, sl in chunk]
            lines.append("")
            (OUT / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")
            emitted += 1
    print(f"[laneR] works={n} types={len(by_type)} index_pages={emitted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

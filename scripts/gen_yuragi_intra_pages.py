# -*- coding: utf-8 -*-
"""Lane Q: 作中实体ページ決定論組立（ベンチマーク 4000+ 超え目標・LLM 消費なし）。

入力:
 - Lane M 抽出台帳 work/yuragi/L1/runs/20261122T1600_l1intra/extract/*.jsonl
   （{term, usage, quotes[{q, ref}]} per unit）
出力: work/yuragi/L1/runs/20261122T2100_l1enQ/entities/<slug>.md
   （frontmatter term/type/count + 概要=篇別 usage + 逐語引用+ref + 関連導線）
冪等: 再実行で全件再生成。publish は最新 *_l1en run を本体とし旧 *_l1en（K 51 記事）を継承する。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
SRC = W / "work/yuragi/L1/runs/20261122T1600_l1intra/extract"
OUT = W / "work/yuragi/L1/runs/20261122T2100_l1enQ"


def jl(p: Path):
    if not p.is_file():
        return []
    out = []
    for l in p.read_bytes().decode("utf-8", "replace").splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        if isinstance(r, dict) and "_meta" in r:
            continue
        out.append(r)
    return out


def main():
    (OUT / "entities").mkdir(parents=True, exist_ok=True)
    for old in (OUT / "entities").glob("*.md"):
        old.unlink()
    merged: dict = {}
    for jf in sorted(SRC.glob("*.jsonl")):
        uid = jf.stem
        for it in jl(jf):
            t = str(it.get("term", "")).strip()
            if not t:
                continue
            m = merged.setdefault(t, {"disp": t, "units": {}})
            qs = []
            for q0 in (it.get("quotes") or []):
                if isinstance(q0, dict) and q0.get("q"):
                    qs.append((str(q0.get("ref", uid)), str(q0["q"])[:220]))
            m["units"].setdefault(uid, []).append((str(it.get("usage", ""))[:220], qs))
    n = 0
    for term, m in sorted(merged.items()):
        slug = ex.norm(term).replace("・", "_").replace("＝", "=")
        slug = re.sub(r'[\\/:*?"<>|]', "_", slug)[:120]
        if not slug:
            continue
        us = sorted(m["units"].items())
        lines = ["---", f'title: "{term}"', "run: 20261122T2100_l1enQ",
                 f'term: "{term}"', 'type: "作中实体"', f"count: {len(us)}",
                 f'link_audit: "20261122T2100_l1enQ_deterministic"', "---", "",
                 f"# {term}（ゆらぎの神話）", "", "## 使用状況（篇横断・逐語引用＋ref 付き）", ""]
        for uid, entries in us:
            lines.append(f"### [[units/{uid}|{uid}]]")
            lines.append("")
            for usage, qs in entries[:2]:
                if usage:
                    lines.append(usage)
                for ref, q in qs[:2]:
                    pno = ref.split(":")[-1] if ":" in ref else ""
                    base = ref.split(":")[0] if ":" in ref else uid
                    lines.append(f"> 「{q}」 [[full/{base}#post-{pno}|{ref}]]")
                lines.append("")
        lines += ["---", "",
                  "※ 本記事は作中侧抽出（Lane M）台帳からの決定論組立（v0.14 創作活動基準）。",
                  "→ [[entities_index|実体索引]] ／ [[entities_map/index|体系版索引]]", ""]
        (OUT / "entities" / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")
        n += 1
    print(f"[laneQ] terms merged={len(merged)} written={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
from cn_gate import find_cn

W = Path(ex.__file__).resolve().parent.parent
SRC = [W / "work/yuragi/L1/runs/20261122T1700_l1intra2/extract",
       W / "work/yuragi/L1/runs/20261122T1600_l1intra/extract"]
OUT = W / "work/yuragi/L1/runs/20261122T2100_l1en"


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
    # 原文 body 全集（引用逐語検証ゲート）
    bodies: dict = {}
    uids = [jf.stem for _sd in SRC if _sd.is_dir() for jf in sorted(_sd.glob("*.jsonl"))]
    for uid in uids:
        try:
            sd, meta = ex.unit_dir(uid)
        except Exception:
            continue
        for r in jl(sd / "structured.jsonl"):
            bodies[f"{uid}:{r.get('post_no')}"] = str(r.get("body", ""))
        bodies[uid] = "\n".join(bodies[f"{uid}:{r.get('post_no')}"]
                                for r in jl(sd / "structured.jsonl")
                                if f"{uid}:{r.get('post_no')}" in bodies)
    merged: dict = {}
    for _sdir in SRC:
     if not _sdir.is_dir():
        continue
     for jf in sorted(_sdir.glob("*.jsonl")):
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
    cn_drop = []
    for term, m in sorted(merged.items()):
        # CN_CHAR ゲート: 台帳 usage（LLM 生成文）に簡体字混入なら当該篇エントリを除外
        units_ok = {}
        for uid, entries in m["units"].items():
            keep = []
            for usage, qs in entries:
                hits, _ = find_cn(usage)
                qhits = sum(len(find_cn(q)[0]) for _, q in qs)
                # 引用逐語検証: 引用元 ref の原文（投稿 body or 篇全文）に逐語で存在すること
                qs_ok = []
                import unicodedata as _ud0
                for ref, q in qs:
                    src = bodies.get(ref) or bodies.get(ref.split(":")[0]) or bodies.get(uid, "")
                    def _nm(s):
                        s = _ud0.normalize("NFKC", str(s))
                        return re.sub(r"[\s\u3000]+", "", s).replace("ー", "〜")
                    norm_q = _nm(q)
                    norm_src = _nm(src)
                    if norm_q and norm_q in norm_src:
                        qs_ok.append((ref, q))
                if hits or qhits or not qs_ok:
                    cn_drop.append((term, uid))
                    continue
                keep.append((usage, qs_ok))
            if keep:
                units_ok[uid] = keep
        if not units_ok:
            continue
        m2 = {"disp": m["disp"], "units": units_ok}
        slug = ex.norm(term).replace("・", "_").replace("＝", "=")
        slug = re.sub(r'[\\/:*?"<>|]', "_", slug)[:120]
        if not slug:
            continue
        us = sorted(m2["units"].items())
        lines = ["---", f'title: "{term}"', "run: 20261122T2100_l1en",
                 f'term: "{term}"', 'type: "作中实体"', f"count: {len(us)}",
                 f'link_audit: "20261122T2100_l1en_deterministic"', "---", "",
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
                    if pno.isdigit():
                        lines.append(f"> 「{q}」 [[full/{base}#post-{pno}|{ref}]]")
                    else:
                        lines.append(f"> 「{q}」 [[full/{base}|{ref}]]")
                lines.append("")
        lines += ["---", "",
                  "※ 本記事は作中侧抽出（Lane M）台帳からの決定論組立（v0.14 創作活動基準）。",
                  "→ [[entities_index|実体索引]] ／ [[entities_map/index|体系版索引]]", ""]
        (OUT / "entities" / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")
        n += 1
    print(f"[laneQ] merged={len(merged)} written={n} gate_drop(usage/引用不合格)={len(cn_drop)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

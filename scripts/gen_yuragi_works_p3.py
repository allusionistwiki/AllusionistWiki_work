# -*- coding: utf-8 -*-
"""Lane P3: P2 判定 creative 1,034 件の works ページ決定論組立。

入力: data/yuragi_works_judged.jsonl（ref/creative/kind/title）＋ 原文 structured.jsonl
出力: work/yuragi/L1/runs/20261122T2200_l1works/works/<slug>.md
各ページ: 題名・类型・作者・投稿 permalink・冒頭引用（原文逐語・機械抽出）。LLM 消費なし。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex
from cn_gate import find_cn


def esc(t: str) -> str:
    """frontmatter YAML 二重引用用エスケープ。"""
    return str(t).replace("\\", "\\\\").replace('"', "'").replace("\n", " ")

W = Path(ex.__file__).resolve().parent.parent
J = W / "data" / "yuragi_works_judged.jsonl"
OUT = W / "work/yuragi/L1/runs/20261122T2200_l1works/works"
PROG = W / "data" / "yuragi_p3_progress.txt"


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
    OUT.mkdir(parents=True, exist_ok=True)
    judged = [json.loads(l) for l in J.read_text(encoding="utf-8").splitlines() if l.strip()]
    cre = [r for r in judged if r.get("creative") and r.get("ref")]
    done = set()
    if PROG.is_file():
        done = {l.strip() for l in PROG.read_text(encoding="utf-8").splitlines() if l.strip()}
    ok = skip = 0
    for r in cre:
        ref = str(r["ref"])
        if ref in done:
            continue
        uid, _, pno = ref.partition(":")
        try:
            sd, meta = ex.unit_dir(uid)
        except Exception:
            skip += 1
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write(ref + "\n")
            continue
        rec = None
        for x0 in jl(sd / "structured.jsonl"):
            if str(x0.get("post_no")) == pno.strip():
                rec = x0
                break
        if rec is None:
            skip += 1
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write(ref + "\n")
            continue
        title = str(r.get("title") or "").strip()
        kind = str(r.get("kind") or "創作")
        body = str(rec.get("body", ""))
        if not title:
            title = body.strip().split("\n")[0][:60]
        hits, _ = find_cn(title + kind)
        if hits:
            skip += 1
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write(ref + "\n")
            continue
        author = str(rec.get("author") or rec.get("nick") or "").strip()[:80]
        dt = str(rec.get("date") or rec.get("posted") or "").strip()[:32]
        pn = pno.strip()
        head = "\n".join(body.strip().split("\n")[:12])[:900]
        slug = ex.norm(title).replace("・", "_").replace("＝", "=").replace("「", "").replace("」", "")
        slug = re.sub(r'[\\/:*?"<>|]', "_", slug)[:120]
        if not slug:
            skip += 1
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write(ref + "\n")
            continue
        plink = ""
        lines = ["---", f'title: "{esc(title)}"', f'work: "{esc(title)}"', f'author: "{esc(author)}"',
                 f'type: "{esc(kind)}"', "run: 20261122T2200_l1works", 'link_audit: "P2全件実読判定→機械照合"',
                 "---", "", f"# {title}", "",
                 f"（作者: {author} ／ 类型: {kind} ／ 出典: {ref}）", "",
                 "## 冒頭（原文逐語・機械抽出）", "", "> " + head.replace("\n", "\n> "), "",
                 f"→ 投稿元: [[full/{uid}#post-{pn}|{ref}]]" + (f"（{dt}・[原文]({plink})）" if plink else ""), "",
                 "※ 本頁は Lane P（無作為カバレッジ監査→機械候補 1,189→LLM 全件実読判定 creative 1,034）による創作索引の増分。", ""]
        (OUT / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")
        ok += 1
        with PROG.open("a", encoding="utf-8") as fd:
            fd.write(ref + "\n")
    print(f"[laneP3] written={ok} skip={skip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

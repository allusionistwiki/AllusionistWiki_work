# -*- coding: utf-8 -*-
"""Lane P4: 第 2 スクリーニング（緩和基準）。
P1 で拾えなかった未収録投稿（全 30k 超の残りの大部分）を、緩い創作的マーカーで候補化。
基準: score2 >= 2（台詞密度・詩的行・題行・■ 見出し・改行密度のみ）。P2 判定ゲートへ渡す。
出力: data/yuragi_works_candidates_p4.json
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
SITE = W.parent / "YuragiWiki" / "content"
OUT = W / "data" / "yuragi_works_candidates_p4.json"


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


def score2(body: str) -> int:
    s = 0
    lines = [l for l in body.splitlines() if l.strip()]
    if re.search(r"^\s*【[^】]{2,25}】\s*$", body, re.M):
        s += 3
    if re.search(r"^\s*■", body, re.M):
        s += 2
    if len(lines) >= 6:
        s += 1
    if re.search(r"^\s*[「『]", body, re.M):
        s += 1
    if re.search(r"小説|詩|設定|二次|脚本|ドラマ|歌|歌詞", body):
        s += 1
    quoted = len(re.findall(r"[「『]", body))
    if quoted >= 3:
        s += 1
    if len(body) >= 300:
        s += 1
    if re.search(r"^\s*(第一|第[一二三四五六七八九十]|プロローグ|終章|epilogue|prologue)", body, re.M | re.I):
        s += 2
    if len(body) < 80:
        s -= 3
    return s


def main():
    covered = set()
    refpat = re.compile(r"YJ-[A-Za-z0-9]+:\d+")
    linkpat = re.compile(r"full/(YJ-[A-Za-z0-9]+)/p\d+#post-(\d+)")
    for wp in (SITE / "works").glob("*.md"):
        if wp.stem == "index":
            continue
        txt = wp.read_bytes().decode("utf-8", "replace")
        covered |= set(refpat.findall(txt))
        for uid0, pno0 in linkpat.findall(txt):
            covered.add(f"{uid0}:{pno0}")
    # 第 1 回候補は除外（P2 済）
    prev = set()
    p1 = W / "data" / "yuragi_works_candidates.json"
    if p1.is_file():
        for c in json.loads(p1.read_text(encoding="utf-8")):
            prev.add(c["ref"])
    units = []
    for l in (W / "work/yuragi/L0/runs/20261117T2021_l0c/units.jsonl").read_bytes().decode("utf-8", "replace").splitlines():
        if l.strip():
            units.append(json.loads(l)["unit_id"])
    cands = []
    n_posts = 0
    for uid in units:
        try:
            sd, meta = ex.unit_dir(uid)
        except Exception:
            continue
        for r in jl(sd / "structured.jsonl"):
            ref = f"{uid}:{r.get('post_no')}"
            if ref in covered or ref in prev:
                continue
            body = str(r.get("body", ""))
            n_posts += 1
            sc = score2(body)
            if sc >= 2:
                cands.append({"ref": ref, "uid": uid, "pno": r.get("post_no"),
                              "score": sc, "head": body[:220]})
    cands.sort(key=lambda x: -x["score"])
    OUT.write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[laneP4] 再走査投稿 {n_posts} / 緩和候補(score>=2) {len(cands)}")
    for c0 in cands[:12]:
        print(" ", c0["ref"], c0["score"], c0["head"][:50].replace("\n", " "))


if __name__ == "__main__":
    main()

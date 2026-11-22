# -*- coding: utf-8 -*-
"""Lane P Step1: 未収録投稿の創作候補スクリーニング（決定論・非 LLM）。

works 収録 ref を除く全投稿を、創作的マーカーで採点し候補化:
 +【題】行頭/単独行 / ■ 見出し / 詩的行数(改行>=6) / 「」台詞密度 / （※分割投稿）系メタ /
 冒頭が題行 / 句読みの文体 (です・ます・である調混在は減点軽微)
出力: data/yuragi_works_candidates.json（[{ref, uid, pno, score, head}] 降順）
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
SITE = W.parent / "YuragiWiki" / "content"
OUT = W / "data" / "yuragi_works_candidates.json"


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


def score(body: str) -> int:
    s = 0
    lines = [l for l in body.splitlines() if l.strip()]
    if re.search(r"^\s*【[^】]{2,25}】\s*$", body, re.M):
        s += 3
    if re.search(r"^\s*■", body, re.M):
        s += 2
    if len(lines) >= 10:
        s += 2
    elif len(lines) >= 6:
        s += 1
    if re.search(r"^\s*[「『]", body, re.M):
        s += 1
    if re.search(r"分割投稿|文字数制限|一応小説|小説】|詩】|設定】|二次】", body):
        s += 2
    if re.match(r"^\s*【", body):
        s += 2
    quoted = len(re.findall(r"[「『]", body))
    if quoted >= 8:
        s += 2
    if len(body) >= 600:
        s += 1
    # 会話・雑談寄りの減点
    if re.search(r"^>>\d", body, re.M) and len(lines) < 12:
        s -= 2
    if len(body) < 120:
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
            if ref in covered:
                continue
            body = str(r.get("body", ""))
            n_posts += 1
            sc = score(body)
            if sc >= 4:
                cands.append({"ref": ref, "uid": uid, "pno": r.get("post_no"),
                              "score": sc, "head": body[:220]})
    cands.sort(key=lambda x: -x["score"])
    OUT.write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[laneP1] 未収録投稿 {n_posts} / 候補(score>=4) {len(cands)}")
    for c0 in cands[:15]:
        print(" ", c0["ref"], c0["score"], c0["head"][:60].replace("\n", " "))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_edition_map.py — なろう版(正典baseline) <-> カクヨム版 の対応表 run を生成する。

方針（2026-10-17 確定）:
  - カクヨム版参照は ¶N 原生（サイト URL アンカー #pN と一致）。vault 流 pN 変換は行わない。
  - 本 run は「対応表」のみ（原文テキストは持たない → work repo 持ち込み禁止に抵触しない）。
  - 来歴: derived_from = L1 baseline run + raw 台帳 (AllusionistWiki_raw) 所在。

出力 (work/allusionist_v2/L0/runs/<run_id>/):
  run.json
  episode-map.jsonl      なろう chNNNNN -> カクヨム chNNNNN[] (title 照合, status auto|review)
  kakuyomu-only.jsonl    なろうに対応話なしのカクヨム話
  paragraph-map/chNNNNN.jsonl  なろう ¶N -> {k:[ch,¶M]|null, type: exact|edited|deleted}
  needs-review.jsonl     自動照合できなかった章
"""
import json, re, sys, unicodedata, hashlib, difflib
from datetime import datetime
from pathlib import Path

RAW = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_raw/raw/novel")
KAK = RAW / "kakuyomu/16816927859268545348_幻想再帰のアリュージョニスト"
SYO = RAW / "syosetu/n9073ca_幻想再帰のアリュージョニスト"
VAULT_RAW = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistLLMWiki2/raw")
WORK = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")

def norm(s):
    s = re.sub(r"（空）|\(空\)|⏎", "", s)
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\s\u3000]+", "", s)

def base_title(name):
    name = re.sub(r"\.md$", "", name)
    m = re.match(r"ch\d+(?:__|_)(.*)", name)
    t = m.group(1) if m else name
    t = re.sub(r"_\d\d$", "", t)
    t = re.sub(r"[①②③④⑤⑥⑦⑧⑨]$", "", t)
    t = re.sub(r"^幻想再帰のアリュージョニスト - ", "", t)
    t = re.sub(r"^\d+-\d+\s*", "", t)
    return norm(t)

# ---------- kakuyomu episodes ----------
def kakuyomu_paras(path):
    """return [(¶N, text, kind)] kind: text|struct"""
    lines = path.read_text(encoding="utf-8").splitlines()
    body, idx, started = [], [], False
    for l in lines:
        if l.strip().startswith("【"):
            continue
        if l.strip().startswith("¶"):
            started = True
        (idx if started else body).append(l)
    index = {}
    for l in idx:
        m = re.match(r"^¶(\d+)\s*(.*)$", l.strip())
        if m:
            index[int(m.group(1))] = m.group(2)
    while body and body[-1] == "":
        body.pop()
    walk = []
    for l in body:
        if l == "":
            walk.append(("brk", ""))
        elif l.strip() == "":
            walk.append(("empty", ""))
        else:
            walk.append(("text", l.strip()))
    while walk and walk[-1][0] != "text":
        walk.pop()
    def align(cand):
        if len(cand) != len(index):
            return False
        for n, (kind, txt) in enumerate(cand, start=1):
            prev = index.get(n, "")
            if kind == "text":
                if prev in ("（空）", "⏎") or not txt.startswith(prev[:12]):
                    return False
            elif kind == "brk":
                if prev != "⏎":
                    return False
            else:  # empty
                if prev != "（空）":
                    return False
        return True
    paras = None
    for o in range(0, 8):
        cand = walk[o:]
        if align(cand):
            paras = cand; break
    assert paras is not None, f"{path.name}: no alignment (walk {len(walk)} vs index {len(index)})"
    return paras

def ep_id(path):
    m = re.search(r"episodes/(\d+)", path.read_text(encoding="utf-8", errors="replace")[:600])
    return m.group(1) if m else ""

kak = {}  # ch -> {title, paras, ep_id}
for p in sorted(KAK.glob("*.md")):
    ch = int(re.match(r"ch(\d+)", p.name).group(1))
    kak[ch] = {"title": base_title(p.name), "paras": kakuyomu_paras(p), "ep_id": ep_id(p)}

# ---------- syosetu chapters (vault raw = 正典 ¶) ----------
def vault_paras(path):
    """return [(¶N, text)] from 【pN】 blocks; p4 title line dropped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    cur = None
    for l in lines:
        m = re.match(r"^【p(\d+)】$", l.strip())
        if m:
            cur = int(m.group(1)); out.append([cur, []]); continue
        if cur is not None:
            if re.match(r"^\d+$", l.strip()):
                continue
            out[-1][1].append(l.strip())
    res = []
    for n, blk in out:
        txt = "　".join(blk)
        if n == 4 and blk:  # drop title line merged into p4
            txt = "　".join(blk[1:]) if len(blk) > 1 else ""
        res.append((n, txt))
    return res

sy = {}
for p in sorted(VAULT_RAW.glob("ch*.txt")):
    ch = int(re.match(r"ch(\d+)", p.name).group(1))
    sy[ch] = vault_paras(p)
sy_title = {}
for p in sorted(SYO.glob("*.md")):
    ch = int(re.match(r"ch(\d+)", p.name).group(1))
    sy_title.setdefault(ch, base_title(p.name))

# ---------- episode map (title 照合, 順序グリーディ) ----------
kak_by_title = {}
for ch in sorted(kak):
    kak_by_title.setdefault(kak[ch]["title"], []).append(ch)

used = set()
emap = []
for ch in sorted(sy):
    t = sy_title.get(ch, "")
    cands = [c for c in kak_by_title.get(t, []) if c not in used]
    if not cands:
        emap.append({"syosetu_ch": ch, "title": t, "kakuyomu": [], "status": "needs_review"})
        continue
    # 同一タイトルが複数章に存在する場合: 直前の章の次以降の最小 ch を採る
    prev_max = max([max(e["kakuyomu"]) for e in emap if e["kakuyomu"]], default=0)
    after = [c for c in cands if c > prev_max]
    pick = after or cands
    used.update(pick)
    emap.append({"syosetu_ch": ch, "title": t,
                 "kakuyomu": pick,
                 "status": "auto" if len(kak_by_title[t]) == 1 or len(pick) > 1 else "review"})

kaku_only = sorted(set(kak) - used)

# ---------- paragraph map ----------
stats = {"exact": 0, "edited": 0, "deleted": 0, "kaku_new": 0, "chapters": 0}
def para_map(ch):
    entry = next(e for e in emap if e["syosetu_ch"] == ch)
    if not entry["kakuyomu"]:
        return None
    s_paras = sy[ch]
    k_paras = []
    for kc in entry["kakuyomu"]:
        for n, (kind, txt) in kak[kc]["paras"]:
            if kind == "text":
                k_paras.append((kc, n, txt))
    s_keys = [norm(t) for _, t in s_paras]
    k_keys = [norm(t) for _, _, t in k_paras]
    sm = difflib.SequenceMatcher(None, s_keys, k_keys, autojunk=False)
    rows = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for di in range(i2 - i1):
                rows.append({"s": s_paras[i1+di][0], "k": list(k_paras[j1+di][:2]), "type": "exact"})
                stats["exact"] += 1
        elif tag == "replace":
            for di in range(max(i2-i1, j2-j1)):
                s = s_paras[i1+di][0] if i1+di < i2 else None
                k = list(k_paras[j1+di][:2]) if j1+di < j2 else None
                rows.append({"s": s, "k": k, "type": "edited"})
                stats["edited"] += 1
        elif tag == "delete":
            for di in range(i2-i1):
                rows.append({"s": s_paras[i1+di][0], "k": None, "type": "deleted"})
                stats["deleted"] += 1
        elif tag == "insert":
            for dj in range(j2-j1):
                rows.append({"s": None, "k": list(k_paras[j1+dj][:2]), "type": "kaku_new"})
                stats["kaku_new"] += 1
    return rows

# ---------- write run ----------
now = datetime.now()
h = hashlib.sha1((str(now) + str(len(kak)) + str(len(sy))).encode()).hexdigest()[:4]
run_id = now.strftime("%Y%m%dT%H%M_") + h
run_dir = WORK / "work/allusionist_v2/L0/runs" / run_id
(run_dir / "paragraph-map").mkdir(parents=True, exist_ok=True)

for e in emap:
    if e["kakuyomu"]:
        rows = para_map(e["syosetu_ch"])
        stats["chapters"] += 1
        (run_dir / "paragraph-map" / f"ch{e['syosetu_ch']:05d}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

(run_dir / "episode-map.jsonl").write_text(
    "\n".join(json.dumps(e, ensure_ascii=False) for e in emap) + "\n", encoding="utf-8")
(run_dir / "kakuyomu-only.jsonl").write_text(
    "\n".join(json.dumps({"kakuyomu_ch": c, "title": kak[c]["title"], "ep_id": kak[c]["ep_id"]},
                         ensure_ascii=False) for c in kaku_only) + "\n", encoding="utf-8")
(run_dir / "needs-review.jsonl").write_text(
    "\n".join(json.dumps(e, ensure_ascii=False) for e in emap if e["status"] == "needs_review") + "\n",
    encoding="utf-8")

run_json = {
    "run_id": run_id,
    "layer": "L0",
    "kind": "edition-map",
    "created": now.isoformat(timespec="seconds"),
    "derived_from": {
        "l1_run": "20261012T0000_baseline",
        "raw_ledger_syosetu": "AllusionistWiki_raw/raw/novel/syosetu/n9073ca_幻想再帰のアリュージョニスト",
        "raw_ledger_kakuyomu": "AllusionistWiki_raw/raw/novel/kakuyomu/16816927859268545348_幻想再帰のアリュージョニスト",
        "vault_raw_syosetu": "AllusionistLLMWiki2_Obsidian/raw (chNNNN.txt, 【pN】 正典)",
    },
    "policy": "カクヨム参照は ¶N 原生（URL アンカー #pN 対応）。vault 流 pN 変換は行わない。",
    "tool": "scripts/build_edition_map.py",
    "stats": {**stats, "syosetu_chapters": len(sy), "kakuyomu_episodes": len(kak),
              "mapped_chapters": stats["chapters"], "kakuyomu_only": len(kaku_only),
              "needs_review": sum(1 for e in emap if e["status"] == "needs_review")},
}
(run_dir / "run.json").write_text(json.dumps(run_json, ensure_ascii=False, indent=1), encoding="utf-8")
(WORK / "work/allusionist_v2/L0/latest.txt").write_text(run_id + "\n", encoding="utf-8")

# runs-index update
ri_path = WORK / "work/allusionist_v2/index/runs-index.json"
ri = json.loads(ri_path.read_text(encoding="utf-8"))
ri.setdefault("L0", {})[run_id] = {"path": f"work/allusionist_v2/L0/runs/{run_id}", "status": "active",
                                   "kind": "edition-map", "derived_from": "20261012T0000_baseline"}
ri_path.write_text(json.dumps(ri, ensure_ascii=False, indent=1), encoding="utf-8")

print(json.dumps(run_json["stats"], ensure_ascii=False, indent=1))
print("run:", run_id)

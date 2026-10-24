#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_quote_map.py — なろう版 baseline facts の引用文をカクヨム版で全文検索し、
引用→カクヨム ¶ アンカーの対応表を作る（2026-10-17 方針: 短文引用検索、不一致のみ再解析）。

方針:
  - カクヨム参照は ¶N 原生（サイト URL アンカー #pN）。
  - 対応表は引用単位: 完全一致した引用は ¶ アンカー確定、不一致は再解析キュー行き。
  - 原文全文は持たない（引用は既存 facts 内の引用範囲まで → work repo 運用則に適合）。

出力 (work/allusionist_v2/L0/runs/<run_id>/):
  run.json
  episode-map.jsonl            なろう chNNNNN -> カクヨム ch[] (title 照合)
  quote-map/chNNNNN.jsonl      {s_para, quote_head, k:[ch,¶start,¶end]|null}
  needs-reanalysis.jsonl       完全一致しなかった引用 {type, episode, s_para, quote_head}
  kakuyomu-only.jsonl          なろう対応なしのカクヨム話
"""
import json, re, sys, unicodedata, hashlib, bisect
from datetime import datetime
from pathlib import Path

RAW = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_raw/raw/novel")
KAK = RAW / "kakuyomu/16816927859268545348_幻想再帰のアリュージョニスト"
SYO = RAW / "syosetu/n9073ca_幻想再帰のアリュージョニスト"
BASE = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/work/allusionist_v2/L1/runs/20261012T0000_baseline")
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
    t = re.sub(r"[\u2460-\u2473\u3220-\u3229\u3251-\u325F\u32B1-\u32BF]$", "", t)  # 丸数字 ①-㊿
    t = re.sub(r"^幻想再帰のアリュージョニスト - ", "", t)
    t = re.sub(r"^\d+-\d+\s*", "", t)
    t = re.sub(r"^(幕間|終節|転章|祝祭前夜|死人の森の断章|アポテオーズ)[：:〆\s]*", "", t)  # 接頭辞語
    t = re.sub(r"^\d+-\d+\s*", "", t)
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[\s\u3000()（）《》「」『』\[\]【】｛｝<>〈〉・・\\-—ー〜~〜]+", "", t)  # 括弧・記号を無視
    return t

def kakuyomu_paras(path):
    """[(¶N, text)] — テキスト¶のみ: 本文の非空行を索引のテキストpreview順に対応させる.
    構造¶ (⏎/⏎⏎/（空）) は検索に不要なので復元しない。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    body, idx, started = [], [], False
    for l in lines:
        if re.match(r"^【(kakuyomu ep|公開|章|URL|段落数|¶索引)", l.strip()):
            continue
        if l.strip().startswith("¶"):
            started = True
        (idx if started else body).append(l)
    index = {}
    for l in idx:
        m = re.match(r"^¶(\d+)\s*(.*)$", l.strip())
        if m:
            index[int(m.group(1))] = m.group(2)
    text_idx = [n for n in sorted(index)
                if index[n] not in ("⏎", "⏎⏎", "（空）")
                and not re.fullmatch(r"[⏎（空）]+", index[n])]
    out = []
    k = 0
    for l in body:
        if l.strip() == "":
            continue
        if k >= len(text_idx):
            raise AssertionError(f"{path.name}: extra body line {l[:20]!r} beyond ¶ index")
        n = text_idx[k]
        prev = index[n]
        if not l.strip().startswith(prev[:12]):
            raise AssertionError(f"{path.name}: ¶{n} preview {prev[:14]!r} vs body {l[:20]!r}")
        out.append((n, l.strip()))
        k += 1
    if k != len(text_idx):
        raise AssertionError(f"{path.name}: {len(text_idx)-k} text ¶ unmatched (body short)")
    return out

def ep_id(path):
    m = re.search(r"episodes/(\d+)", path.read_text(encoding="utf-8", errors="replace")[:600])
    return m.group(1) if m else ""

kak = {}
for p in sorted(KAK.glob("*.md")):
    ch = int(re.match(r"ch(\d+)", p.name).group(1))
    kak[ch] = {"title": base_title(p.name), "paras": kakuyomu_paras(p), "ep_id": ep_id(p)}

sy_title = {}
sy_vol = {}
for p in sorted(SYO.glob("*.md")):
    ch = int(re.match(r"ch(\d+)_", p.name).group(1))
    sy_title.setdefault(ch, base_title(p.name))
    m = re.search(r" - (\d+)-\d+", p.name)
    sy_vol[ch] = int(m.group(1)) if m else None
prev = 0
for ch in sorted(sy_vol):
    if sy_vol[ch] is None:
        sy_vol[ch] = prev
    prev = sy_vol[ch]

kak_vol = {}
for ch in sorted(kak):
    m = re.match(r"^(\d+)-\d+", re.match(r"ch\d+__(.+)\.md$", sorted(KAK.glob(f"ch{ch:05d}__*.md"))[0].name).group(1))
    kak_vol[ch] = int(m.group(1)) if m else None
prev = 0
for ch in sorted(kak_vol):
    if kak_vol[ch] is None:
        kak_vol[ch] = prev
    prev = kak_vol[ch]

# 巻別コーパス: 引用ヒットが対応を直接与える (タイトル照合は使わない)
vol_corpus = {}
for v in sorted(set(kak_vol.values())):
    text = ""
    pos = []
    for kc in sorted(c for c in kak if kak_vol[c] == v):
        for n, txt in kak[kc]["paras"]:
            nt = norm(txt)
            if not nt:
                continue
            pos.append((len(text), kc, n))
            text += nt
    vol_corpus[v] = (text, pos)

def locate(pos, start, length):
    ends = [p[0] for p in pos]
    i = bisect.bisect_right(ends, start) - 1
    p0 = pos[i]
    j = bisect.bisect_right(ends, start + length - 1) - 1
    p1 = pos[j]
    return [p0[1], p0[2], p1[1], p1[2]]

# load baseline facts quotes
facts = []
for d in ["facts", "events", "appearance_facts", "deferral_facts"]:
    for f in (BASE / d).glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            q = r.get("quote") or ""
            if not q:
                for qq in r.get("quotes", []) or []:
                    if isinstance(qq, dict) and qq.get("quote"):
                        q = qq["quote"]; break
            m = re.match(r"ch(\d+)", r.get("episode", ""))
            if not m:
                continue
            facts.append((d, int(m.group(1)), r.get("paragraph", ""), q))

now = datetime.now()
h = hashlib.sha1((str(now) + str(len(facts))).encode()).hexdigest()[:4]
run_id = now.strftime("%Y%m%dT%H%M_") + h
run_dir = WORK / "work/allusionist_v2/L0/runs" / run_id
(run_dir / "quote-map").mkdir(parents=True, exist_ok=True)

stats = {"total": 0, "hit": 0, "miss": 0, "no_volume": 0}
per_ch = {}
hits_by_ch = {}
reanalysis = []
for d, ch, s_para, q in facts:
    stats["total"] += 1
    nq = norm(q)
    if not nq:
        continue
    v = sy_vol.get(ch)
    if v not in vol_corpus:
        stats["no_volume"] += 1
        reanalysis.append({"type": d, "episode": ch, "s_para": s_para,
                           "quote_head": q[:40], "reason": "no_volume_corpus"})
        continue
    text, pos = vol_corpus[v]
    idx = text.find(nq)
    head = q[:40]
    if idx >= 0:
        stats["hit"] += 1
        loc = locate(pos, idx, len(nq))
        per_ch.setdefault(ch, []).append({"s_para": s_para, "quote_head": head,
                                          "k": loc, "type": d})
        hits_by_ch.setdefault(ch, set()).add(loc[0])
        hits_by_ch.setdefault(ch, set()).add(loc[2])
    else:
        stats["miss"] += 1
        reanalysis.append({"type": d, "episode": ch, "s_para": s_para,
                           "quote_head": head, "reason": "no_exact_match"})

# episode map: 引用ヒットから導出 (なろう ch -> ヒットしたカクヨム ch 集合)
emap = {}
for ch in sorted(sy_title):
    hits = sorted(hits_by_ch.get(ch, []))
    emap[ch] = {"title": sy_title[ch], "kakuyomu": hits,
                "status": "hit-derived" if hits else "needs_review"}
used = set(h for hs in hits_by_ch.values() for h in hs)
kaku_only = sorted(set(kak) - used)

for ch, rows in per_ch.items():
    (run_dir / "quote-map" / f"ch{ch:05d}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
(run_dir / "needs-reanalysis.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in reanalysis) + "\n", encoding="utf-8")
(run_dir / "episode-map.jsonl").write_text(
    "\n".join(json.dumps({"syosetu_ch": c, **emap[c]}, ensure_ascii=False) for c in sorted(emap)) + "\n",
    encoding="utf-8")
(run_dir / "kakuyomu-only.jsonl").write_text(
    "\n".join(json.dumps({"kakuyomu_ch": c, "title": kak[c]["title"], "ep_id": kak[c]["ep_id"]},
                         ensure_ascii=False) for c in kaku_only) + "\n", encoding="utf-8")

run_json = {
    "run_id": run_id, "layer": "L0", "kind": "quote-map",
    "created": now.isoformat(timespec="seconds"),
    "derived_from": {
        "l1_run": "20261012T0000_baseline",
        "raw_ledger_syosetu": "AllusionistWiki_raw/raw/novel/syosetu/n9073ca_幻想再帰のアリュージョニスト",
        "raw_ledger_kakuyomu": "AllusionistWiki_raw/raw/novel/kakuyomu/16816927859268545348_幻想再帰のアリュージョニスト",
    },
    "policy": "カクヨム参照は ¶N 原生（URL #pN 対応）。引用全文一致で ¶ 対応を確定、不一致は再解析。",
    "tool": "scripts/build_quote_map.py",
    "stats": {**stats, "syosetu_chapters": len(emap), "kakuyomu_episodes": len(kak),
              "kakuyomu_only": len(kaku_only),
              "chapters_needing_review": sum(1 for v in emap.values() if v["status"] == "needs_review")},
}
(run_dir / "run.json").write_text(json.dumps(run_json, ensure_ascii=False, indent=1), encoding="utf-8")
(WORK / "work/allusionist_v2/L0/latest.txt").write_text(run_id + "\n", encoding="utf-8")
ri_path = WORK / "work/allusionist_v2/index/runs-index.json"
ri = json.loads(ri_path.read_text(encoding="utf-8"))
ri.setdefault("L0", {})[run_id] = {"path": f"work/allusionist_v2/L0/runs/{run_id}", "status": "active",
                                   "kind": "quote-map", "derived_from": "20261012T0000_baseline"}
ri_path.write_text(json.dumps(ri, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(run_json["stats"], ensure_ascii=False, indent=1))
print("run:", run_id)

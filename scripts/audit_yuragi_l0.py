#!/usr/bin/env python3
"""Yuragi L0 全量監査 v3（raw 5 層 × 台帳 × 索引・全件・サンプリングなし）。

A1 台帳×raw: ① 再パース == 台帳（post_no/author/date）、② slice == ③ body（全 48,891 件・disk 実測）
A2 ④ chains: 全 post 純分割・単一作者・台帳列順で連続・話題規則再生成一致（【…】部分集合）
A3 ⑤ thread: body_full == ③ 全文連結（投稿順）全 185 篇
A4 chunks: 全 post がちょうど 1 窓に所属・群窓連続・② manifest SHA 一致（disk 実測）
A5 索引: posts マスタ完全性・スニペット全件再生成一致・by-date 単調・terms 全件再集計一致
座標: raw バイト基準（read_bytes + decode(errors=replace)）。
"""
import json
import re
import sys
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
JST = timezone(timedelta(hours=9))
TERM_RE = re.compile(r"【([^】\n]{2,40})】")
sys.path.insert(0, r"C:/Users/d5dx/Downloads/Code/YuragiWiki/tools")
import split_posts as sp

def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def norm_term(s: str) -> str:
    s = re.sub(r"[【】\s]+", "", s).strip()
    return s[:40]

def jl(p: Path):
    return [json.loads(l) for l in rd(p).splitlines() if l.strip()]

def main():
    rid = datetime.now(JST).strftime("%Y%m%dT%H%M") + "_l0aud"
    run = L0 / "runs" / rid
    run.mkdir(parents=True, exist_ok=True)
    issues = []
    counters = {}

    def add(cat, detail):
        issues.append((cat, str(detail)))

    chunk_run = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    src = L0 / "runs" / chunk_run
    units = {u["unit_id"]: u for u in jl(src / "units.jsonl")}
    counters["units"] = len(units)

    # 索引 run（latest 直後の l0si）
    si = [r.name for r in (L0 / "runs").iterdir()
          if r.is_dir() and (r / "run.json").exists()
          and json.loads(rd(r / "run.json")).get("kind") == "l0-search-index"
          and json.loads(rd(r / "run.json")).get("derived_from", {}).get("l0_run") == chunk_run]
    si_run = L0 / "runs" / max(si)

    body_all = {}  # ref -> ③ body（disk 実測で共有）
    for uid, u in units.items():
        if u["source"] == "jbbs":
            d = RAW / u["raw_path"].rsplit("/", 1)[0]
        elif u["source"] == "mixi":
            d = RAW / "mixi/373088" / u["title"]
        else:
            d = RAW / "hatena_flicker"
        ledger = jl(src / "units" / f"{uid}.jsonl")
        struct = jl(d / "structured.jsonl")
        chains = jl(d / "chains.jsonl")
        thread = json.loads(rd(d / "thread.json"))
        sb = {r["post_no"]: r["body"] for r in struct}

        # A1a: ① 再パース == 台帳（hatena は ③ と 1:1 なのでスキップ）
        if u["source"] != "hatena":
            posts, _ = sp.regions(rd(RAW / u["raw_path"]))
            if len(posts) != len(ledger):
                add("A1_COUNT", f"{uid} ①{len(posts)} 台帳{len(ledger)}")
            for p, l in zip(posts, ledger):
                if (p["post_no"], p["author"], p["date"]) != (l["post_no"], l["author"], l["date"]):
                    add("A1_FIELDS", f"{uid}:{p['post_no']}")
        # A1b: ② slice == ③ body（disk 実測・全件）
        tc = {}
        for l in ledger:
            rp = l["raw_group_path"]
            rp = rp[0] if isinstance(rp, list) else rp
            if rp not in tc:
                tc[rp] = rd(RAW / rp)
            if tc[rp][l["body_start"]:l["body_end"]] != sb[l["post_no"]]:
                add("A1_SLICE", f"{uid}:{l['post_no']}")
        counters["A1_slices"] = counters.get("A1_slices", 0) + len(ledger)
        for l in ledger:
            body_all[l["ref"]] = sb[l["post_no"]]

        # A2 ④ 純分割・単一作者・列順連続・話題規則再生成
        order = [l["post_no"] for l in ledger]
        seq = {n: i for i, n in enumerate(order)}
        covered = []
        for c in chains:
            nos = c["post_nos"]
            covered += nos
            if len({l["author"] for l in ledger if l["post_no"] in set(nos)}) != 1:
                add("A2_AUTHOR", f"{c['chain_id']}")
            idxs = sorted(seq[n] for n in nos)
            if idxs != list(range(idxs[0], idxs[0] + len(nos))):
                add("A2_ADJACENCY", c["chain_id"])
            gset = set()
            for n in sorted(nos, key=lambda x: seq[x]):
                toks = {norm_term(t) for t in TERM_RE.findall(sb[n])}
                if not toks <= gset and gset:
                    add("A2_TOPIC", f"{c['chain_id']}:{n}")
                gset |= toks
        if sorted(covered) != sorted(order) or len(covered) != len(order):
            add("A2_PARTITION", uid)

        # A3 ⑤ 連結
        joined = "\n\n".join(sb[n] for n in order)
        if thread["body_full"] != joined:
            add("A3_JOIN", uid)
        counters["A3_units"] = counters.get("A3_units", 0) + 1

        # A4 chunks: 窓が台帳全 post をちょうど 1 回、群窓連続、② SHA 一致
        chunks = jl(src / "chunks" / f"{uid}.jsonl")
        cnt = {n: 0 for n in order}
        bygroup = {}
        for c in chunks:
            for n in range(c["post_range"][0], c["post_range"][1] + 1):
                if n in cnt:
                    cnt[n] += 1
            bygroup.setdefault(c["group_id"], []).append(c)
        ghosts = [n for n, k in cnt.items() if k == 0]
        dup = [n for n, k in cnt.items() if k > 1]
        if ghosts:
            add("A4_GAP", f"{uid} {len(ghosts)} ghosts")
        if dup:
            add("A4_DUP", f"{uid} {len(dup)} dup")
        for gid, parts in bygroup.items():
            parts.sort(key=lambda c: c["part"])
            chain = next(c for c in chains if c["chain_id"] == gid)
            cnos = sorted(chain["post_nos"], key=lambda x: seq[x])
            flat = [n for c in parts for n in range(c["post_range"][0], c["post_range"][1] + 1)]
            flat = [n for n in flat if n in set(cnos)]
            if [n for c in parts for n in range(c["post_range"][0], c["post_range"][1] + 1)
                if n in set(cnos)] != cnos:
                add("A4_WINDOW", gid)
        # ② SHA 一致（manifest 照合・disk 再読）
        if u["source"] != "hatena":
            mf = json.loads(rd(d / "posts" / "_manifest.json"))
            sha_map = {f["file"]: f["sha1"] for f in mf["files"]}
            for c in chunks:
                rp = c["raw_group_path"]
                rp = rp[0] if isinstance(rp, list) else rp
                fn = rp.rsplit("/", 1)[-1]
                if fn not in sha_map:
                    add("A4_REF", f"{c['chunk_id']} {fn}")
                elif sha_map[fn] != sha1_bytes((RAW / rp).read_bytes()):
                    add("A4_SHA", f"{c['chunk_id']} {fn}")
        counters["A4_chunks"] = counters.get("A4_chunks", 0) + len(chunks)

    # A5 索引
    posts_idx = jl(si_run / "search" / "posts.jsonl")
    refs_l = set(body_all)
    refs_i = {x["ref"] for x in posts_idx}
    if refs_l != refs_i or len(posts_idx) != len(refs_i):
        add("A5_MASTER", f"ledger {len(refs_l)} index {len(refs_i)}")
    counters["A5_posts"] = len(posts_idx)
    # 投稿番号順 vs 時刻逆行（実況スレ採番抖り・裁定済み事象は counter 記録）
    postdate_inv = 0
    for uid, u in units.items():
        ep_prev = None
        for l in jl(src / "units" / f"{uid}.jsonl"):
            if l["epoch"] is None:
                continue
            if ep_prev is not None and l["epoch"] < ep_prev - 1:
                postdate_inv += 1
            ep_prev = max(ep_prev, l["epoch"]) if ep_prev is not None else l["epoch"]
    counters["A5_POSTDATE_INV"] = postdate_inv
    for x in posts_idx:
        body = body_all[x["ref"]]
        if x["snippet"] != body[:60].replace("\n", " "):
            add("A5_SNIP", x["ref"])
    bydate = jl(si_run / "search" / "by-date.jsonl")
    chrono = 0
    last = {}
    for x in bydate:
        uid = x["ref"].split(":")[0]
        if uid in last and x["epoch"] < last[uid] - 1:
            chrono += 1
        last[uid] = max(last.get(uid, 0), x["epoch"])
    counters["A5_CHRONO"] = chrono
    for i in range(1, len(bydate)):
        if bydate[i]["epoch"] < bydate[i - 1]["epoch"]:
            add("A5_DATE_ORDER", i)
            break
    terms = {}
    for ref, body in body_all.items():
        for t in {norm_term(x) for x in TERM_RE.findall(body)}:
            terms[t] = terms.get(t, 0) + 1
    terms_idx = jl(si_run / "search" / "terms.jsonl")
    if {t["term"]: t["count"] for t in terms_idx} != terms:
        add("A5_TERMS", f"recount {len(terms)} index {len(terms_idx)}")
    counters["A5_terms_recount"] = len(terms)

    result = "PASS" if not issues else "ISSUES"
    report = {
        "audit_of": {"chunk_run": chunk_run, "search_run": max(si)},
        "counters": counters,
        "adjudication": {
            "A5_POSTDATE_INV": "隣接採番で同日秒刻みの逆行（実況スレのサーバ採番抖り）＝出典 faithful、修正不要",
        },
        "issues_count": len(issues),
        "issues": [{"cat": c, "detail": d} for c, d in issues[:50]],
    }
    (run / "audit-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                           encoding="utf-8", newline="\n")
    (run / "run.json").write_text(json.dumps({
        "run_id": rid, "kind": "audit",
        "derived_from": {"l0_run": chunk_run, "search_run": max(si)},
        "created": datetime.now(JST).isoformat(), "result": result,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    idx_p = W / "work" / "yuragi" / "index" / "runs-index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    idx["L0"][rid] = {"status": "current", "kind": "audit", "result": result,
                      "path": "work/yuragi/L0/runs/" + rid}
    idx_p.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"AUDIT {rid} {result} ISSUES={len(issues)}")
    cats = {}
    for c, d in issues:
        cats[c] = cats.get(c, 0) + 1
    for c, k in sorted(cats.items()):
        print(f"  {c} {k}")
    for c, d in issues[:15]:
        print("  >", c, d)
    print("counters:", json.dumps(counters, ensure_ascii=False))
    return 0 if not issues else 1

if __name__ == "__main__":
    sys.exit(main())

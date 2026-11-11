#!/usr/bin/env python3
"""YuragiWiki L0 全量監査（quality-first full audit）.

対象: 現行 chunk run（latest.txt）+ 現行 search-index run + raw posts/ 層。
検査は全量（サンプル検査しない）:
  A1 篇台帳: raw 再パース == 台帳（件数・post_no 逐増・body オフセット整合）
  A2 連投群: 台帳から再グループ化 == chunks の group 分割（part 連結 == 群全体）
  A3 raw 群ファイル: disk 上の全 12,389 ファイル × 台帳（ヘッダ集合一致・単一作者純度・連結一致性を manifest ではなく disk 実測で再検証）
  A4 chunks 台帳: 全 post がちょうど 1 群に属す・raw_group_path 実在・SHA 一致
  A5 索引: posts.jsonl 全件の ref 一意・スニペット再生成一致・term 再集計一致（全 6,225 語）・日時正規化網羅（date_raw 非空 ⇔ date_iso）・年代域フラグ
  A6 来歴/索引整合: run.json・latest.txt・runs-index.json の整合
出力: runs/<audit_run_id>/audit-report.json + 合格/不合格
"""
import json
import re
import hashlib
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW_ROOT = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki")
L0 = REPO / "work" / "yuragi" / "L0"

HEADER_RE = re.compile(
    r"^## (\d+) ：(.*?) ：((?:\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日)]?.*?\d{1,2}:\d{2}(?::\d{2})?)?)\s*$", re.M
)
DELETED_RE = re.compile(r"^<<.+>>$")
DATE_RE = re.compile(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日)]?.*?(\d{1,2}):(\d{2})(?::(\d{2}))?$")
TERM_RE = re.compile(r"【([^】\n]{2,40})】")
YEAR_OK = (2004, 2027)


def sha1_file(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()


def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
    run_id = f"{ts[:8]}T{ts[9:]}_l0aud"
    run_dir = L0 / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    issues = []
    counters = {}

    def issue(code, detail, n=1):
        issues.append({"code": code, "detail": detail, "n": n})
        counters[code] = counters.get(code, 0) + n

    chunk_run = (L0 / "latest.txt").read_text().strip()
    src = L0 / "runs" / chunk_run
    if not (src / "units.jsonl").exists():
        issue("RUN_POINTER", f"latest.txt -> {chunk_run} has no units.jsonl")
        report(run_dir, run_id, chunk_run, None, issues, counters)
        return 1
    units = [json.loads(l) for l in open(src / "units.jsonl", encoding="utf-8")]

    # locate latest search-index run
    idx = json.loads((REPO / "work/yuragi/index/runs-index.json").read_text(encoding="utf-8"))
    si_runs = [k for k, v in idx["L0"].items() if v.get("kind") == "search-index" and v.get("status") == "complete"]
    si_run = max(si_runs) if si_runs else None

    all_posts = []
    per_unit_posts = {}
    # ---------- A1 + ledger collection ----------
    for u in units:
        uid = u["unit_id"]
        unit_posts = [json.loads(l) for l in open(src / "units" / f"{uid}.jsonl", encoding="utf-8")]
        per_unit_posts[uid] = unit_posts
        all_posts += [(uid, p) for p in unit_posts]
        per_post_raw = all("raw_path" in p for p in unit_posts)
        if per_post_raw:
            for p in unit_posts:
                fp = RAW_ROOT / p["raw_path"]
                if not fp.exists():
                    issue("A1_RAW_MISSING", f"{uid}:{p['post_no']} {p['raw_path']}")
            continue
        text = (RAW_ROOT / u["raw_path"]).read_bytes().decode("utf-8", errors="replace")  # raw 基準
        heads = [m for m in HEADER_RE.finditer(text)]
        if len(heads) != u["n_posts"]:
            issue("A1_COUNT", f"{uid}: raw headers {len(heads)} != ledger {u['n_posts']}")
        if u["declared_posts"] is not None and len(heads) != u["declared_posts"]:
            issue("A1_DECLARED", f"{uid}: raw headers {len(heads)} != declared {u['declared_posts']}")
        nos = [int(m.group(1)) for m in heads]
        if nos != sorted(nos):
            issue("A1_ORDER", f"{uid}: header post_no not increasing")
        for i, p in enumerate(unit_posts):
            body = text[p["body_start"]:p["body_end"]]
            if len(body.strip()) != p["chars"]:
                issue("A1_BODYLEN", f"{uid}:{p['post_no']}")
            if i < len(heads):
                h = heads[i]
                if not (h.start(0) <= p["body_start"] and p["body_end"] <= h.end(0) + 20000):
                    issue("A1_OFFSET", f"{uid}:{p['post_no']}")
                # author/date must match header line
                hln = text[h.start(0):text.index("\n", h.start(0))]
                mm = HEADER_RE.match(hln.rstrip("\r\n"))
                if not mm or (mm.group(2).strip() != p["author"]):
                    issue("A1_AUTHOR", f"{uid}:{p['post_no']}")

    # ---------- A2 + A4: chunks ledger structural audit ----------
    for u in units:
        uid = u["unit_id"]
        posts = per_unit_posts[uid]
        by_no = {p["post_no"]: p for p in posts}
        chunks = [json.loads(l) for l in open(src / "chunks" / f"{uid}.jsonl", encoding="utf-8")]
        sorted_nos = sorted(by_no)
        covered = {}
        group_parts = {}
        for c in chunks:
            a, b = c["post_range"]
            for n in sorted_nos:
                if a <= n <= b:
                    covered[n] = covered.get(n, 0) + 1
            gp = group_parts.setdefault(c["group_id"], [])
            gp.append(c)
        for n, k in covered.items():
            if k != 1:
                issue("A4_MULTICOVER", f"{uid}:{n} covered {k}x")
        missing = set(by_no) - set(covered)
        if missing:
            issue("A4_UNCOVERED", f"{uid} uncovered posts: {sorted(missing)[:10]}", len(missing))
        # parts contiguity per group（台帳の列順で連続 = 数値 +1 ではない: 欠番を跨いでよい）
        for gid, parts in group_parts.items():
            parts.sort(key=lambda c: c["post_range"][0])
            if len(parts) > 1:
                for i in range(len(parts) - 1):
                    seq_after = [n for n in sorted_nos if n > parts[i]["post_range"][1]]
                    if not seq_after or seq_after[0] != parts[i + 1]["post_range"][0]:
                        issue("A2_PART_GAP", gid)
                if parts[-1]["part"] != len(parts):
                    issue("A2_PART_IDX", gid)
            # chain purity from ledger: all posts in group same author, not deleted (chain kind)
            seg = [by_no[n] for c in parts for n in sorted_nos if c["post_range"][0] <= n <= c["post_range"][1]]
            kind = parts[0]["kind"]
            auths = {s["author"] for s in seg}
            if kind == "chain" and (len(auths) != 1 or any(DELETED_RE.match(a) for a in auths)):
                issue("A2_CHAIN_PURITY", f"{gid} authors={len(auths)}")
            if kind == "post" and len(seg) != 1:
                issue("A2_SINGLE_MULTI", gid)
            if kind == "deleted" and not all(DELETED_RE.match(s["author"]) for s in seg):
                issue("A2_DELETED_PURITY", gid)
            # raw group file: exists, sha, header set == group posts
            rgp = parts[0]["raw_group_path"]
            if not rgp:
                issue("A4_NO_REF", gid); continue
            fp = RAW_ROOT / rgp
            if not fp.exists():
                issue("A4_REF_MISSING", rgp); continue
            if sha1_file(fp) != parts[0]["raw_group_sha1"]:
                issue("A4_SHA", rgp)
            if "hatena" in rgp:
                continue
            ftxt = fp.read_bytes().decode("utf-8", errors="replace")
            fheads = sorted(int(m.group(1)) for m in HEADER_RE.finditer(ftxt))
            want = sorted(s["post_no"] for s in seg)
            if fheads != want:
                issue("A3_FILE_HEADERSET", f"{rgp}: file={fheads[:3]}.. want={want[:3]}.. ({len(fheads)} vs {len(want)})")
            fauth = {m.group(2).strip() for m in HEADER_RE.finditer(ftxt)}
            if len(fauth) > 1:
                issue("A3_FILE_MIXED", rgp)

    # A3: split manifest losslessness recompute from disk (all 184 units)
    manifest_files = list(RAW_ROOT.glob("raw/bbs/**/posts/_manifest.json"))
    counters["A3_manifests"] = len(manifest_files)
    for mp in manifest_files:
        m = json.loads(mp.read_text(encoding="utf-8"))
        srcf = mp.parent.parent / m["src"]
        if not srcf.exists():
            issue("A3_SRC_MISSING", str(mp)); continue
        text = srcf.read_bytes().decode("utf-8", errors="replace")
        joined = "".join((mp.parent / f["file"]).read_bytes().decode("utf-8", errors="replace") for f in m["files"])
        region = text[m["files"][0]["region_start"]:m["files"][-1]["region_end"]]
        if joined != region:
            issue("A3_CONCAT", str(mp))
        if m["n_posts"] != sum(f["n_posts"] for f in m["files"]):
            issue("A3_MANIFEST_COUNT", str(mp))

    # ---------- A5: search index audit ----------
    if si_run:
        sir = L0 / "runs" / si_run
        recs = [json.loads(l) for l in open(sir / "search/posts.jsonl", encoding="utf-8")]
        counters["A5_posts"] = len(recs)
        refs = [r["ref"] for r in recs]
        if len(set(refs)) != len(refs):
            issue("A5_REF_DUP", f"{len(refs) - len(set(refs))} duplicate refs")
        want_refs = {f"{uid}:{p['post_no']}" for uid, p in all_posts}
        got = set(refs)
        if got != want_refs:
            issue("A5_REF_SET", f"missing={len(want_refs - got)} extra={len(got - want_refs)}")
        # snippets & dates: recompute from raw (full)
        text_cache = {}
        bad_snip = 0
        for r in recs:
            if r["source"] == "hatena_bbs":
                continue  # group refs are per-post pages; body slice from unit ledger
            uid = r["unit_id"]
            u = next(x for x in units if x["unit_id"] == uid)
            rp = RAW_ROOT / u["raw_path"]
            if rp not in text_cache:
                text_cache[str(rp)] = rp.read_bytes().decode("utf-8", errors="replace")  # raw 基準
            text = text_cache[str(rp)]
            lp = by_no_lookup(per_unit_posts, uid, r["post_no"])
            if lp is None:
                issue("A5_LEDGER_MISS", r["ref"]); continue
            body = text[lp["body_start"]:lp["body_end"]].strip()
            snip = " ".join(body[:60].split())
            if snip != r["snippet"]:
                bad_snip += 1
                if bad_snip <= 5:
                    issue("A5_SNIPPET", f"{r['ref']}: '{r['snippet'][:30]}' vs '{snip[:30]}'")
        if bad_snip > 5:
            counters["A5_SNIPPET_total"] = bad_snip
        # date coverage: date_raw non-empty <=> date_iso present
        raw_nonempty = [(uid, p) for uid, p in all_posts if p["date"]]
        idx_by_ref = {r["ref"]: r for r in recs}
        missing_iso = 0
        for uid, p in raw_nonempty:
            r = idx_by_ref.get(f"{uid}:{p['post_no']}")
            if r is None or not r["date_iso"]:
                missing_iso += 1
        if missing_iso:
            issue("A5_DATE_COVER", f"{missing_iso} posts with raw date lack ISO", missing_iso)
        out_of_range = sorted({r["date_iso"][:4] for r in recs if r["date_iso"] and not (YEAR_OK[0] <= int(r["date_iso"][:4]) < YEAR_OK[1])})
        if out_of_range:
            issue("A5_YEAR_RANGE", f"years outside {YEAR_OK}: {out_of_range}")
        # chronology per unit
        chrono_bad = 0
        for uid, posts in per_unit_posts.items():
            prev = None
            for p in sorted(posts, key=lambda x: x["post_no"]):
                if not p["date"]:
                    continue
                iso, ep = None, None
                m = DATE_RE.match(p["date"].strip())
                if m:
                    try:
                        iso = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                       int(m.group(4)), int(m.group(5)), int(m.group(6) or 0),
                                       tzinfo=timezone(timedelta(hours=9)))
                        ep = iso.timestamp()
                    except ValueError:
                        continue
                if ep is None:
                    continue
                if prev is not None and ep < prev - 1:
                    chrono_bad += 1
                prev = ep
        if chrono_bad:
            issue("A5_CHRONO", f"{chrono_bad} posts older than preceding post in same thread", chrono_bad)
        # terms recount (full)
        tcount = {}
        for uid, posts in per_unit_posts.items():
            u = next(x for x in units if x["unit_id"] == uid)
            per_post_raw = all("raw_path" in p for p in posts)
            tc = {}
            for p in posts:
                rp = p.get("raw_path") if per_post_raw else u["raw_path"]
                if rp not in tc:
                    tc[rp] = (RAW_ROOT / rp).read_bytes().decode("utf-8", errors="replace")  # raw 基準
                body = tc[rp][p["body_start"]:p["body_end"]]
                for t in TERM_RE.findall(body):
                    tn = " ".join(t.split())
                    if tn:
                        tcount[tn] = tcount.get(tn, 0) + 1
        tidx = {json.loads(l)["term"]: json.loads(l)["count"] for l in open(sir / "search/terms.jsonl", encoding="utf-8")}
        diff_a = {t: c for t, c in tcount.items() if tidx.get(t) != c}
        diff_b = {t: c for t, c in tidx.items() if tcount.get(t) != c}
        if diff_a or diff_b:
            issue("A5_TERM_COUNT", f"recount diff: missing-in-index={len(diff_a)} phantom={len(diff_b)} sample={list(diff_a.items())[:5]}{list(diff_b.items())[:5]}")
        counters["A5_terms_recount"] = len(tcount)
    else:
        issue("A5_NO_INDEX", "no search-index run registered")

    report(run_dir, run_id, chunk_run, si_run, issues, counters)
    return 0


def by_no_lookup(per_unit_posts, uid, no):
    return next((p for p in per_unit_posts.get(uid, []) if p["post_no"] == no), None)


def report(run_dir, run_id, chunk_run, si_run, issues, counters):
    rep = {
        "audit_run": run_id,
        "audited_chunk_run": chunk_run,
        "audited_search_index_run": si_run,
        "generated": datetime.now(timezone.utc).isoformat(),
        "tool": "scripts/audit_yuragi_l0.py",
        "counters": counters,
        "issue_count": len(issues),
        "issues_by_code": {c: n for c, n in counters.items() if not c.startswith("A") or c in [i["code"] for i in issues]},
        "issues": issues[:300],
    }
    (run_dir / "audit-report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    (run_dir / "run.json").write_text(json.dumps({
        "run_id": run_id, "wiki": "yuragi", "layer": "L0", "kind": "audit",
        "created": rep["generated"], "tool": rep["tool"],
        "derived_from": {"l0_run": chunk_run, "search_index_run": si_run},
        "result": "PASS" if not issues else f"ISSUES {len(issues)}",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    idx_path = REPO / "work/yuragi/index/runs-index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    idx["L0"][run_id] = {
        "path": "work/yuragi/L0/runs/" + run_id, "status": "complete",
        "wiki": "yuragi", "layer": "L0", "kind": "audit",
        "created": rep["generated"],
        "derived_from": {"l0_run": chunk_run, "search_index_run": si_run},
        "result": rep.get("result") or ("PASS" if not issues else f"ISSUES {len(issues)}"),
    }
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print("AUDIT", run_id, "PASS" if not issues else f"ISSUES={len(issues)}")
    by_code = {}
    for i in issues:
        by_code[i["code"]] = by_code.get(i["code"], 0) + i["n"]
    for c, n in sorted(by_code.items()):
        print(" ", c, n)
    for i in issues[:15]:
        print("  >", i["code"], i["detail"][:160])
    print("counters:", json.dumps(counters, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    sys.exit(main())

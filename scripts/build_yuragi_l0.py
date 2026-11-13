#!/usr/bin/env python3
"""Yuragi L0 台帳生成器 v3（raw 5 層設計のリセット後）。

raw 5 層（YuragiWiki repo・正）:
  ① Thread.md / *_topic_comment.md   スレッド形式（無改変）
  ② posts/pXXXX.md                   各投稿チャンク（記事参照用・manifest 検証済み）
  ③ structured.jsonl                 各投稿構造化（全文・LLM 用）
  ④ chains.jsonl                     同一作者＋同一話題の一まとめ
  ⑤ thread.json                      スレッド全体の一まとめ

本層（work L0 台帳）= ①〜⑤ を結ぶアンカー台帳:
  units.jsonl            185 篇メタ（① sha1・② dir・③④⑤ sha1・層参照）
  units/<unit>.jsonl     投稿台帳（ref・② ファイル内 body 座標 raw 基準・chain_id）
  chunks/<unit>.jsonl    ④ の台帳ビュー（LLM 窓 = 24,000 字超群のみ post 境界分割）
  stats.json / run.json / latest.txt / index/runs-index.json

座標規約（恒久）: すべて対象ファイルの raw バイト列（改行変換なし）上の char 座標。
読み = read_bytes().decode('utf-8', errors='replace')。生成時ゲート: ② slice == ③ body 全件。
"""
import json
import re
import sys
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
JBBS = RAW / "jbbs" / "movie-7039"
MIXI = RAW / "mixi" / "373088"
HATENA_MD = RAW / "hatena_flicker" / "md"
L0 = W / "work" / "yuragi" / "L0"
RUNS = L0 / "runs"
BUDGET = 24000
JST = timezone(timedelta(hours=9))

sys.path.insert(0, r"C:/Users/d5dx/Downloads/Code/YuragiWiki/tools")
import split_posts as sp

DATE_RE = re.compile(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日)]?.*?(\d{1,2}):(\d{2})(?::(\d{2}))?$")

def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def iso_date(raw: str):
    if not raw:
        return None, None
    m = DATE_RE.match(raw.strip())
    if not m:
        return None, None
    try:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      int(m.group(4)), int(m.group(5)), int(m.group(6) or 0), tzinfo=JST)
    except ValueError:
        return None, None
    return dt.isoformat(), dt.timestamp()

def jl(p: Path):
    return [json.loads(l) for l in rd(p).splitlines() if l.strip()]

def make_windows(chain):
    """④ 群 → LLM 窓（budget 超のみ post 境界分割）。"""
    per = chain["per_chars"]
    nos = chain["post_nos"]
    windows = []
    cur, chars = [], 0
    def flush():
        if cur:
            windows.append(cur[:])
    for n in nos:
        c = per.get(n, 0)
        if cur and chars + c > BUDGET:
            flush()
            cur = []
            chars = 0
        cur.append(n)
        chars += c
    flush()
    if len(windows) <= 1:
        return [(nos, 1, 1)]
    return [(w, i + 1, len(windows)) for i, w in enumerate(windows)]

def build_unit(job, rid):
    unit_id = job["unit_id"]
    d = job["dir"]
    src = job["src"]
    struct = jl(d / "structured.jsonl")
    chains = jl(d / "chains.jsonl")
    layers = json.loads(rd(d / "_layers_manifest.json"))
    sb = {r["post_no"]: r["body"] for r in struct}
    chain_of = {n: c["chain_id"] for c in chains for n in c["post_nos"]}
    per_chars = {r["post_no"]: len(r["body"]) for r in struct}

    if job["source"] == "hatena":
        # ② = ページそのもの（1 ページ 1 投稿）
        posts = [{"post_no": r["post_no"], "author": r["author"], "date": r["date_raw"]}
                 for r in struct]
        page_files = {r["post_no"]: job["pages"][r["post_no"]] for r in struct}
        ledger, gate = [], 0
        for p in posts:
            n = p["post_no"]
            pf = page_files[n]
            ft = rd(pf)
            body = sb[n]
            lines = ft.splitlines(keepends=True)
            offs, acc = [], 0
            for ln in lines:
                offs.append(acc)
                acc += len(ln)
            hi = ni = None
            for i, ln in enumerate(lines):
                if hi is None and re.match(r"^##\s+\[\d+\]\(", ln):
                    hi = i
                if "mode=reply" in ln and "｜" in ln:
                    ni = i
            s5 = offs[hi + 1]
            e3 = offs[ni]
            region = ft[s5:e3]
            lead = len(region) - len(region.lstrip())
            bs = s5 + lead
            be = bs + len(body)
            assert ft[bs:be] == body, f"{unit_id}:{n} ② slice != ③ body"
            iso, ep = iso_date(p["date"])
            rel = str(pf.relative_to(RAW)).replace("\\", "/")
            ledger.append({"ref": f"{unit_id}:{n}", "post_no": n, "author": p["author"],
                           "date": p["date"], "date_iso": iso,
                           "epoch": None if ep is None else round(ep, 3),
                           "file": pf.name, "raw_group_path": rel,
                           "body_start": bs, "body_end": be, "chars": len(body),
                           "chain_id": chain_of[n]})
            gate += 1
        raw_group_sha1 = {f"{unit_id}:{r['post_no']}": sha1_bytes(job["pages"][r["post_no"]].read_bytes())
                          for r in struct}
    else:
        mf = json.loads(rd(d / "posts" / "_manifest.json"))
        text1 = rd(src)
        posts, _ = sp.regions(text1)
        f_of, meta_of = {}, {}
        for f in mf["files"]:
            a, b = f["post_range"]
            meta_of[f["file"]] = f
            for n in range(a, b + 1):
                f_of[n] = f["file"]
        texts2 = {}
        ledger = []
        for p in posts:
            n = p["post_no"]
            fname = f_of[n]
            f2 = d / "posts" / fname
            if str(f2) not in texts2:
                texts2[str(f2)] = rd(f2)
            t2 = texts2[str(f2)]
            off = p["region_start"] - meta_of[fname]["region_start"]
            idx = t2.find("\n", off)
            after = t2[idx + 1:p["region_end"] - meta_of[fname]["region_start"]]
            lead = len(after) - len(after.lstrip())
            body = sb[n]
            bs = idx + 1 + lead
            be = bs + len(body)
            assert t2[bs:be] == body, f"{unit_id}:{n} ② slice != ③ body"
            iso, ep = iso_date(p["date"])
            ledger.append({"ref": f"{unit_id}:{n}", "post_no": n, "author": p["author"],
                           "date": p["date"], "date_iso": iso,
                           "epoch": None if ep is None else round(ep, 3),
                           "file": fname,
                           "raw_group_path": str((d / "posts" / fname).relative_to(RAW)).replace("\\", "/"),
                           "body_start": bs, "body_end": be, "chars": len(body),
                           "chain_id": chain_of[n]})
        raw_group_sha1 = {f["file"]: f["sha1"] for f in mf["files"]}

    # chunks（④ 台帳ビュー＋ LLM 窓）
    chunks = []
    seq = 0
    for c in chains:
        c = dict(c)
        c["per_chars"] = per_chars
        wins = make_windows(c)
        for nos, part, total in wins:
            seq += 1
            a, b = min(nos), max(nos)
            chars = sum(per_chars[n] for n in nos)
            noset = set(nos)
            fset = sorted({l["raw_group_path"] for l in ledger if l["post_no"] in noset})
            chunks.append({
                "chunk_id": f"{unit_id}#c{seq:03d}", "group_id": c["chain_id"],
                "kind": c["kind"], "author": c["author"], "topics": c["topics"],
                "post_range": [a, b], "n_posts": len(nos), "chars": chars,
                "part": part, "parts_total": total,
                "raw_group_path": fset[0] if len(fset) == 1 else fset,
            })
    unit_meta = {
        "unit_id": unit_id, "source": job["source"], "title": job["title"], "url": job["url"],
        "raw_path": None if job["source"] == "hatena" else str(src.relative_to(RAW)).replace("\\", "/"),
        "raw_sha1": None if job["source"] == "hatena" else sha1_bytes(src.read_bytes()),
        "n_posts": len(posts), "n_chains": len(chains),
        "layers_sha1": layers["layers"]["sha1"],
        "first_date": ledger[0]["date_iso"] if ledger else None,
        "last_date": ledger[-1]["date_iso"] if ledger else None,
    }
    return unit_meta, ledger, chunks, raw_group_sha1

def main():
    rid = datetime.now().strftime("%Y%m%dT%H%M") + "_l0c"
    run = RUNS / rid
    (run / "units").mkdir(parents=True, exist_ok=True)
    (run / "chunks").mkdir(parents=True, exist_ok=True)
    jobs = []
    for d in sorted(p for p in JBBS.iterdir() if p.is_dir()):
        m = re.match(r"(\d{3})_", d.name)
        jobs.append({"unit_id": f"YJ-T{m.group(1)}", "source": "jbbs",
                     "title": d.name.split("_", 1)[1],
                     "url": f"https://jbbs.shitaraba.net/bbs/read.cgi/movie/7039/{int(m.group(1))}/",
                     "dir": d, "src": d / "Thread.md"})
    for tdir in sorted(p for p in MIXI.iterdir() if p.is_dir()):
        cf = sorted(tdir.glob("*_topic_comment.md"))
        tid = cf[0].name.split("_", 1)[0]
        jobs.append({"unit_id": f"YJ-M{tid}", "source": "mixi", "title": tdir.name,
                     "url": f"https://mixi.jp/view_bbs.pl?comm_id=373088&id={tid}",
                     "dir": tdir, "src": cf[0]})
    pages = {}
    for f in HATENA_MD.rglob("*bbs_1_*.md"):
        m = re.search(r"bbs_1_(\d+)_(\d{14})\.md$", f.name)
        if not m:
            continue
        pages.setdefault(int(m.group(1)), []).append((m.group(2), f))
    jobs.append({"unit_id": "YJ-H01", "source": "hatena", "title": "ふりかーBBS（portal）",
                 "url": "https://flicker.g.hatena.ne.jp/bbs/1/1",
                 "dir": RAW / "hatena_flicker", "src": None,
                 "pages": {int(k): sorted(v)[-1][1] for k, v in pages.items()}})

    units_out, all_chunks = [], []
    stats = {"units": 0, "posts": 0, "chains": 0, "chunks": 0, "windows_split": 0,
             "chars_body": 0, "authors": set()}
    for j in jobs:
        meta, ledger, chunks, rg_sha1 = build_unit(j, rid)
        (run / "units" / f"{j['unit_id']}.jsonl").write_text(
            "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in ledger),
            encoding="utf-8", newline="\n")
        (run / "chunks" / f"{j['unit_id']}.jsonl").write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks),
            encoding="utf-8", newline="\n")
        units_out.append(meta)
        all_chunks.extend(chunks)
        stats["units"] += 1
        stats["posts"] += meta["n_posts"]
        stats["chains"] += meta["n_chains"]
        stats["chunks"] += len(chunks)
        stats["windows_split"] += sum(1 for c in chunks if c["parts_total"] > 1)
        stats["chars_body"] += sum(l["chars"] for l in ledger)
        stats["authors"].update(l["author"] for l in ledger)
    (run / "units.jsonl").write_text(
        "".join(json.dumps(u, ensure_ascii=False) + "\n" for u in units_out),
        encoding="utf-8", newline="\n")
    stats["authors"] = len(stats["authors"])
    (run / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    ysha = __import__("subprocess").run(["git", "-C", str(RAW.parent.parent), "rev-parse", "HEAD"],
                                         capture_output=True, text=True).stdout.strip()
    (run / "run.json").write_text(json.dumps({
        "run_id": rid, "kind": "l0-ledger-v3",
        "derived_from": {"yuragi_commit": ysha, "raw_layers": ["①", "②", "③", "④", "⑤"]},
        "created": datetime.now(JST).isoformat(),
        "stats_file": "stats.json",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (L0 / "latest.txt").write_text(rid, encoding="utf-8")
    # runs-index
    idx_p = W / "work" / "yuragi" / "index" / "runs-index.json"
    idx_p.parent.mkdir(parents=True, exist_ok=True)
    idx = json.loads(idx_p.read_text(encoding="utf-8")) if idx_p.exists() else {"L0": {}}
    idx["L0"][rid] = {"status": "current", "kind": "l0-ledger-v3",
                      "path": "work/yuragi/L0/runs/" + rid}
    idx_p.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Yuragi raw 層 → LLM 投入ペイロード読み取り（スレッド情報を 1 回だけ付与）。

③ structured.jsonl は 1 行目 = 篇メタ（thread_title/url/source）、投稿行は ref/post_no/author/日付/body のみ。
④ chains.jsonl は chain_id 先頭 = unit_id（重複なし）。このリーダが篇メタを補って LLM 用ペイロードに組む。

使い方:
  python scripts/read_yuragi.py units                         # 篇メタ一覧（JSONL）
  python scripts/read_yuragi.py unit  YJ-T031 [--text]        # 篇全体（--text = LLM ペイロード）
  python scripts/read_yuragi.py chains YJ-T031                # ④ 索引（chain_id/author/n_posts/topics/summary）
  python scripts/read_yuragi.py chain  YJ-T031#g012 [--text]  # 1 群（--text = 篇ヘッダ＋本文全文）
  python scripts/read_yuragi.py posts  YJ-T031 1245-1249 [--text]
  共通: --max N 本文 1 件あたり N 字に切つ（0=無制限・既定 0）
JSON 出力は LLM プログラム連携用、--text はそのまま prompt 本文に置ける整形テキスト。
"""
import json
import sys
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def jl(p: Path, with_meta: bool = False):
    out = []
    for l in rd(p).splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if isinstance(r, dict) and r.get("_meta"):
            if with_meta:
                out.append(r)
            continue
        out.append(r)
    return out

def unit_index():
    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    units = {}
    for u in jl(L0 / "runs" / latest / "units.jsonl"):
        uid = u["unit_id"]
        if u["source"] == "jbbs":
            d = RAW / u["raw_path"].rsplit("/", 1)[0]
        elif u["source"] == "mixi":
            d = RAW / "mixi/373088" / u["title"]
        else:
            d = RAW / "hatena_flicker"
        units[uid] = {"dir": d, "source": u["source"], "title": u["title"], "url": u["url"]}
    return units

def load_unit(units, uid):
    m = units[uid]
    meta = jl(m["dir"] / "structured.jsonl", with_meta=True)[0]
    posts = jl(m["dir"] / "structured.jsonl")
    return m, meta, posts

def cut(body: str, mx: int) -> str:
    return body[:mx] + ("…" if len(body) > mx else "") if mx else body

def emit_unit_text(meta, posts, mx):
    print(f"# スレッド: {meta['thread_title']}")
    print(f"# source={meta['source']} url={meta['url']} n_posts={meta['n_posts']}")
    for p in posts:
        print(f"\n[{p['post_no']}] {p['author']} {p.get('date_iso') or '（日付なし）'}")
        print(cut(p["body"], mx))

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0
    cmd = args[0]
    mx = 0
    if "--max" in args:
        mx = int(args[args.index("--max") + 1])
    text = "--text" in args
    units = unit_index()

    if cmd == "units":
        for uid in sorted(units):
            m = jl(units[uid]["dir"] / "structured.jsonl", with_meta=True)[0]
            print(json.dumps(m, ensure_ascii=False))
    elif cmd == "unit" and len(args) >= 2:
        m, meta, posts = load_unit(units, args[1])
        if text:
            emit_unit_text(meta, posts, mx)
        else:
            print(json.dumps({"meta": meta, "posts":
                              [{k: (cut(v, mx) if k == "body" else v) for k, v in p.items()}
                               for p in posts]}, ensure_ascii=False))
    elif cmd == "chains" and len(args) >= 2:
        for c in jl(units[args[1]]["dir"] / "chains.jsonl"):
            print(json.dumps({k: c.get(k) for k in
                              ("chain_id", "kind", "author", "post_range", "n_posts",
                               "topics", "chars", "summary")}, ensure_ascii=False))
    elif cmd == "chain" and len(args) >= 2:
        cid = args[1]
        uid = cid.split("#", 1)[0]
        m, meta, posts = load_unit(units, uid)
        by_no = {p["post_no"]: p for p in posts}
        chain = [c for c in jl(m["dir"] / "chains.jsonl") if c["chain_id"] == cid]
        if not chain:
            raise SystemExit(f"chain 見つからず: {cid}")
        chain = chain[0]
        rows = [by_no[n] for n in chain["post_nos"]]
        if text:
            print(f"# スレッド: {meta['thread_title']} (source={meta['source']} url={meta['url']})")
            print(f"# chain {cid} author={chain['author']} topics={','.join(chain['topics'])} "
                  f"posts={chain['post_range'][0]}-{chain['post_range'][1]} ({chain['n_posts']} 件)")
            print(f"# 要約: {chain.get('summary', '')}")
            for p in rows:
                print(f"\n[{p['post_no']}] {p['author']} {p.get('date_iso') or '（日付なし）'}")
                print(cut(p["body"], mx))
        else:
            print(json.dumps({"meta": meta, "chain": chain, "posts": rows}, ensure_ascii=False))
    elif cmd == "posts" and len(args) >= 3:
        uid, rng = args[1], args[2]
        a, b = (rng.split("-") + [rng])[:2]
        a, b = int(a), int(b)
        m, meta, posts = load_unit(units, uid)
        rows = [p for p in posts if a <= p["post_no"] <= b]
        if text:
            print(f"# スレッド: {meta['thread_title']} (url={meta['url']})")
            for p in rows:
                print(f"\n[{p['post_no']}] {p['author']} {p.get('date_iso') or '（日付なし）'}")
                print(cut(p["body"], mx))
        else:
            for p in rows:
                print(json.dumps(p, ensure_ascii=False))
    else:
        raise SystemExit("usage: units | unit ID | chains ID | chain ID#NNN | posts ID a-b  [--text] [--max N]")
    return 0

if __name__ == "__main__":
    sys.exit(main())

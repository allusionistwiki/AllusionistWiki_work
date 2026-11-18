#!/usr/bin/env python3
"""Yuragi 創作記述抽出 — 全群（chains.jsonl）を LLM で分類し works.jsonl 台帳を作る。

サイト意義（ユーザー指示）: 各所に散らばった創作的記述のインデックス化・追跡可能な公開。
入力: 篇ごとの chains.jsonl（chain_id/post_nos/author/topics/summary）＋ 先頭投稿本文（詩等の特徴判別）。
出力: work/yuragi/L1/works.jsonl  1 行 1 群:
  {chain_id, uid, post_range, author, creative, type, work, hint, n_posts}
判定基準: 創作者自身が書いた content（詩/短編/脚本/歌詞/設定文/劇中作品文/販促文/韻文/日记体 等）を creative=true、
          転載・既存作引用・雑談・質問・実況は false。
使い方: python scripts/classify_yuragi_works.py [--workers 3] [--batch 8] [--out works.jsonl]
      （checkpoint: 同名 .progress.jsonl、resume 自動）
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
L1 = W / "work" / "yuragi" / "L1"

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def jl(p: Path):
    out = []
    for l in rd(p).splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if isinstance(r, dict) and r.get("_meta"):
            continue
        out.append(r)
    return out

def load_llm_config():
    cfg = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistLLMWiki2/config.yaml").read_text(encoding="utf-8")
    sec = cfg.split("llm:", 1)[1]
    def grab(key):
        m = re.search(rf'^\s*{key}:\s*"?([^"#\n]+?)"?\s*(#.*)?$', sec, re.M)
        return m.group(1).strip() if m else None
    return {"base_url": grab("base_url").rstrip("/"), "api_key": grab("api_key"), "model": grab("model")}

CFG = load_llm_config()

def call_llm(prompt: str, max_tokens: int = 1500) -> str:
    body = json.dumps({
        "model": CFG["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1, "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                CFG["base_url"] + "/chat/completions", data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {CFG['api_key']}"})
            resp = json.loads(urllib.request.urlopen(req, timeout=600).read().decode("utf-8"))
            ch = resp["choices"][0]
            txt = (ch.get("message") or {}).get("content") or ch.get("content") or ""
            if txt.strip():
                return txt.strip()
        except Exception:
            pass
        time.sleep(2 + 3 * attempt)
    return ""

TYPES = "詩/短編・小説/脚本/歌詞/設定文/劇中作品文(TCGカード・劇中ゲーム・劇中書物等の文面)/販促文・宣伝文/韻文・格言・謎かけ/その他創作/非創作"

import threading
w_lock = threading.Lock()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--out", default=str(L1 / "works.jsonl"))
    a = ap.parse_args()
    out_f = Path(a.out)
    prog_f = out_f.with_suffix(".progress.jsonl")
    done = set()
    if prog_f.exists():
        for r in jl(prog_f):
            done.add(r["chain_id"])

    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    chains_all = []
    seen = set()
    for d in sorted(RAW.glob("**/chains.jsonl")):
        uid = None
        for l in (d.parent / "structured.jsonl").read_bytes().decode("utf-8", "replace").splitlines():
            if l.strip():
                r0 = json.loads(l)
                if isinstance(r0, dict) and r0.get("_meta"):
                    uid = r0.get("unit_id")
                    break
        if not uid:
            continue
        bodies = {p["post_no"]: p for p in jl(d.parent / "structured.jsonl")}
        for c in jl(d):
            cid = c["chain_id"]
            if cid in seen:
                continue
            seen.add(cid)
            chains_all.append((uid, c, bodies))
    todo = [t for t in chains_all if t[1]["chain_id"] not in done]
    batches = [todo[i:i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"chains={len(chains_all)} todo={len(todo)} batches={len(batches)}", flush=True)

    lock_f = prog_f.open("ab")

    def work(batch):
        lines = []
        for uid, c, bodies in batch:
            nos = c.get("post_nos") or list(range(c["post_range"][0], c["post_range"][1] + 1))
            first = ""
            for n in nos[:2]:
                if n in bodies:
                    first += bodies[n]["body"][:180] + " / "
            t = "、".join(c.get("topics", [])) or "—"
            lines.append(f"[{c['chain_id']}] 作者:{c.get('author','')} 話題:{t} 要約:{c.get('summary','')} 冒頭:{first[:260]}")
        prompt = (
            "以下は『ゆらぎの神話』BBS 実況コーパスの連続投稿群です。各群が**創作的記述**"
            "（投稿者自身が執筆した詩・短編・脚本・歌詞・設定文・劇中作品の文面・販促文・韻文・日记体創作など）かを判定してください。"
            "既存作品の転載・引用、実況・雑談・質問・技術話・日常話は非創作です。\n"
            f"type は次から 1 つ: {TYPES}\n"
            "work は創作と判定した場合のみ、その作品名（原文に現れる表記をそのまま・30 字以内、無ければ「無題」）。\n"
            "各行について 1 行の JSON を出力: "
            '{"id":"chain_id","creative":true/false,"type":"...","work":"...","hint":"创作内容の一言ヒント（非創作は空）"}\n'
            "JSON 以外（前置き・コードフェンス）は出さない。\n\n" + "\n".join(lines)
        )
        text = call_llm(prompt)
        got = {}
        for m in re.finditer(r"\{[^{}]*\}", text):
            try:
                j = json.loads(m.group(0))
                got[j.get("id")] = j
            except Exception:
                pass
        rows = []
        for uid, c, bodies in batch:
            cid = c["chain_id"]
            g = got.get(cid, {})
            rows.append({"chain_id": cid, "uid": uid, "post_range": c["post_range"],
                         "author": c.get("author", ""), "n_posts": len(nos := (c.get("post_nos") or range(c["post_range"][0], c["post_range"][1] + 1))),
                         "creative": bool(g.get("creative", False)), "type": g.get("type", "未分類"),
                         "work": g.get("work", ""), "hint": g.get("hint", ""), "judged": bool(g)})
        with w_lock:
            for r in rows:
                lock_f.write((json.dumps(r, ensure_ascii=False) + "\n").encode())
            lock_f.flush()
        return len(rows)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        n = sum(ex.map(work, batches))
    lock_f.close()
    # 台帳整形（非重複）
    rows, seen2 = [], set()
    for r in jl(prog_f):
        if r["chain_id"] in seen2:
            continue
        seen2.add(r["chain_id"])
        rows.append(r)
    out_f.write_bytes("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8"))
    cre = sum(1 for r in rows if r.get("creative"))
    print(json.dumps({"chains": len(rows), "creative": cre, "non": len(rows) - cre,
                      "unjudged": sum(1 for r in rows if not r.get("judged"))}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())

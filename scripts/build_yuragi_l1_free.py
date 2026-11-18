#!/usr/bin/env python3
"""Yuragi L1 制約なし版記事（free 層）— L1 篇記事＋原文群情報をもとに自由記述で書く。

ユーザー意図: 「L1 と原文をもとに、L1 の構造制約なしで記事を自由記述する」。
入力: L1 監査済み篇記事（2115_l1u）＋ 篇の群索引（chains.jsonl 群要約・話題・作者）
      ＋ 短文篇（投稿 <= 150）は原文全文。
出力: work/yuragi/L1/runs/<rid>_l1free/units/<uid>.md（frontmatter unit/title）。
制約: 引用長・見出し・字数の制限なし。ただし引用は原文から逐語、内容は入力情報のみ、
      本文中に投稿参照（uid:N 形式）を含むこと。
監査: audit_yuragi_l1.py --scope free（機械ゲート: 引用逐語性・heads 検査なし＋LLM 全量）。
使い方: python scripts/build_yuragi_l1_free.py [--workers 4] [--run-dir RID] [--only uid ...]
"""
import argparse
import datetime as dt
import hashlib
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
UNIT_RUN = "20261117T2115_l1u"

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

def call_llm(prompt: str, max_tokens: int = 4000) -> str:
    body = json.dumps({
        "model": CFG["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4, "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False},
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    rid = a.run_dir or (dt.datetime.now().strftime("%Y%m%dT%H%M") + "_l1free")
    out = L1 / "runs" / rid
    (out / "units").mkdir(parents=True, exist_ok=True)
    done_f = out / "done.txt"
    done = set(done_f.read_bytes().decode("utf-8").split()) if done_f.exists() else set()
    only = set(a.only) if a.only else None

    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    dirs = {}
    for u in jl(L0 / "runs" / latest / "units.jsonl"):
        uid = u["unit_id"]
        if uid in dirs:
            continue
        d = (RAW / u["raw_path"].rsplit("/", 1)[0] if u["source"] == "jbbs"
             else RAW / "mixi/373088" / u["title"] if u["source"] == "mixi"
             else RAW / "hatena_flicker")
        dirs[uid] = (u, d)

    jobs = [uid for uid in dirs if uid not in done and (only is None or uid in only)]

    def work(uid):
        u, d = dirs[uid]
        art = L1 / "runs" / UNIT_RUN / "units" / f"{uid}.md"
        if not art.exists():
            return uid, None
        art_txt = art.read_bytes().decode("utf-8", "replace")
        mm = re.match(r"^---\r?\n.*?\r?\n---\r?\n", art_txt, re.S)
        art_body = art_txt[mm.end():] if mm else art_txt
        posts = jl(d / "structured.jsonl")
        chains = jl(d / "chains.jsonl")
        chain_txt = []
        for c in chains:
            t = "、".join(c.get("topics", [])) or "—"
            chain_txt.append(f"[{c['post_range'][0]}-{c['post_range'][1]}] 話題:{t} 要約: {c.get('summary','')}")
        input_parts = [f"=== 篇: {u['title']}（{uid}・{len(posts)} 投稿・URL {u['url']}） ===",
                       "=== L1 篇記事（監査済み・参考） ===", art_body,
                       "=== 群索引（原文の話題展開と要約） ===", "\n".join(chain_txt)]
        if len(posts) <= 150:
            input_parts.append("=== 原文全文 ===")
            input_parts.append("\n".join(f"[{p['post_no']}] {p['author']} {p.get('date_iso') or ''}\n{p['body']}"
                                          for p in posts))
        prompt = (
            "あなたはゆらぎの神話 BBS 実況コーパスの wiki 編集者です。\n"
            "下の入力情報だけをもとに、この篇（スレッド群）の wiki 記事を**制約なしの自由記述**で書いてください。\n"
            "【構成】見出し構成は自由、長さの制限なし（内容は濃いほど良い）。原文引用の長さに制限はありません。\n"
            "【引用の鉄則】\n"
            "・「」の中は**原文投稿の本文からの逐語コピーのみ**（連続部分文字列。改変・省略・語順変更・複数投稿の結合・文中での切断は禁止。文末/改行で切る）。\n"
            "・群索引の要約文は引用してはいけない（参考情報であり原文ではない）。\n"
            "・名前・用語・概念を強調するだけの「」は使わない（そういう用途には『』か plain テキスト）。\n"
            "・逐語で引用できない内容は「」を使わずに自分の文で要約して書く。\n"
            "【出典参照】具体的な投稿にもとづく記述には、必ず「" + uid + ":N」の形で投稿番号を明記する（N は投稿番号。\n"
            "群索引の [開始-終了] 範囲から、代表となる投稿番号を選んで付けること。記事全体で 10 件以上の参照を目安に）。\n"
            "【忠実性】入力にない事実（推測・外部知識）は書かない。\n"
            "【出力】Markdown 本文のみ（コードフェンスで囲まない）。先頭は `# " + u['title'] + "`。\n\n"
            + "\n\n".join(input_parts)
        )
        text = call_llm(prompt)
        if not text.strip() or len(text) < 300:
            return uid, None
        fm = f"---\nunit: {uid}\ntitle: \"{u['title']}\"\nversion: free（制約なし自由記述）\nsource_run: {UNIT_RUN}\nrun: {rid}\n---\n\n"
        (out / "units" / f"{uid}.md").write_bytes((fm + text.strip() + "\n").encode("utf-8"))
        with done_f.open("ab") as f:
            f.write((uid + "\n").encode())
        return uid, len(text)

    emitted = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for uid, size in ex.map(work, jobs):
            if size:
                emitted += 1
            print(f"{uid}: {'OK' if size else 'FAIL'} {size or ''}", flush=True)
    (out / "run.json").write_text(json.dumps({
        "run_id": rid, "layer": "L1/free", "mode": "llm-free-composition",
        "derived_from": {"L0_ledger": latest, "L1_units": UNIT_RUN},
        "created": dt.datetime.now().isoformat(),
        "jobs": len(jobs), "emitted": emitted}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"rid": rid, "jobs": len(jobs), "emitted": emitted}, ensure_ascii=False))
    return 0 if emitted == len(jobs) else 1

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""④ chains 用 LLM 要約生成（Strata local・resumable・追記専用）。

入力: YuragiWiki raw 層 ④ chains.jsonl ＋ ③ structured.jsonl（chain 本文）
出力: work/yuragi/L0/runs/<rid>_l0sum/summaries.jsonl（1 群 1 行・追記専用）
  {chain_id, unit_id, chain_sha1, n_posts, author, model, created, summary}
削除群（author <<…>>）は要約固定「（削除投稿）」＝LLM 呼出なし。
バッチ: 入力 ~12,000 字まで群を詰め「番号: 1文要約」形式で出力、行数不一致は再試行。
中身検証: chain_sha1 で来歴固定（マージ時に再照合）。
使い方: python scripts/summarize_yuragi_chains.py [--limit N] [--workers 1]
"""
import json
import re
import sys
import time
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
JST = timezone(timedelta(hours=9))

def load_llm_config():
    """vault config.yaml の llm: 節を簡易パース（secret は実行時のみ参照・非表示）。"""
    cfg = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistLLMWiki2/config.yaml")
    txt = cfg.read_text(encoding="utf-8")
    sec = txt.split("llm:", 1)[1]
    def grab(key):
        m = re.search(rf'^\s*{key}:\s*"?([^"#\n]+?)"?\s*(#.*)?$', sec, re.M)
        return m.group(1).strip() if m else None
    return {"base_url": grab("base_url"), "api_key": grab("api_key"), "model": grab("model")}

LLMC = load_llm_config()
BASE_URL = LLMC["base_url"]
API_KEY = LLMC["api_key"]
MODEL = LLMC["model"]
BATCH_CHARS = 12000
TRUNC = 1200
BATCH_MAX = 30
MAX_TOKENS = 4000
RETRIES = 3

def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def jl(p: Path):
    out = []
    for l in rd(p).splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if isinstance(r, dict) and r.get("_meta"):
            continue  # ③ 篇メタ行は投稿行ではない
        out.append(r)
    return out

def all_chains():
    """Yuragi ④ chains.jsonl 全 185 篇ぶん＋③ 本文から chain 本文を作る。"""
    out = []
    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    units = {u["unit_id"]: u for u in jl(L0 / "runs" / latest / "units.jsonl")}
    for uid, u in units.items():
        if u["source"] == "jbbs":
            d = RAW / u["raw_path"].rsplit("/", 1)[0]
        elif u["source"] == "mixi":
            d = RAW / "mixi/373088" / u["title"]
        else:
            d = RAW / "hatena_flicker"
        sb = {r["post_no"]: r["body"] for r in jl(d / "structured.jsonl")}
        for c in jl(d / "chains.jsonl"):
            text = "\n\n".join(sb[n] for n in c["post_nos"])
            out.append({
                "chain_id": c["chain_id"], "unit_id": uid, "author": c["author"],
                "n_posts": c["n_posts"], "topics": c["topics"], "kind": c["kind"],
                "text": text, "sha1": sha1_bytes(text.encode("utf-8")),
            })
    return out

def make_prompt(batch):
    lines = ["以下の番号つきの BBS 投稿（群）.each の話題内容を、1 文（25〜60 字）で要約してください。",
             "形式は「番号: 要約」の行のみ。説明文・前置き・見出しは不要。",
             "要約には作者の意図（記述投稿/質問/実況/雑談/批判 等）と中心的な固有名詞を含める。", ""]
    for i, c in enumerate(batch):
        t = c["text"]
        if len(t) > TRUNC:
            t = t[:TRUNC] + "…（後略）"
        topic = "、".join(c["topics"][:3])
        lines.append(f"--- {i} （作者:{c['author']} 話題:{topic}）")
        lines.append(t)
    return "\n".join(lines)

def call_llm(client, prompt):
    resp = client.chat.completions.create(
        model=MODEL, temperature=1.0, max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}], stream=False)
    ch = resp.choices[0]
    if getattr(ch, "message", None) is not None and getattr(ch.message, "content", None):
        return ch.message.content
    if getattr(ch, "content", None):
        return ch.content
    return ch.text

def parse_lines(out, n):
    res = {}
    for ln in out.splitlines():
        m = re.match(r"^\s*(\d{1,3})\s*[:：]\s*(.+)$", ln.strip())
        if m and 0 <= int(m.group(1)) < n:
            res[int(m.group(1))] = m.group(2).strip()
    return res

def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    rid = datetime.now(JST).strftime("%Y%m%dT%H%M") + "_l0sum"
    run = L0 / "runs" / rid
    run.mkdir(parents=True, exist_ok=True)
    (run / "run.json").write_text(json.dumps({
        "run_id": rid, "kind": "l0-chain-summary", "model": MODEL, "base_url": BASE_URL,
        "created": datetime.now(JST).isoformat(), "prompt": "1 群 1 文要約（25-60 字）",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    outp = run / "summaries.jsonl"

    from openai import OpenAI
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=900)

    chains = all_chains()
    if "--only-file" in sys.argv:
        ids = {json.loads(l)["chain_id"] for l in
               rd(Path(sys.argv[sys.argv.index("--only-file") + 1])).splitlines() if l.strip()}
        chains = [c for c in chains if c["chain_id"] in ids]
    if limit:
        chains = chains[:limit]
    done_ids = {r["chain_id"] for r in jl(outp)} if outp.exists() else set()
    todo = [c for c in chains if c["chain_id"] not in done_ids]

    def emit(recs):
        with outp.open("a", encoding="utf-8", newline="\n") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    fixed = [c for c in todo if c["kind"] == "deleted"]
    emit([{"chain_id": c["chain_id"], "unit_id": c["unit_id"], "chain_sha1": c["sha1"],
           "n_posts": c["n_posts"], "author": c["author"], "model": "fixed",
           "created": datetime.now(JST).isoformat(), "summary": "（削除投稿）"} for c in fixed])
    todo = [c for c in todo if c["kind"] != "deleted"]

    batch, chars = [], 0
    n_done, n_fail = len(fixed), 0
    for c in todo:
        clen = min(len(c["text"]), TRUNC) + 60
        if batch and (chars + clen > BATCH_CHARS or len(batch) >= BATCH_MAX):
            n_done += run_batch(client, batch, outp, emit)
            n_fail += 0
            batch, chars = [], 0
        batch.append(c)
        chars += clen
    if batch:
        n_done += run_batch(client, batch, outp, emit)
    print(json.dumps({"rid": rid, "chains_total": len(chains), "emitted": n_done,
                      "out": str(outp)}, ensure_ascii=False))

def run_batch(client, batch, outp, emit):
    prompt = make_prompt(batch)
    for attempt in range(RETRIES):
        try:
            out = call_llm(client, prompt)
            res = parse_lines(out, len(batch))
            missing = [i for i in range(len(batch)) if i not in res]
            if not missing:
                ts = datetime.now(JST).isoformat()
                emit([{"chain_id": c["chain_id"], "unit_id": c["unit_id"], "chain_sha1": c["sha1"],
                       "n_posts": c["n_posts"], "author": c["author"], "model": MODEL,
                       "created": ts, "summary": res[i]} for i, c in enumerate(batch)])
                return len(batch)
            # 欠損行だけ再試行（部分一致は採用しない）
            batch = [batch[i] for i in missing]
            prompt = make_prompt(batch)
        except Exception as e:
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(5)
    with outp.open("a", encoding="utf-8", newline="\n") as f:
        pass
    return 0

if __name__ == "__main__":
    main()

"""S3 段: 裁定キューの LLM グループ裁定（Strata 直列・resume 対応・DONE 行ログ）。

Usage: python scripts/adjudicate_l2.py <run_id> [--max N]
Reads  work/allusionist_v2/L2/runs/<run_id>/adjudication-queue.jsonl
Writes work/allusionist_v2/L2/runs/<run_id>/adjudications.jsonl  (per group, resumable)
       work/allusionist_v2/L2/runs/<run_id>/review-queue.jsonl    (parse_failed/unknown 再投入)
       work/data/adjudicate_<run_id>.log
"""
import json
import sys
import time
import re
import datetime
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import L2_RUNS, ROOT

BASE_URL = "http://127.0.0.1:8080/v1"
API_KEY = "sk-l2l2l2l2"
MODEL = "swift-1.5-iq3_xxs"
TEMP = 1.0            # Qwen 公式推奨（skill 準拠）
MAX_TOKENS = 2400     # probe 実測: 2grp=613tok; 4grp≈1300tok + ゆとり
BATCH_CHARS = 4000    # payload JSON 字数の上限（probe: 2grp payload 7.4k→1grp 相当の大型は独立）
CALL_SLEEP = 1.2      # throttle（プロセス内）

INSTR = (
    "あなたは実体名統合の裁定者です。各グループは表記の相関で機械検出された名義群です。"
    "グループごとに各変種（norm）を裁定し、JSON のみで応答してください。"
    "verdict の意味: alias=同一実体（canonical を一つ選び aliases に含める。"
    "既存公開IDが members にあれば canonical はそのIDを優先採用）、"
    "separate=別実体（別人・別物）、related=関連語（X選・都市X 等の派生実体。統合せず対象Xとの関係として別実体）、"
    "unknown=証拠不足（要検証）。"
    "multi-kind グループ（同一名に複数 kind の公開ID）は canonical kind を1つ裁定し、残りの用法は related か notes 向け reason に記述。"
    "kind-tie グループは quote 証拠から canonical kind を裁定。"
    "confidence は 明言|蓋然性高|要検証 のいずれか。reason は30字以内の簡潔な根拠。"
    "出力形式: {\"results\":[{\"id\":\"<group id>\",\"decisions\":[{\"norm\":\"...\",\"verdict\":\"alias|separate|related|unknown\",\"canonical\":\"alias の時のみ代表 surface または公開ID\",\"kind\":\"character|terminology|item|organization|location|motif|phrase|event|creature|relationship\",\"confidence\":\"明言|蓋然性高|要検証\",\"reason\":\"...\"}]}]} "
    "groups を全件含めること。\n\ngroups=\n"
)


def compact_member(m):
    kv = dict(sorted(m["kind_votes"].items(), key=lambda kv: -kv[1])[:3])
    return {"norm": m["norm"][:30],
            "surfaces": [{"s": x["surface"][:30], "n": x["count"]} for x in m["surfaces"][:3]],
            "seeds": [{"id": s["id"], "kind": s["kind"]} for s in m["seed_ids"][:2]],
            "kind_votes": kv,
            "facts_total": m["count"],
            "quote": (m["quotes"][0]["q"] if m["quotes"] else "")[:60]}


def parse_json_lenient(text):
    t = text.strip()
    t = re.sub(r"^```[a-z]*\n?|```$", "", t.strip())
    try:
        return json.loads(t)
    except Exception:
        pass
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        s = t[i:j + 1]
        for tail in ("", "]} }", "]}]}"):
            try:
                return json.loads(s + tail)
            except Exception:
                continue
    return None


def main():
    if len(sys.argv) < 2:
        print("usage: adjudicate_l2.py <run_id> [--max N]")
        sys.exit(2)
    run_id = sys.argv[1]
    max_calls = None
    shard_i, shard_n = 0, 1
    if "--max" in sys.argv:
        max_calls = int(sys.argv[sys.argv.index("--max") + 1])
    if "--shard" in sys.argv:
        shard_i, shard_n = [int(x) for x in sys.argv[sys.argv.index("--shard") + 1].split("/")]
    out = L2_RUNS / run_id
    queue = [json.loads(l) for l in open(out / "adjudication-queue.jsonl", encoding="utf-8")]
    res_path = out / ("adjudications.shard%d.jsonl" % shard_i)
    done_ids = set()
    if res_path.exists():
        for line in res_path.read_text(encoding="utf-8").splitlines():
            try:
                done_ids.add(json.loads(line)["id"])
            except Exception:
                continue
    todo = [g for g in queue if g["id"] not in done_ids]
    todo = [g for i, g in enumerate(todo) if i % shard_n == shard_i]
    out = L2_RUNS / run_id
    log = ROOT / "data" / ("adjudicate_%s.shard%d.log" % (run_id, shard_i))
    log.parent.mkdir(exist_ok=True)

    def wlog(s):
        line = "[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), s)
        print(line, flush=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    wlog("start run=%s queue=%d done_before=%d todo=%d" % (run_id, len(queue), len(done_ids), len(todo)))

    # バッチ詰め
    batches, cur, cur_len = [], [], 0
    for g in todo:
        payload = {"id": g["id"], "edge_types": g["edge_types"],
                   "members": [compact_member(m) for m in g["members"][:10]]}
        blen = len(json.dumps(payload, ensure_ascii=False))
        if cur and (cur_len + blen > BATCH_CHARS or len(cur) >= 4):
            batches.append(cur)
            cur, cur_len = [], 0
        cur.append(payload)
        cur_len += blen
    if cur:
        batches.append(cur)
    wlog("batches=%d" % len(batches))

    from openai import OpenAI
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=600, max_retries=0)

    nf = OpenAI
    res_f = open(res_path, "a", encoding="utf-8")
    review_f = open(out / ("review-queue.shard%d.jsonl" % shard_i), "a", encoding="utf-8")
    n_done, n_fail = 0, 0
    for bi, batch in enumerate(batches):
        if max_calls is not None and n_done >= max_calls:
            wlog("max calls reached, stop (resumable)")
            break
        prompt = INSTR + json.dumps(batch, ensure_ascii=False)
        got = None
        for attempt in range(3):
            try:
                time.sleep(CALL_SLEEP)
                r = client.chat.completions.create(
                    model=MODEL, temperature=TEMP, max_tokens=MAX_TOKENS,
                    messages=[{"role": "user", "content": prompt}])
                got = parse_json_lenient(r.choices[0].message.content or "")
                if got and isinstance(got.get("results"), list) and got["results"]:
                    break
                got = None
            except Exception as e:
                wlog("call err b=%d a=%d: %s" % (bi, attempt, str(e)[:120]))
                time.sleep(2 + 2 * attempt)
        if not got:
            for g in batch:
                review_f.write(json.dumps({"id": g["id"], "reason": "parse_failed",
                                           "edge_types": g["edge_types"]}, ensure_ascii=False) + "\n")
                n_fail += 1
            review_f.flush()
            wlog("b=%d PARSE_FAILED x%d" % (bi, len(batch)))
            continue
        by_id = {r.get("id"): r for r in got["results"]}
        for g in batch:
            rec = by_id.get(g["id"])
            if not rec:
                review_f.write(json.dumps({"id": g["id"], "reason": "missing_in_answer"},
                                          ensure_ascii=False) + "\n")
                n_fail += 1
                continue
            res_f.write(json.dumps({"id": g["id"], "run": run_id,
                                    "decisions": rec.get("decisions", [])},
                                   ensure_ascii=False) + "\n")
            n_done += 1
        res_f.flush()
        if bi % 10 == 0:
            wlog("b=%d/%d done=%d fail=%d" % (bi, len(batches), n_done, n_fail))
    res_f.close()
    review_f.close()
    wlog("finished done=%d fail=%d remaining_todo=%d" % (n_done, n_fail, len(todo) - n_done))
    wlog("=== L2 ADJUDICATE DONE %s ===" % run_id)


if __name__ == "__main__":
    main()

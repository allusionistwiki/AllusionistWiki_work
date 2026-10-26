"""S3R: 再裁定 v2（P4 v2 プロトコル — 全話使用実 evidence で既存 alias 統合を検証）。

Usage: python scripts/adjudicate_l2_v2.py <run_id> [--max N]
Input : runs/<id>/review-evidence.jsonl
Output: runs/<id>/adjudications_v2.jsonl（keep/split/要検証）
        runs/<id>/review-v2-queue.jsonl（parse 落ち再投入）
        data/adjudicate_v2_<run_id>.log
方針: デフォルト分離。keep_alias は「全使用例で指示対象一致・反例なし」を引用で確認できた場合のみ。
"""
import json
import sys
import time
import collections
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import L2_RUNS
from openai import OpenAI

RUN = sys.argv[1]
OUT = L2_RUNS / RUN
MAX_TOKENS = 1400
CALL_SLEEP = 1.5

BASE_URL = "http://127.0.0.1:8080/v1"
API_KEY = "***"
MODEL = "swift-1.5-iq3_xxs"
TEMP = 1.0

INSTR = """あなたは固有名詞の同一性検証者です。小説全話からの使用実証拠が渡されます。
既に v1 で行われた名前の alias 統合（同一実体扱い）が正しいか検証してください。

規則:
- デフォルトは split（別実体）。alias 統合を維持(keep)してよいのは、全使用例で指示対象が一致し、反例が1つもない場合のみ。理由に具体的な根拠（ep・引用）を1つ以上書け。
- 反例 = 同じ場面で両名義が別の存在として並ぶ、指示対象が矛盾する使用、同一fact内共起（mech_split は機械検出済みの同一文共起=強い別人信号。keep を主張するなら「別表記の自己紹介・改名・二重命名の明言」が必要）。
- 証拠が薄く判断不能なものは needs。
- kind は証拠に振る舞いがある場合のみ調整（character/item/terminology/organization/location/motif/phrase/event/creature/relationship のいずれか）。

出力は JSON のみ。形式:
{"results":[{"id":"<gid>","verdicts":[{"norm":"...","decision":"keep|split|needs","canonical":"...","kind":"...","confidence":"明言|蓋然性高|要検証","reason":"40字以内で根拠の要点のみ"}]}]}
判定対象は prev で alias 判定された norm のみ。prev が空の群は {"results":[{"id":"<gid>","verdicts":[]}]} を返せ。

群データ:
"""


def parse_json_lenient(txt):
    i = txt.find("{")
    if i < 0:
        return None
    try:
        return json.loads(txt[i:])
    except json.JSONDecodeError:
        j = txt.rfind("}")
        while j > i:
            try:
                return json.loads(txt[i:j + 1])
            except json.JSONDecodeError:
                j = txt.rfind("}", i, j)
    return None


def main():
    max_calls = 10 ** 9
    for a in sys.argv[2:]:
        if a.startswith("--max"):
            max_calls = int(a.split("=")[1]) if "=" in a else int(a[5:])
    log_path = L2_RUNS.parents[3] / "data" / ("adjudicate_v2_%s.log" % RUN)
    log_path.parent.mkdir(exist_ok=True)

    def wlog(m):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), m)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    rows = [json.loads(l) for l in (OUT / "review-evidence.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    done_ids = set()
    outp = OUT / "adjudications_v2.jsonl"
    if outp.exists():
        for l in outp.read_text(encoding="utf-8").splitlines():
            try:
                done_ids.add(json.loads(l)["id"])
            except Exception:
                pass
    todo = [r for r in rows if r["id"] not in done_ids]
    wlog("start run=%s rows=%d done_before=%d todo=%d"
         % (RUN, len(rows), len(done_ids), len(todo)))

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=600, max_retries=0)
    review_path = OUT / "review-v2-queue.jsonl"
    n_done = n_fail = 0

    def slim_of(row):
        slim = {"id": row["id"], "edge_types": row.get("edge_types", []),
                "prev": {k: v for k, v in row.get("prev", {}).items()
                         if v.get("verdict") == "alias"},
                "mech_split": row.get("mech_split", []),
                "members": []}
        for m in row.get("members", []):
            mm = {"norm": m["norm"], "count": m.get("count", 0),
                  "surfaces": m.get("surfaces", [])[:3],
                  "evidence": [{k: (str(v)[:60] if k == "q" else v)
                                for k, v in e.items()} for e in m.get("evidence", [])[:5]]}
            slim["members"].append(mm)
        return slim

    def chunk_rows(sl, cap_chars=5000):
        # 巨大群は members をチャンク分割（同一 id で再投入、resume 安全）
        chunks, cur, ln = [], [], len(json.dumps({k: v for k, v in sl.items() if k != "members"}, ensure_ascii=False))
        for m in sl["members"]:
            ml = len(json.dumps(m, ensure_ascii=False))
            if cur and ln + ml > cap_chars:
                chunks.append({**sl, "members": cur})
                cur, ln = [], len(json.dumps({k: v for k, v in sl.items() if k != "members"}, ensure_ascii=False))
            cur.append(m)
            ln += ml
        if cur:
            chunks.append({**sl, "members": cur})
        return chunks

    batches, cur, cur_len, cur_v = [], [], 0, 0
    for row in todo:
        sl = slim_of(row)
        ln = len(json.dumps(sl, ensure_ascii=False))
        nv = len(sl["prev"]) + len(sl["mech_split"])  # 出力を支配する判断数
        if ln > 5200:
            for ch in chunk_rows(sl):
                chl = len(json.dumps(ch, ensure_ascii=False))
                chnv = len(ch["prev"]) + len(ch["mech_split"])
                if cur and (cur_len + chl > 5000 or len(cur) >= 2 or cur_v + chnv > 28):
                    batches.append(cur)
                    cur, cur_len, cur_v = [], 0, 0
                cur.append(ch)
                cur_len += chl
                cur_v += chnv
            continue
        if cur and (cur_len + ln > 5000 or len(cur) >= 2 or cur_v + nv > 28):
            batches.append(cur)
            cur, cur_len, cur_v = [], 0, 0
        cur.append(sl)
        cur_len += ln
        cur_v += nv
    if cur:
        batches.append(cur)
    wlog("batches=%d" % len(batches))

    for bi, batch in enumerate(batches):
        if bi >= max_calls:
            wlog("max calls reached, stop (resumable)")
            break
        prompt = INSTR + json.dumps(batch, ensure_ascii=False)
        got = None
        for attempt in range(3):
            try:
                time.sleep(CALL_SLEEP)
                r = client.chat.completions.create(
                    model=MODEL, temperature=TEMP, max_tokens=MAX_TOKENS,
                    extra_body={"chat_template_kwargs":
                                {"thinking": False, "enable_thinking": False}},
                    messages=[{"role": "user", "content": prompt}])
                got = parse_json_lenient(r.choices[0].message.content or "")
                if got and isinstance(got.get("results"), list) and got["results"]:
                    break
                got = None
            except Exception as e:
                wlog("call err b=%d a=%d: %s" % (bi, attempt, str(e)[:100]))
        answered = {}
        if got:
            for res in got["results"]:
                answered[res.get("id")] = res.get("verdicts", [])
            with outp.open("a", encoding="utf-8") as f:
                for sl in batch:
                    if sl["id"] in answered:
                        f.write(json.dumps({"id": sl["id"], "run": RUN,
                                            "verdicts": answered[sl["id"]]},
                                           ensure_ascii=False) + "\n")
                        n_done += len(answered[sl["id"]])
        for sl in batch:
            if sl["id"] not in answered:
                with review_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"id": sl["id"], "reason": "parse_failed"},
                                       ensure_ascii=False) + "\n")
                n_fail += 1
        if bi % 25 == 0:
            wlog("b=%d/%d done=%d fail=%d" % (bi, len(batches), n_done, n_fail))
    wlog("finished done=%d fail=%d remaining=%d" % (n_done, n_fail, len(todo)))
    wlog("=== L2 ADJUDICATE V2 DONE %s ===" % RUN)


if __name__ == "__main__":
    main()

"""S3V3: エンティティ有効性裁定（v3 — 台帳外 surface の実体判定・所属付け）。

Usage: python scripts/adjudicate_l2_v3.py <run_id> [--max N]
Input : runs/<id>/v3-review-queue.jsonl
Output: runs/<id>/adjudications_v3.jsonl
方針: 独立実体か、既存実体の付属(aspect)か、実体でないか（一般名詞）を裁定する。
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import L2_RUNS
from openai import OpenAI

RUN = sys.argv[1]
OUT = L2_RUNS / RUN
MAX_TOKENS = 1500
CALL_SLEEP = 1.5

BASE_URL = "http://127.0.0.1:8080/v1"
API_KEY = "qwe***345"
MODEL = "swift-1.5-iq3_xxs"
TEMP = 1.0

INSTR = """あなたは小説のエンティティ台帳の品質審査者です。台帳に登録されていない名義が渡されます。
各名義について、その名義が「何であるか」を判定してください。

判定 categories:
- standalone: 独立した実体（キャラクター character / 物 item / 用語 terminology / 組織 organization / 場所 location / 種族 creature / 事件 event / 関係 relationship / 概念 motif-phrase など）。kind を付ける。
- aspect_of: 既存キャラクター・実体に付随する属性・状態・側面（例:「アキラの正体」「◯◯の心」「◯◯の能力」）。parent（付随先）に parent_candidates のいずれかを指定。
- generic: 個別実体ではない一般名詞・場面・类别（例:「戦場」「街路」「観客」「男」）。実体台帳に載せるべきでない。
- alias_of: 既存の parent_candidates に挙がった名義の単なる表記ゆれ・別名。target にその名義を指定。
- needs: 証拠が薄く判定不能。

規則:
- 引用と entity_type 投票が最優先の根拠。名前形式（所有構文・敬称）は補助。
- 「〜の正体/心/能力/腕/姿」型は原則 aspect_of、parent は所有構文の側。
- 明显な一般名詞（場所種別・人物类别・抽象名）は standalone にせず generic。
- confidence は 明言/蓋然性高/要検証。

出力は JSON のみ。形式:
{"verdicts":[{"norm":"...","category":"standalone|aspect_of|generic|alias_of|needs","kind":"character|item|terminology|organization|location|creature|event|relationship|motif|phrase|-","parent":"...|-","target":"...|-","confidence":"明言|蓋然性高|要検証","reason":"30字以内"}]}
入力の norm すべてに verdict を返せ。

データ:
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
    log_path = L2_RUNS.parents[3] / "data" / ("adjudicate_v3_%s.log" % RUN)
    log_path.parent.mkdir(exist_ok=True)

    def wlog(m):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), m)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    rows = [json.loads(l) for l in (OUT / "v3-review-queue.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    outp = OUT / "adjudications_v3.jsonl"
    done_ids = set()
    if outp.exists():
        for l in outp.read_text(encoding="utf-8").splitlines():
            try:
                done_ids.add(json.loads(l)["id"])
            except Exception:
                pass
    todo = [r for r in rows if r["id"] not in done_ids]
    wlog("start run=%s rows=%d todo=%d" % (RUN, len(rows), len(todo)))

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=600, max_retries=0)
    n_done = n_fail = 0
    review_path = OUT / "v3-retry-queue.jsonl"

    def slim(row):
        tg = []
        for t in row["targets"]:
            tg.append({
                "norm": t["norm"],
                "events_count": t["events_count"],
                "entity_type_votes": dict(list(t["entity_type_votes"].items())[:3]),
                "page_subtype": t["page_subtype"],
                "quotes": t["quotes"][:2],
                "parent_candidates": t["parent_candidates"],
                "in_ledger": t["in_ledger"],
            })
        return {"id": row["id"], "targets": tg}

    batches, cur, cur_len = [], [], 0
    for row in todo:
        sl = slim(row)
        ln = len(json.dumps(sl, ensure_ascii=False))
        if cur and cur_len + ln > 5500:
            batches.append(cur)
            cur, cur_len = [], 0
        cur.append(sl)
        cur_len += ln
    if cur:
        batches.append(cur)
    wlog("batches=%d" % len(batches))

    with outp.open("a", encoding="utf-8") as fo:
        for bi, batch in enumerate(batches):
            if bi >= max_calls:
                wlog("max_calls reached, remaining=%d" % (len(batches) - bi))
                break
            prompt = INSTR + json.dumps(batch, ensure_ascii=False)
            ok = False
            for attempt in range(3):
                try:
                    resp = client.chat.completions.create(
                        model=MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=TEMP, max_tokens=MAX_TOKENS,
                        extra_body={"chat_template_kwargs": {"thinking": False, "enable_thinking": False}},
                    )
                    txt = resp.choices[0].message.content or ""
                    data = parse_json_lenient(txt)
                    if data and data.get("verdicts"):
                        rec = {"id": batch[0]["id"], "batch_ids": [b["id"] for b in batch],
                               "verdicts": data["verdicts"]}
                        fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        fo.flush()
                        n_done += 1
                        ok = True
                        break
                except Exception as e:
                    wlog("call err b=%d a=%d: %s" % (bi, attempt, str(e)[:80]))
                    time.sleep(5)
            if not ok:
                n_fail += 1
                with review_path.open("a", encoding="utf-8") as fr:
                    for b in batch:
                        fr.write(json.dumps(b, ensure_ascii=False) + "\n")
            if (bi + 1) % 25 == 0:
                wlog("b=%d/%d done=%d fail=%d" % (bi + 1, len(batches), n_done, n_fail))
            time.sleep(CALL_SLEEP)
    wlog("finished done=%d fail=%d" % (n_done, n_fail))
    wlog("=== L2 ADJUDICATE V3 DONE %s ===" % RUN)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Lane P Step2: 創作候補の LLM バッチ判定（10 件/呼び出し・Strata 直列）。

入力: data/yuragi_works_candidates.json（Step1 スクリーニング）
出力: data/yuragi_works_judged.jsonl（{ref, creative, kind, title, author_hint}）
progress: data/yuragi_worksjudge_progress.txt（ref 済行）
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
CANDS = Path(os.environ.get("YJ_CANDS", W / "data/yuragi_works_candidates.json"))
PROG = Path(os.environ.get("YJ_PROG", W / "data/yuragi_worksjudge_progress.txt"))
OUTJ = Path(os.environ.get("YJ_OUTJ", W / "data/yuragi_works_judged.jsonl"))

PROMPT = """あなたは創作索引監査人です。以下は同一スレの全文コーパスから抽出した未収録投稿 {N} 件です。各投稿に「作品として数えうる創作的記述」（詩・歌詞・短編・小説断片・設定資料・劇中作品文・伝承文・格言集 等）があるか判定してください。
BBS の会話・雑談・連絡・実在作品の紹介・一字書き込み・返信のみの投稿は creative=false。
出力 JSON のみ:
{"results":[{"no": 番号, "creative": true/false, "kind": "詩|歌詞|短編|小説|設定文|伝承文|劇中作品|その他", "title": "作品名（原文の【題】等・なければ要約語）"}]}
--- 投稿一覧 ---
{BODY}"""


def jl(p: Path):
    if not p.is_file():
        return []
    out = []
    for l in p.read_bytes().decode("utf-8", "replace").splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        if isinstance(r, dict) and "_meta" in r:
            continue
        out.append(r)
    return out


def main():
    cands = json.loads(CANDS.read_text(encoding="utf-8"))
    # 全文を structured.jsonl から復元（head は先頭 220 字のみ）
    posts: dict = {}
    for uid in sorted({c["uid"] for c in cands}):
        try:
            sd, meta = ex.unit_dir(uid)
        except Exception:
            continue
        for r in jl(sd / "structured.jsonl"):
            posts[f"{uid}:{r.get('post_no')}"] = str(r.get("body", ""))
    for c in cands:
        c["full"] = posts.get(c["ref"], c.get("head", ""))
    done = set()
    if PROG.is_file():
        done = {l.strip() for l in PROG.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [c for c in cands if c["ref"] not in done]
    print(f"[laneP2] cands={len(cands)} todo={len(todo)}")
    # 同一 uid 継続の分割投稿をバッチまとめる（10 件/呼び）
    ok = errs = 0
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        try:
            body = "\n".join(f"【{j + 1}·{c['ref']}】{str(c.get('full', c['head']))[:1500]}"
                             for j, c in enumerate(batch))
            raw = None
            for att in range(6):
                try:
                    raw = ex.call_llm(PROMPT.replace("{N}", str(len(batch))).replace("{BODY}", body),
                                      max_tokens=1500)
                    break
                except Exception:
                    time.sleep(5 * (2 ** att))
            d = ex.parse_json_lenient(raw) if raw else None
            res = (d or {}).get("results", [])
            judged = {int(r0.get("no", 0)): r0 for r0 in res if isinstance(r0, dict)}
            with OUTJ.open("a", encoding="utf-8") as fd:
                for j, c in enumerate(batch, 1):
                    r0 = judged.get(j, {})
                    fd.write(json.dumps({"ref": c["ref"],
                                         "creative": bool(r0.get("creative")),
                                         "kind": r0.get("kind", ""),
                                         "title": r0.get("title", ""),
                                         "score": c["score"]}, ensure_ascii=False) + "\n")
                    done.add(c["ref"])
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write("\n".join(c["ref"] for c in batch) + "\n")
            ok += sum(1 for j in range(1, len(batch) + 1) if judged.get(j, {}).get("creative"))
            if (i // 10 + 1) % 5 == 0:
                print(f"[laneP2] {min(i + 10, len(todo))}/{len(todo)} judged_creative={ok} err={errs}", flush=True)
        except Exception as e:
            errs += 1
            print(f"[laneP2] batch ERR @ {i}: {type(e).__name__} {e}", flush=True)
            if errs >= 8:
                print("[laneP2] abort: 8 連続エラー", flush=True)
                return 1
    print(f"[laneP2] FINISH judged_creative={ok} err={errs}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

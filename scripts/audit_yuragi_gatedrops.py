# -*- coding: utf-8 -*-
"""Lane E: gate_drops 回収監査（Strata 直列・resume 対応）。

各 gate drop 項目を window 原文ごと再読し、keep 判定なら引用を逐語採集して
unit jsonl へ復元（mech_gate の引用検証を通過したものだけ）。
台帳: data/yuragi_gatedrops_progress.txt（uid<TAB>term 済）。来歴: 各 run の gate_audit.jsonl。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
L1 = W / "work" / "yuragi" / "L1"
RUNS = L1 / "runs"
PROG = W / "data" / "yuragi_gatedrops_progress.txt"

PROMPT = """あなたは実世界参照（allusion）抽出の gate drop 回収監査人です。
以下の使用説明（gate により公開対象外とされた項目）を、原文実読で keep/drop 裁定してください。
基準:
- keep: 原文が実世界対象（神話・宗教・文学・映像・ゲーム・ブランド・実在人物・地名・学術概念・ネットサービス・ミーム 等）への参照を明示している。
- drop: 作中創作（作中地名/条約/神/催事/書物）、一般名詞（物品・食品・動物・日用品・类别語・一般地名）、原文に明示のない知識想起。
- 一般名詞でも、作品引用・連作体系・比喩体系・命名源として原文が明示する場合は keep。
- quotes は原文からの逐語（130 字以内、ref 形式「{UID}:投稿番号」）。原文に無い文字列を出してはならない。
出力は JSON のみ:
{{"verdict":"keep"|"drop","kind":"神話|宗教|文学|人物|歴史|地理|映像|音楽|ゲーム|ブランド|科学|その他","usage":"日本語一文の使用実態","reason":"裁定理由 日本語一文","quotes":[{{"ref":"{UID}:N","q":"逐語引用"}}]}}
--- 監査対象（gate={GATE}） ---
term: {TERM}
usage: {USAGE}
--- 本文（{UID} 投稿{LO}〜{HI}） ---
{BODY}"""


def jl(p: Path):
    if not p.is_file():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            if isinstance(r, dict) and "_meta" in r:
                continue
            out.append(r)
    return out


def load_drops():
    seen: dict = {}
    for run in sorted(RUNS.glob("202611*_l1a2b*")):
        fp = run / "allusions" / "gate_drops.jsonl"
        for d in jl(fp):
            k = (d.get("uid", ""), ex.norm(d.get("term", "")))
            if k not in seen:
                seen[k] = (run, d)
    return seen


def main():
    done = set()
    if PROG.is_file():
        for l in PROG.read_text(encoding="utf-8").splitlines():
            if "\t" in l:
                uid, term = l.split("\t", 1)
                done.add((uid, ex.norm(term)))
    drops = load_drops()
    todo = [(k, v) for k, v in drops.items() if k[0] not in done]
    print(f"[laneE] drops={len(drops)} done={len(done)} todo={len(todo)}", flush=True)
    kept = dropped = errs = 0
    for i, ((uid, tk), (run, d)) in enumerate(sorted(todo, key=lambda x: x[0][0])):
        term = d.get("term", "")
        try:
            dd, meta = ex.unit_dir(uid)
            posts = {r["post_no"]: r["body"] for r in jl(dd / "structured.jsonl")}
            nums = sorted(posts)
            windows = [nums[j:j + 60] for j in range(0, len(nums), 60)]
            wi = max(0, int(d.get("win", 1)) - 1)
            if wi >= len(windows):
                wi = 0
            win = windows[wi]
            body = "\n".join(f"【投稿{n}】{posts[n]}" for n in win)
            body = body[:26000]
            lo, hi = win[0], win[-1]
            prompt = (PROMPT.replace("{UID}", uid).replace("{TERM}", term)
                      .replace("{USAGE}", str(d.get("usage", ""))[:300])
                      .replace("{GATE}", str(d.get("gate", "")))
                      .replace("{LO}", str(lo)).replace("{HI}", str(hi))
                      .replace("{BODY}", body))
            raw = None
            for att in range(5):
                try:
                    raw = ex.call_llm(prompt, max_tokens=1200)
                    break
                except Exception as e:
                    time.sleep(5 * (2 ** att))
            data = ex.parse_json_lenient(raw) if raw else None
            verdict = str((data or {}).get("verdict", "")).lower()
            audit_rec = {"uid": uid, "term": term, "gate": d.get("gate", ""),
                         "verdict": verdict, "run": run.name}
            if verdict == "keep":
                item = {"term": term, "kind": str(data.get("kind", "その他")),
                        "confidence": "監査回収", "usage": str(data.get("usage", "")),
                        "quotes": [q for q in data.get("quotes", [])
                                   if isinstance(q, dict)][:5]}
                it2, st = ex.mech_gate(uid, item, posts)
                if st == "ok":
                    outp = run / "allusions" / f"{uid}.jsonl"
                    have = {ex.norm(str(x.get("term", ""))) for x in jl(outp)}
                    if ex.norm(term) not in have:
                        with outp.open("a", encoding="utf-8") as fd:
                            fd.write(json.dumps(it2, ensure_ascii=False) + "\n")
                        kept += 1
                        audit_rec["restored"] = True
                    else:
                        audit_rec["restored"] = False
                        audit_rec["note"] = "dup: 同名項目が既に公開面"
                else:
                    audit_rec["restored"] = False
                    audit_rec["note"] = f"mech_gate {st}"
                    dropped += 1
            else:
                audit_rec["restored"] = False
                dropped += 1
            with (run / "gate_audit.jsonl").open("a", encoding="utf-8") as fd:
                fd.write(json.dumps(audit_rec, ensure_ascii=False) + "\n")
        except Exception as e:
            errs += 1
            print(f"[laneE] ERR {uid}/{term}: {type(e).__name__} {e}", flush=True)
            if errs >= 8:
                print("[laneE] abort: 8 連続エラー（Strata 疑い）", flush=True)
                return 1
        with PROG.open("a", encoding="utf-8") as fd:
            fd.write(f"{uid}\t{term}\n")
        done.add((uid, tk))
        if (i + 1) % 10 == 0:
            print(f"[laneE] {i + 1}/{len(todo)} kept={kept} drop={dropped} err={errs}", flush=True)
    print(f"[laneE] FINISH kept={kept} drop={dropped} err={errs}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

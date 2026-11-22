# -*- coding: utf-8 -*-
"""Lane J: suppressions drop 520 件の再裁定（ユーザー基準 2026-11-22 最終＝物体/素材/食品は記事化）。

各 drop 裁定の原文窓を再読し、新基準で keep/drop 再裁定。
keep → 当該 suppressions 行を除去（公開面へ復帰）＋ reaudit.jsonl 来歴。
drop 維持 → 現行行に reaudit 注記を追記。
台帳: data/yuragi_reaudit_progress.txt（unit<TAB>term）。Strata 直列 workers=1。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
RUNS = W / "work" / "yuragi" / "L1" / "runs"
PROG = W / "data" / "yuragi_reaudit_progress.txt"

PROMPT = """あなたは allusion（実世界参照）drop 裁定の再監査人です。
2026-11-22 確定基準:
- 記事化の判定は分類（物/食品/人名…）では行わない。**drop を確定する前に、その対象に対して「創作活動」が行われているかを実読で判定する**。
- 創作活動の例: 対象についての描写・物語・設定の構築、語遊び・ダジャレ・かけ合い、命名源・語源の考案、比喩体系や概念体系への組込み、詩・歌・随筆的表現、ゲームや作品内の素材としての仕込み、考察・論考の主題にする 等。創作活動がある対象は **keep（記事化が必要）**。食品・物品・動物・素材でも創作活動の素材になっているなら keep（納豆・味噌・きしめん等）。
- drop は次の場合のみ: 原文に対象について創作活動が全く無い（単なる列挙・舞台の小道具として一度触れるだけ・会話の流れの中の一語）。実在固有名を**命名素材に借用しただけ**（坂本・山田・マイケル型）。原文に明示のない知識想起。
- 判断は必ず下の実読窓に基づく。窓に出現しない知識を使わない。
出力 JSON のみ:
{{"verdict":"keep"|"drop","reason":"日本語一文（窓の該当表現を引用し、創作活動の有無を述べる）"}}
--- 再監査対象 ---
term: {TERM}
旧裁定: drop（{OLD_REASON}）
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


def main():
    done = set()
    if PROG.is_file():
        for l in PROG.read_text(encoding="utf-8").splitlines():
            if "\t" in l:
                uid, term = l.split("\t", 1)
                done.add((uid, ex.norm(term)))
    todo = []
    seen: set = set()
    for sp in sorted(RUNS.glob("202611*_l1a2b*/suppressions.json")):
        for s in json.loads(sp.read_text(encoding="utf-8")):
            if s.get("action") != "drop":
                continue
            uid = str(s.get("unit", ""))
            term = str(s.get("term", "")).strip()
            k = (uid, ex.norm(term))
            if k in done or k in seen:
                continue
            seen.add(k)
            todo.append((sp, uid, term, str(s.get("reason", ""))[:100]))
    print(f"[laneJ] todo={len(todo)} done={len(done)}", flush=True)
    revoked = kept0 = errs = 0
    for i, (sp, uid, term, old) in enumerate(todo):
        try:
            dd, meta = ex.unit_dir(uid)
            posts = {r["post_no"]: r["body"] for r in jl(dd / "structured.jsonl")}
            nums = sorted(posts)
            # 窓特定: term が本文に出現する投稿群
            hits = [n for n in nums if term and term[:3] in posts[n]]
            if hits:
                lo = max(1, hits[0] - 20)
                hi = min(nums[-1], hits[0] + 40)
            else:
                lo, hi = nums[0], min(nums[-1], 60)
            body = "\n".join(f"【投稿{n}】{posts[n]}" for n in range(lo, hi + 1) if n in posts)
            body = body[:26000]
            prompt = (PROMPT.replace("{UID}", uid).replace("{TERM}", term)
                      .replace("{OLD_REASON}", old)
                      .replace("{LO}", str(lo)).replace("{HI}", str(hi))
                      .replace("{BODY}", body))
            raw = None
            for att in range(5):
                try:
                    raw = ex.call_llm(prompt, max_tokens=600)
                    break
                except Exception:
                    time.sleep(5 * (2 ** att))
            data = ex.parse_json_lenient(raw) if raw else None
            verdict = str((data or {}).get("verdict", "")).lower()
            if verdict == "keep":
                arr = json.loads(sp.read_text(encoding="utf-8"))
                k = term.strip().lower().replace("・", "").replace(" ", "")
                out = []
                for s in arr:
                    kk = str(s.get("term", "")).strip().lower().replace("・", "").replace(" ", "")
                    if str(s.get("unit", "")) == uid and kk == k and s.get("action") == "drop":
                        continue
                    out.append(s)
                sp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
                revoked += 1
            else:
                kept0 += 1
            rec = {"unit": uid, "term": term, "verdict": verdict if verdict in ("keep", "drop") else "invalid",
                   "reason": str((data or {}).get("reason", ""))[:150]}
            with (sp.parent / "reaudit.jsonl").open("a", encoding="utf-8") as fd:
                fd.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except KeyError as e:
            rec = {"unit": uid, "term": term, "verdict": "skip", "reason": f"KeyError {e}"}
            with (sp.parent / "reaudit.jsonl").open("a", encoding="utf-8") as fd:
                fd.write(json.dumps(rec, ensure_ascii=False) + "\n")
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write(f"{uid}\t{term}\n")
            continue
        except Exception as e:
            errs += 1
            print(f"[laneJ] ERR {uid}/{term}: {type(e).__name__} {e}", flush=True)
            if errs >= 8:
                print("[laneJ] abort: 8 連続エラー（Strata 疑い）", flush=True)
                return 1
            continue
        with PROG.open("a", encoding="utf-8") as fd:
            fd.write(f"{uid}\t{term}\n")
        if (i + 1) % 10 == 0:
            print(f"[laneJ] {i + 1}/{len(todo)} revoked={revoked} drop維持={kept0} err={errs}", flush=True)
    print(f"[laneJ] FINISH revoked={revoked} drop維持={kept0} err={errs}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

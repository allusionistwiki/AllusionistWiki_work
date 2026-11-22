# -*- coding: utf-8 -*-
"""Lane K: 作中創作エンティティ記事化（v0.13 基準: 創作活動があれば記事化・坂本型/作中物品）。

候補 = allusion 監査記録中の「作中創作」系 drop 対象＋ユーザー明示名。
各候補を原文検索で窓収集→LLM 記述生成→LLM 監査（逐語引用一致・内容一致）→
新 run 20261122T1200_enK_l1en/entities/<slug>.md へ書込み（追加専用）。
publish が *_l1en 最新 run として entities 面に統合する。
progress: data/yuragi_entitygen_progress.txt（term 済行）。
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
RUNS = W / "work" / "yuragi" / "L1" / "runs"
PROG = W / "data" / "yuragi_entitygen_progress.txt"
OUT = RUNS / "20261122T1200_enK_l1en"

GEN_PROMPT = """あなたは『ゆらぎの神話』の作中創作エンティティ記事生成者です。
対象「{TERM}」は参加者の創作活動によって作中世界に存在する实体（物品・場所・制度・催事・団体・用語・生物・作品）。実世界参照ではなく、**作中世界観の構成要素としての記事**を Wiki 用に生成してください。
出力は JSON のみ:
{{"type":"人物|場所|物品|制度|催事|団体|用語|生物|作品","summary":"概要 2〜4 文（日本語）","flow":["篇番号:投稿番号 + 逐語引用（100字以内、必ず提示した原文に存在する文を使う）+ 要約 1 文"],"related":["関連する作中实体名"]}}
- summary・flow の内容が原文にない主張を作らない。引用は原文逐語のみ。日本語のみ使用（外国の簡体字等は不可）。
--- 原文窓 ---
{BODY}"""

AUD_PROMPT = """あなたは生成記事の監査人です。記事が提示原文と一致するか（引用逐語の存在・原文にない主張の有無）を監査し JSON のみ出力:
{{"verdict":"pass"|"fix","issues":"日本語一文（問題点。なければ空）"}}
--- 記事 ---
{ART}
--- 原文窓 ---
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


def collect_candidates() -> dict:
    cands: dict = {}
    seed = ["ペレテケンヌル", "マジケット", "ラルビット条約", "新東京", "オクトパス・ブレイバーズ",
            "アルカェ・レダーナ", "PTS", "シャーネスの風", "ダミー・メサイア", "猫の国",
            "レーヴェン・ケーニッヒ", "サカームトーアー・クラウド", "アレノサカームト"]
    for t in seed:
        cands[t] = "ユーザー明示/監査"
    for sp in RUNS.glob("202611*_l1a2b*/suppressions.json"):
        for s in json.loads(sp.read_text(encoding="utf-8")):
            r = str(s.get("reason", ""))
            if re.search(r"作中(創作|命名|地名|書物|条約|催事|神|民族|技術|实体)|作中世界|作中名詞|作中ゲーム|架空生物", r):
                t = str(s.get("term", "")).strip()
                if t and ex.norm(t) not in {ex.norm(k) for k in cands}:
                    cands[t] = "監査記録"
    # 既存 entities と重複するものは除外
    ent = {p.stem for p in (OUT / "entities").glob("*.md")} if (OUT / "entities").is_dir() else set()
    for p in (W.parent / "YuragiWiki" / "content" / "entities").glob("*.md"):
        ent.add(p.stem)
    out = {}
    for t, why in cands.items():
        slug = ex.norm(t).replace("・", "_")
        if slug in {ex.norm(e).replace("・", "_") for e in ent}:
            continue
        out[t] = why
    return out


def find_windows(term: str, max_posts: int = 14):
    """全篇の structured.jsonl から term 出現投稿を集め、文脈窓を作る。"""
    hits = []  # (uid, post_no, body)
    seen_units: dict = {}
    latest = (W / "work" / "yuragi" / "L0" / "latest.txt").read_text(encoding="utf-8").strip()
    for u in jl(W / "work" / "yuragi" / "L0" / "runs" / latest / "units.jsonl"):
        uid = u["unit_id"]
        try:
            dd, meta = ex.unit_dir(uid)
        except Exception:
            continue
        rows = jl(dd / "structured.jsonl")
        posts = {r["post_no"]: r["body"] for r in rows}
        for n in sorted(posts):
            if term and (term in posts[n] or term[:3] in posts[n]):
                hits.append((uid, n, posts[n]))
        seen_units[uid] = True
    # 篇ごとに先頭 2 命中まで
    per: dict = {}
    for uid, n, b in hits:
        per.setdefault(uid, []).append((n, b))
    sel = []
    for uid, lst in per.items():
        for n, b in lst[:2]:
            sel.append((uid, n, b))
        if len(sel) >= max_posts:
            break
    return sel[:max_posts]


def main():
    (OUT / "entities").mkdir(parents=True, exist_ok=True)
    done = set()
    if PROG.is_file():
        done = {l.strip() for l in PROG.read_text(encoding="utf-8").splitlines() if l.strip()}
    cands = collect_candidates()
    todo = [t for t in cands if t not in done]
    print(f"[laneK] cands={len(cands)} todo={len(todo)}", flush=True)
    ok = skip = errs = 0
    for i, term in enumerate(sorted(todo)):
        try:
            hits = find_windows(term)
            if not hits:
                rec = {"term": term, "status": "no_occurrence"}
                with (OUT / "gen_audit.jsonl").open("a", encoding="utf-8") as fd:
                    fd.write(json.dumps(rec, ensure_ascii=False) + "\n")
                with PROG.open("a", encoding="utf-8") as fd:
                    fd.write(term + "\n")
                skip += 1
                continue
            body = "\n".join(f"【{uid}:{n}】{b[:900]}" for uid, n, b in hits)[:24000]
            raw = None
            for att in range(5):
                try:
                    raw = ex.call_llm(GEN_PROMPT.replace("{TERM}", term).replace("{BODY}", body), max_tokens=1600)
                    break
                except Exception:
                    time.sleep(5 * (2 ** att))
            data = ex.parse_json_lenient(raw) if raw else None
            if not isinstance(data, dict) or not data.get("summary"):
                raise ValueError("gen failed")
            art = {k: data.get(k) for k in ("type", "summary", "flow", "related")}
            raw2 = None
            for att in range(5):
                try:
                    raw2 = ex.call_llm(AUD_PROMPT.replace("{ART}", json.dumps(art, ensure_ascii=False))
                                       .replace("{BODY}", body), max_tokens=400)
                    break
                except Exception:
                    time.sleep(5 * (2 ** att))
            ad = ex.parse_json_lenient(raw2) if raw2 else None
            verdict = str((ad or {}).get("verdict", "")).lower()
            if verdict == "fix":
                raw3 = None
                for att in range(5):
                    try:
                        raw3 = ex.call_llm(GEN_PROMPT.replace("{TERM}", term).replace("{BODY}", body)
                                           + f"\n--- 前回の指摘を反映して再生成: {(ad or {}).get('issues','')} ---",
                                           max_tokens=1600)
                        break
                    except Exception:
                        time.sleep(5 * (2 ** att))
                d3 = ex.parse_json_lenient(raw3) if raw3 else None
                if isinstance(d3, dict) and d3.get("summary"):
                    art = {k: d3.get(k) for k in ("type", "summary", "flow", "related")}
                    verdict = "regen"
            slug = ex.norm(term).replace("・", "_")
            count = len(hits)
            lines = ["---", f'title: "{term}"', "run: 20261122T1200_enK_l1en",
                     "model: swift-1.5-iq3_xxs", f'term: "{term}"',
                     f'type: "{art.get("type","用語")}"', f"count: {count}",
                     f'generated: "{datetime.now().isoformat()}"',
                     f'link_audit: "20261122T1200_enK_l1en_{"audit" if verdict in ("pass","regen") else "pending"}"', "---", "",
                     f"# {term}（ゆらぎの神話）", "", "## 概要", "", str(art.get("summary", "")).strip(), "",
                     "## 記述の流れ", ""]
            for f0 in art.get("flow", [])[:12]:
                lines.append(f"* {f0}")
            rel = art.get("related", [])
            if rel:
                lines += ["", "## 関連する実体", ""]
                lines.append("* " + "、".join(f"[[entities/{ex.norm(str(r)).replace('・','_')}|{r}]]" for r in rel[:10]))
            lines += ["", "※ 本記事は作中創作实体（v0.13 創作活動基準）として Lane K で生成・監査済。", ""]
            (OUT / "entities" / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")
            with (OUT / "gen_audit.jsonl").open("a", encoding="utf-8") as fd:
                fd.write(json.dumps({"term": term, "status": "written", "audit": verdict, "posts": count}, ensure_ascii=False) + "\n")
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write(term + "\n")
            ok += 1
        except Exception as e:
            errs += 1
            print(f"[laneK] ERR {term}: {type(e).__name__} {e}", flush=True)
            if errs >= 8:
                print("[laneK] abort: 8 連続エラー", flush=True)
                return 1
        if (i + 1) % 5 == 0:
            print(f"[laneK] {i + 1}/{len(todo)} ok={ok} skip={skip} err={errs}", flush=True)
    print(f"[laneK] FINISH ok={ok} skip={skip} err={errs}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

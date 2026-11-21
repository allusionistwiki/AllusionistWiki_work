#!/usr/bin/env python3
"""Yuragi 解析層 pilot: 実世界参照（allusion）抽出 — 篇本文窓 → LLM 抽出 → 機械ゲート（逐語/ref 実在）。

python scripts/extract_yuragi_allusions.py --uids YJ-T018 YJ-T024 [--workers 2] [--run-dir rid]
出力: work/yuragi/L1/runs/<rid>/allusions/<uid>.jsonl（1 行 1 抽出物・resume 対応）
     <rid>/log.txt（窓進行・DONE マーカー）
機械ゲート: q が対象 ref 投稿 body の正規化後連続部分文字列（入れ子引用・装飾除去・空白除去）。
          ref 実在（篇:番号）。q 100 字超なし。CN 専用グリフ検出は prose 部のみ（引用は逐語保護）。
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
L1 = W / "work" / "yuragi" / "L1"
CN = set("实气时门关开语说话请谢过义习乡乐头图圆园员资货邮译议军队丰艺节丛兰标网吗呢吧们这她它您哥币儿什戏")
KINDS = {"神話", "宗教", "文学", "音楽", "映像", "ゲーム", "歴史", "地理", "科学", "人物", "ブランド", "その他"}
KIND_FIX = {"游戏": "ゲーム", "品牌": "ブランド", "其他": "その他"}
BAD_TERMS = set("""レモン 蜂蜜 蜂蜜レモン 豆腐 納豆 葱 猫 カブト クワガタ 島 湖 無人島 墓場 北方 民間 交易 分家 姓 漁業 石 ガラス 亀 中枢神経系 大海嘯 ライター タバコ スパンコール チャリ 単車 サーフボード トロロ ハバネア エビ カレー ガチョウ アメンボ カマキリ 言語野 脳みそ 腸 鼓膜 クロ シロ タマ ポチ ミオ ミドルネーム ギリシャ語 ラテン語 人名大辞典 地球人 詩人 作曲家 歌手 女子高生 学校 目覚まし時計 死者 魔法少女 魔人 ネクロマンサー ゾンビ ヒポポタマス トリックスター 山田 田中 今川焼き 回転焼き 大判焼き ジャーキー ポニー スーパーマーケット ジョーク ステゴロ テロリスト ブーメラン リーゼント 地獄耳 愛羅武勇 仏恥義理 一筆書き じゃんけん 学位論文 その他 科学 文学 歴史 地理 神話 宗教 数学 哲学 文学ジャンル 楽譜 猫の国 オートマチ子 カピバラ サナダムシ マスターベーション ネズミ講 スイーツ 若手漫才日本一決定戦 民主党 猫 ジャム カシス バイエルン カタコンベ オココト星人 時雨 著作権 固有名詞 黄金 白銀 メノウ 白檀 鋼 針金 石碑 粘土板 結縄 火薬 ドリル ドーナツ ピーマン マタタビ 朝鮮人参 Tシャツ ふんどし ミサンガ 自動二輪 広告 超音波破壊砲 電磁パルス 霊長類 瀉血 地衣類 翼竜 三枝""".split())
TERM_KIND = {"その他", "科学", "文学", "歴史", "地理", "神話", "宗教", "人物", "音楽", "映像", "ゲーム", "ブランド", "明言", "推測", "蓋然性高"}


def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", "replace")


def jl(p: Path, with_meta: bool = False):
    out = []
    for l in rd(p).splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if isinstance(r, dict) and r.get("_meta"):
            if with_meta:
                out.append(r)
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


def call_llm(prompt: str, max_tokens: int = 2200, temperature: float = 0.3) -> str:
    body = json.dumps({
        "model": CFG["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(
        CFG["base_url"] + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + CFG["api_key"]},
    )
    for i in range(8):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode())
            c = d["choices"][0]["message"]["content"]
            if c and c.strip():
                return c
        except Exception as e:
            body_e = ""
            if hasattr(e, "read"):
                try:
                    body_e = e.read().decode("utf-8", "replace")[:240]
                except Exception:
                    pass
            print(f"  llm retry {i}: {type(e).__name__} {e} body={body_e}", flush=True)
            time.sleep(5 * (2 ** i))
    return ""


def _balance_repair(t: str) -> str:
    stack = []
    in_s = False
    esc = False
    for ch in t:
        if in_s:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_s = False
            continue
        if ch == '"':
            in_s = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
    t = t.rstrip()
    if in_s:
        t += '"'
    t = t.rstrip(",")
    for close in reversed(stack):
        t += close
    return t


def parse_json_lenient(text: str):
    i = text.find("{")
    if i < 0:
        return None
    t = text[i:]
    t = re.sub(r",\s*([}\]])", r"\1", t)
    for cand in (t, _balance_repair(t)):
        try:
            obj, _end = json.JSONDecoder().raw_decode(cand, 0)
            return obj
        except json.JSONDecodeError:
            continue
    j = t.rfind("}")
    if j > 0:
        try:
            return json.loads(t[:j + 1])
        except json.JSONDecodeError:
            return None
    return None


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[#*_`>|]+", "", s)
    return re.sub(r"\s+", "", s)


ENT_LEDGER_RUN = "20261119T2042_l1en"

def load_entity_names() -> set:
    names = set()
    for rd in sorted((L1 / "runs").iterdir()):
        if not (rd.is_dir() and "_l1en" in rd.name and (rd / "entities").is_dir()):
            continue
        for pp in (rd / "entities").glob("*.md"):
            m = re.search(r'^term:\s*"?([^"\n]+)"?', pp.read_text(encoding="utf-8"), re.M)
            if m:
                t = m.group(1).strip()
                if len(t) >= 2:
                    names.add(t)
    return names

ENT_NAMES = load_entity_names()


PROMPT = """あなたは実況 Wiki 編集者です。『ゆらぎの神話』関連 BBS スレッド{UNIT}「{TITLE}」の投稿 {LO}〜{HI}（ref は YuragiWiki 原文アンカー）をすべて読み、創作的記述が**実世界の対象を命名源・概念・ジャンル・体系・比喩・制度・作品・人名・地名・ブランド・用語として参照している箇所**（allusion/analogy）を全件洗い出してください。
対象（scope）: 作品名（小説・漫画・アニメ・ゲーム・曲・映画）、実在の人名（作者・音楽家・武将・宗教者・芸人など、命名の由来・言及として機能するもの）、実在地名・国家・遺跡・地形（命名・舞台参照として機能するもの）、宗教・神話体系・教義用語、思想・学術の概念や理論、文化制度・風俗・ゲーム体系・ジャンル名（TRPG・麻雀・漫才・特撮など）、ブランド・商品名（実在が明示される言及）、実在の出来事・歴史上の事件。
**実世界参照の判定は原文の明示による: 実世界に同名の姓・人名・ブランド・商品名・書名らしきものがあるだけでは創作的命名であり対象外（例: 貴族【坂本】は作中人物の命名であって実在の坂本氏を引用していない）。原文が実世界の対象を明示的に指している箇所だけを allusion として出す: 実在作品名+作者/媒体の提示（「THIRD EXCALIBURってゲーム」「吉本ばななの作品」）、実在書物の書誌引用（「沖浦和光『陰陽師の原像』などを参照のこと」）、特定の有名実在個人・作品名の作中同一性・系譜・比較への使用（「芦屋道満の流れを汲む」「俺的桃太郎」）、実在の出来事・制度・学術概念・ジャンル名（TRPG・麻雀等）の説明を伴う言及。一般姓・ありふれた名（坂本・鈴木・山田・マイケル型）は命名素材の創作。usage に「〜を想起させる」「原文に対応の明示はない」と書かねばならない場合はその item を出すな（＝外部知識捏造）。confidence=推測 は、同一文脈に実世界対象の明示がある場合（命名の類似・言い換え）だけ。**
対象外（必ず除外）:
- 場面に登場するだけの**一般名詞**（実世界の固有名を持たない物・動物・植物・食べ物・身体部位・自然物: レモン・猫・島・貝・石・脳みそ・ガチョウ 等）。実在のブランド・商品名・作品名が比喩・言及として使われている場合は対象側だが、作中の命名素材に借用しているだけは対象外（上記の明示基準）。
- ファンタジー系の一般名詞（悪魔・魔法・魔法少女・ネクロマンサー・ゾンビ 等、実世界の個別対象ではないもの）
- 創作由来の造語・自作の固有名詞
- 実世界と同名の姓・人名を**作中の命名に借用しているだけ**の箇所（貴族【坂本】・山田太郎 型: 原文に実世界対象への明示がなく、作中創作として使われている）
- 話題・語句そのもの（創作内容の要約は不要）
- 作中の引用文献・書誌形式（『作中書名』・作中著者名・「〜より引用」）は、実世界で著名な実在書物・実在人物と明白に判断できる場合だけ対象。判断できないものは出さない
対象名（term）の書き方: 実世界対象の固有名を最短形で。kind ラベル名（科学・その他等）を term にしない。同一対象は 1 項目に統合し、引用は 1 項目に複数可。
confidence: 明言 = 原文が対象を明示（名前を挙げる・作品名を明記）。推測 = 名前が近い・構造が似る等の類似。蓋然性高 = 明言に準じる明示（固有名がそのまま使われ命名源が明白な場合）。
usage ルール（最重要）: **引用の文脈における対象の機能を日本語 20〜60 字で記述する（原文に準拠）。原文に明記がない実世界帰属（X 氏は Y の作者・Z を想起・出典は Y）を外部知識で補わない。明言されていない対応は「原文に対応の明示はない」と書く。**
引用 q は原文逐語（100 字以内）。ref は引用した投稿（投稿番号 1 つ）。
JSON のみで出力（説明文禁止・1 行のコンパクト JSON・インデント改行禁止）:
{{"items": [{{"term": "対象名", "kind": "神話|宗教|文学|音楽|映像|ゲーム|歴史|地理|科学|人物|ブランド|その他", "confidence": "明言|推測|蓋然性高", "usage": "引用文脈における機能（原文準拠）", "quotes": [{{"ref": "{UNIT}:N", "q": "逐語引用"}}]}}]}}
対象が 1 つも見つからない場合は {{"items": []}} と出力。
作中名詞（実体台帳登録済み＝作中創作対象なので対象外。これらの名前は allusion として出さないこと）: {LEDGER}
{s_struct}
--- 本文（{LO}〜{HI}） ---
{BODY}"""


def unit_dir(uid: str) -> tuple[Path, dict]:
    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    for u in jl(L0 / "runs" / latest / "units.jsonl"):
        if u["unit_id"] != uid:
            continue
        if u["source"] == "jbbs":
            return RAW / u["raw_path"].rsplit("/", 1)[0], u
        if u["source"] == "mixi":
            return RAW / "mixi/373088" / u["title"], u
        return RAW / "hatena_flicker", u
    raise KeyError(uid)


def mech_gate(uid: str, item: dict, posts: dict) -> tuple[dict, str]:
    term = (item.get("term") or "").strip()
    kind = KIND_FIX.get(item.get("kind") or "", item.get("kind") or "")
    if kind not in KINDS:
        kind = "その他"
    usage = (item.get("usage") or "").strip()
    if not term or not usage:
        return item, "DROP:EMPTY"
    EXPLICIT = ("実在", "命名", "喩", "比喩", "俗称", "名称", "制度", "現象", "概念", "技法", "髪型", "料理", "菓子", "術語", "用語", "昔話", "神話体系", "文化現象", "ジャンル")
    if term in BAD_TERMS and not any(w in usage for w in EXPLICIT):
        return item, "DROP:GENERIC"
    if term in TERM_KIND and not any(w in usage for w in EXPLICIT):
        return item, "DROP:TERM_IS_KIND"
    if len(term) > 40:
        return item, "DROP:TERM_LONG"
    if "架空" in usage and "実在" not in usage and not any(w in usage for w in EXPLICIT):
        return item, "DROP:FICTION"
    if ("原文に対応の明示はない" in usage and "明示的" not in usage) or ("想起させる" in usage and "明示" not in usage):
        return item, "DROP:EXTERNAL_KNOWLEDGE"
    if re.search(r"原文に明示.{0,12}ない", usage):
        return item, "DROP:EXTERNAL_KNOWLEDGE"
    if re.search(r"実在の?(素材|食品|食料|道具|武器|乗り物|乗物|衣類|衣服|装飾品|建材|貴金属|宝石|木材|化学物質|成分|工具)", usage) and len(term) <= 4 and term not in ENT_NAMES:
        return item, "DROP:OBJ"
    if len(usage) < 12:
        return item, "DROP:USAGE_SHORT"
    cn = [c for c in term + usage if c in CN]
    if cn:
        return item, "DROP:CN_CHAR:" + "".join(cn[:3])
    keep = []
    for q in item.get("quotes", []):
        ref, quote = q.get("ref", ""), q.get("q", "")
        if not ref.startswith(uid + ":"):
            continue
        try:
            pno = int(ref.split(":")[1])
        except ValueError:
            continue
        body = posts.get(pno)
        if body is None:
            continue
        if len(quote) > 130:
            continue
        segs = [s for s in re.split(r"…+|\.\.\.+|⋯+", quote) if s.strip()]
        nbody = norm(body)
        if all(norm(s) in nbody for s in segs):
            keep.append({"ref": ref, "q": quote})
    if not keep:
        return item, "DROP:NO_VERBATIM_QUOTE"
    item = {**item, "term": term, "kind": kind, "usage": usage, "quotes": keep[:5]}
    return item, "ok"


def extract_unit(uid: str, rid: str, workers: int, window: int, max_calls: int) -> tuple[str, str]:
    outp = L1 / "runs" / rid / "allusions" / f"{uid}.jsonl"
    if outp.exists():
        return uid, "skip"
    d, meta = unit_dir(uid)
    posts_rows = jl(d / "structured.jsonl")
    posts = {r["post_no"]: r["body"] for r in posts_rows}
    title = meta.get("thread_title", uid)
    nums = sorted(posts)
    windows = [nums[i:i + window] for i in range(0, len(nums), window)]
    windows = windows[:max_calls]
    outp.parent.mkdir(parents=True, exist_ok=True)
    out_items, seen_terms = [], {}
    gate_stats: dict = {}
    for wi, win in enumerate(windows):
        parts = []
        for n in win:
            parts.append(f"【投稿{n}】{posts[n]}")
        prompt = PROMPT.replace("{UNIT}", uid).replace("{TITLE}", title) \
                       .replace("{LO}", str(win[0])).replace("{HI}", str(win[-1])) \
                       .replace("{BODY}", "\n".join(parts)).replace("{LEDGER}", "、".join([n for n in sorted(ENT_NAMES) if n in "\n".join(parts)][:60]))
        raw = call_llm(prompt, max_tokens=2600)
        data = parse_json_lenient(raw)
        items = (data or {}).get("items", []) if isinstance(data, dict) else []
        for it in items:
            if not isinstance(it, dict):
                continue
            it2, st = mech_gate(uid, it, posts)
            keyg = st.split(":")[0]
            gate_stats[keyg] = gate_stats.get(keyg, 0) + 1
            if st != "ok":
                with outp.parent.joinpath("gate_drops.jsonl").open("a", encoding="utf-8") as fd:
                    fd.write(json.dumps({"uid": uid, "win": wi + 1, "gate": st, "term": it2.get("term", ""),
                                         "usage_head": str(it2.get("usage", ""))[:80],
                                         "usage": str(it2.get("usage", ""))[:240],
                                         "quote": str(it2.get("quote", ""))[:90],
                                         "ref": str(it2.get("ref", ""))}, ensure_ascii=False) + "\n")
                continue
            key = norm(it2["term"]).replace("・", "").replace("・", "").replace("・", "")
            if key in seen_terms:
                prev = seen_terms[key]
                refs = {q["ref"] for q in prev["quotes"]}
                prev["quotes"] += [q for q in it2["quotes"] if q["ref"] not in refs][:5 - len(prev["quotes"])]
                prev["windows"] = prev.get("windows", 1) + 1
                continue
            it2["unit"] = uid
            it2["windows"] = 1
            seen_terms[key] = it2
            out_items.append(key)
        print(f"[{uid}] window {wi + 1}/{len(windows)} posts {win[0]}-{win[-1]} items={len(out_items)} gate={gate_stats}", flush=True)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("a", encoding="utf-8") as f:
        for key in out_items:
            f.write(json.dumps(seen_terms[key], ensure_ascii=False) + "\n")
    return uid, f"ok items={len(out_items)} windows={len(windows)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uids", nargs="+", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--window", type=int, default=100)
    ap.add_argument("--max-calls", type=int, default=30)
    a = ap.parse_args()
    rid = a.run_dir
    (L1 / "runs" / rid).mkdir(parents=True, exist_ok=True)
    log = (L1 / "runs" / rid / "log.txt").open("a", encoding="utf-8")
    log.write(f"=== START {dt.datetime.now().isoformat()} uids={a.uids} ===\n")
    log.flush()
    fails = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for uid, st in ex.map(lambda x: extract_unit(x, rid, a.workers, a.window, a.max_calls), a.uids):
            line = f"{uid} {st}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()
            if st.startswith("ok") or st == "skip":
                pass
            else:
                fails.append((uid, st))
    log.write(f"=== ALLUD-GEN DONE {dt.datetime.now().isoformat()} fails={len(fails)} ===\n")
    log.flush()
    print(f"ALLUD-GEN[{rid}] done fails={len(fails)} {fails}")


if __name__ == "__main__":
    main()

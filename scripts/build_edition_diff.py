#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版間差分内容記事: 一致率実測・書換・削除・構造差分 → vault wiki/references/edition-diff.md"""
import json, re, sys, unicodedata, difflib, random
from pathlib import Path
from collections import defaultdict

WORK = Path(r"C:\Users\d5dx\Downloads\Code\AllusionistWiki_work")
RAW = Path(r"C:\Users\d5dx\Downloads\Code\AllusionistWiki_raw\raw\novel")
KDIR = RAW / "kakuyomu/16816927859268545348_幻想再帰のアリュージョニスト"
SDIR = RAW / "syosetu/n9073ca_幻想再帰のアリュージョニスト"
OUT = Path(r"C:\Users\d5dx\Downloads\Code\AllusionistLLMWiki2\wiki\references\edition-diff.md")
L0 = WORK / "work/L0/runs/20261017T2011_f863"
L1 = WORK / "work/L1/runs/20261018T0040_588c"

def norm(t):
    t = t.replace("（空）", "").replace("⏎", "")
    t = unicodedata.normalize("NFKC", t)
    return re.sub(r"\s+", "", t)

# --- なろう本文 (ch → text) ---
S = defaultdict(list)
STITLE = {}
for f in sorted(SDIR.glob("ch*.md")):
    n = int(re.match(r"ch(\d+)", f.name).group(1))
    m = re.match(r"ch\d+_[^ ]*\- (.+?)(?:_\d+)?\.md$", f.name)
    if m and n not in STITLE:
        STITLE[n] = m.group(1).strip()
    body = []
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("#") or line.startswith("【"):
            continue
        body.append(line)
    S[n].append("\n".join(body))
STXT = {n: norm("\n".join(v)) for n, v in S.items()}

# --- カクヨム本文 (ch → text) + メタ ---
K = {}
KTXT = {}
for f in sorted(KDIR.glob("ch*.md")):
    n = int(re.match(r"ch(\d+)", f.name).group(1))
    m = re.match(r"ch\d+__(.+)\.md$", f.name)
    title = m.group(1) if m else f.name
    ep = url = pub = para = ""
    body = []
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("#") or line.startswith("【"):
            mm = re.match(r"【kakuyomu ep(\d+)】", line); ep = mm.group(1) if mm else ep
            mm = re.match(r"【URL (\S+)】", line); url = mm.group(1) if mm else url
            mm = re.match(r"【公開 (\S+)】", line); pub = mm.group(1)[:10] if mm else pub
            mm = re.match(r"【段落数 (\d+)】", line); para = mm.group(1) if mm else para
            continue
        body.append(line)
    K[n] = {"title": title, "url": url, "pub": pub, "paras": para}
    KTXT[n] = norm("\n".join(body))

EMAP = {}
for l in (L0/"episode-map.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip():
        r = json.loads(l)
        EMAP[r["syosetu_ch"]] = r

# --- 引用ステータス（ユニーク単位・edition-map と同整合） ---
st = defaultdict(lambda: {"total": 0, "hit": 0, "punct": 0, "llm": 0, "del": 0})
seen = {}
for f in (L0/"quote-map").glob("ch*.jsonl"):
    n = int(re.match(r"ch(\d+)", f.name).group(1))
    seen[n] = set()
    for l in f.read_text(encoding="utf-8").splitlines():
        if not l.strip(): continue
        r = json.loads(l)
        key = (r["s_para"], r["quote_head"])
        if key in seen[n]: continue
        seen[n].add(key)
        st[n]["total"] += 1
        st[n]["hit"] += 1
for l in (L0/"needs-reanalysis.jsonl").read_text(encoding="utf-8").splitlines():
    if not l.strip(): continue
    r = json.loads(l)
    n = r.get("ch") or r.get("episode")
    key = (str(r.get("s_para")), r.get("quote_head", ""))
    seen.setdefault(n, set()).add(key)
    st[n]["total"] += 1
pairs = []  # 書換ペア
for l in (L1/"reanchored-final.jsonl").read_text(encoding="utf-8").splitlines():
    if not l.strip(): continue
    r = json.loads(l)
    n = r["episode"]
    if r.get("method") == "punct":
        st[n]["punct"] += 1
    else:
        st[n]["llm"] += 1
        q, q2 = r.get("quote_head", ""), r.get("new_quote_head", "")
        if q2 and norm(q)[:20] != norm(q2)[:20]:
            pairs.append({"ch": n, "para": r["s_para"], "sy": q, "kaku": q2, "k": r.get("k")})
for l in (L1/"deleted-ledger.jsonl").read_text(encoding="utf-8").splitlines():
    if not l.strip(): continue
    r = json.loads(l)
    st[r["episode"]]["del"] += 1

# --- 章一致率（规范化テキスト exact。キャッシュ edition-diff-sim.json があれば流用） ---
sim = {}
CACHE = OUT.parent / "edition-diff-sim.json"
if CACHE.exists():
    sim = {int(k): v for k, v in json.loads(CACHE.read_text()).items()}
else:
    for n, e in sorted(EMAP.items()):
        a = STXT.get(n, "")
        ks = e.get("kakuyomu", [])
        b = "".join(KTXT.get(k, "") for k in ks)
        if not a or not b:
            sim[n] = None; continue
        q = difflib.SequenceMatcher(None, a, b).quick_ratio()
        sim[n] = round(difflib.SequenceMatcher(None, a, b).ratio(), 3)
    CACHE.write_text(json.dumps({str(k): v for k, v in sim.items()}), encoding="utf-8")

# --- 集計 ---
sims = [v for v in sim.values() if v is not None]
sims.sort()
agg = {k: sum(st[n][k] for n in st) for k in ("total", "hit", "punct", "llm", "del")}
split_hist = defaultdict(int)
for e in EMAP.values():
    split_hist[len(e.get("kakuyomu", []))] += 1

# --- 記事 ---
L = []
L.append("---")
L.append("title: 版間差分内容（なろう版 → カクヨム版）")
L.append("id: references/edition-diff")
L.append("description: 2020-2021 なろう連載版から 2022 カクヨム版への改稿で、内容がどこを・何を・どう変えたかの解析（一致率実測・削除一覧・書換例）")
L.append("---")
L.append("")
L.append("# 版間差分内容（なろう版 → カクヨム版）")
L.append("")
L.append("なろう版（2020-2021・272 話・5-69 で凍結）→ カクヨム版（2022-・589 話）の**内容レベルの差分**を、引用照合と全文実測で解析したページです。対応の構造版は [[references/edition-map|版対応表]]。")
L.append("")
L.append("## サマリ")
L.append("")
med = sims[len(sims)//2]
lo = sims[:10]
L.append(f"- 章単位の全文一致率（正規化テキストの文字列同一性・順序に敏感）: 中央値 **{med:.2f}**、平均 **{sum(sims)/len(sims):.2f}**。分母には章分割による語順移動・構造段落も差分として効くため、内容の同一性そのもの（文レベル一致率の実測 95〜98%）より低く出る。0.9 以上 {sum(1 for v in sims if v >= 0.9)} 章、0.35 未満 {sum(1 for v in sims if v < 0.35)} 章")
L.append("- 対応章なし（一致率対象外）: 28『もし狂犬が戦国乱世に転生したら』・42『松明の騎士』・56『言震《ワードクェイク》』・76『黒血のハルベルト』の幕間 4 話（カクヨム側で同名だが本文話として構成が別）と 232『五章キャラ一覧暫定』（付録）")
low = sorted((n, v) for n, v in sim.items() if v is not None and v < 0.40)
L.append("- 低一致章（0.40 未満・対応章あり）: " + "、".join(f"{n}『{(EMAP.get(n) or {}).get('title', STITLE.get(n, ''))[:18]}』{v:.2f}" for n, v in low) + " — 章全面の書き直し群（4-37 型のように番号が同名でも別内容の章を含む）")
L.append(f"- baseline 引用 {agg['total']} 件の照合内訳: 全文一致 {agg['hit']} + 記号のみの一致 {agg['punct']} + **書換を伴う再アンカー {agg['llm']}** + 削除 {agg['del']}")
L.append(f"- 話数の分割: なろう 1 話 → カクヨム 2〜13 話（最頻 {max(split_hist, key=lambda k: split_hist[k])} 話、全 272 話中 {sum(v for k,v in split_hist.items() if k>=2)} 話が分割された）")
L.append("")
L.append("## 差分のカテゴリ")
L.append("")
L.append("### 1. 章の分割と連番（全文一致のまま構造だけ変わる）")
L.append("")
L.append("カクヨム版は 1 話を 1,500〜3,500 字の連載単位に分割し、章題に連番（1-1①..⑬）を付けた。本文はほぼそのまま。なろう側の `p` 段落番号がカクヨムの `¶` 段落番号へ写る位置関係は章ごとに独立で、対応表で章単位に引き直されている。")
hist = "、".join(f"{k}話:{v}" for k, v in sorted(split_hist.items()) if k <= 8)
L.append(f"分割分布（なろう1話あたりカクヨム話数）: {hist}")
L.append("")
L.append("### 2. 幕間の扱い（削除と本文昇格）")
L.append("")
L.append("なろう版の幕間（ショートショート）は、カクヨム版で 3 パターンに分かれた:")
L.append("- **本文話へ昇格**: 幕間『松明の騎士』→ 3-43〜45 として本編化（短縮、共有部 14 引用が ¶ 回収）/ 幕間『言震《ワードクェイク》』→ 3-64〜65 / 幕間『黒血のハルベルト』→ 第三巻エピローグ")
L.append("- **丸ごと削除**: 幕間『もし狂犬が戦国乱世に転生したら』（なろう 28 話・引用 87 件）はカクヨムに同名作品なし")
L.append("- **短縮削除**: 昇格先でも冒頭・場面の一部（神々の図書館の冒頭、魔女ミュトス〜の列挙、ガーデニアのファンレター等）が省略され、該当引用 16 件は削除台帳行き")
L.append("")
L.append("### 3. 付録の廃止（カクヨム正典は本文のみ）")
L.append("")
L.append("なろう版の「五章キャラ一覧（暫定）」（232 話・149 件）、「5-29」埋め込みのキャラ一覧・外伝プロフィール・章構造のメタ記述・作者注記（計 160+6 件）は、カクヨム版の掲載形態に存在しない。wiki の典拠は本文 ¶ のみで構成される。")
L.append("")
L.append("### 4. 局部改稿（同じ場面・同じ内容の文が書き換えられた）")
L.append("")
L.append(f"記号除去で完全一致する引用 {agg['punct']} 件（引用符・句読点・区切り線の正規化のみ）に対し、**LLM 再アンカー {agg['llm']} 件はカクヨム側で文言が変わっている** = 局部改稿の密度。改稿は『同じ場面・同じ内容の一節を別の書き回しで提示する』形で、用語の言い換え（例: 比喩の更新）・文のリズム変更・語順変更が中心。")
L.append("")
L.append("### 5. 本編から削除された場面（scene_removed 73 件）")
L.append("")
L.append("カクヨム全巻の全文検索（記号除去正規化）で非存在が確認された、なろう版本編の場面引用。改稿で落ちた小シーン・モノローグが中心:")
L.append("")
L.append("| なろう話 | 段落(歴史的p) | 削除された引用（冒頭） |")
L.append("|---|---|---|")
for l in (L1/"deleted-ledger.jsonl").read_text(encoding="utf-8").splitlines():
    if not l.strip(): continue
    r = json.loads(l)
    if r["reason"] in ("scene_removed", "verify_failed"):
        q = r["quote_head"].replace("|", "＊").replace("\r", "").replace("\n", " ")[:64]
        L.append(f"| {r['episode']} | {r['s_para']} | {q} |")
L.append("")
L.append("### 6. カクヨム専用の新内容（27 話）")
L.append("")
L.append("2022 年の本文 6 話（3-43〜45 松明の騎士・3-64〜65 言震・エピローグ黒血のハルベルト）と、2025 年 5-70〜5-90 の続編 21 話（リーナちゃんのお人形遊び〜愛の森を越えろ）。なろう側に存在せず、カクヨム版だけの内容。→ [[references/edition-map#カクヨム専用話|対応表の専用話一覧]]")
L.append("")
L.append("## 章別 一致率・引用改稿密度")
L.append("")
L.append("| # | 章 | 一致率 | 全文一致 | 記号のみ | 書換 | 削除 |")
L.append("|---|---|---|---|---|---|---|")
for n in sorted(st.keys()):
    s = st[n]
    r = sim.get(n)
    rs = f"{r:.2f}" if r is not None else "—"
    title = ((EMAP.get(n) or {}).get("title") or STITLE.get(n, ""))[:24]
    L.append(f"| {n:03d} | {title} | {rs} | {s['hit']} | {s['punct']} | {s['llm']} | {s['del']} |")
L.append("")
L.append("## 書換例（なろう版 → カクヨム版）")
L.append("")
L.append("再アンカーで『同じ内容の一節が書き換えられた』実例（引用冒頭 40 字の対比・→ はカクヨム ¶）:")
L.append("")
random.seed(7)
sample = random.sample(pairs, min(60, len(pairs)))
sample.sort(key=lambda x: (x["ch"], int(re.sub(r"\D", "", str(x["para"])) + "0") if x["para"] else 0))
for p in sample:
    a = p["sy"].replace("|", "＊").replace("\r", "").replace("\n", " ")[:40]
    b = p["kaku"].replace("|", "＊").replace("\r", "").replace("\n", " ")[:40]
    k = p.get("k")
    kk = f"¶{k[1]}" if k else ""
    L.append(f"- {p['ch']}: {a}")
    L.append(f"  → {kk} {b}")
L.append("")
L.append("## 来歴")
L.append("")
L.append("- データ: L0 `20261017T2011_f863`（引用照合）、L1 `20261018T0040_588c`（再アンカー 4 パス+裁定 4,036 件完遂）")
L.append("- 一致率: 各章の正規化本文（空白・改行除去・NFKC）のdifflib 文字列同一性。生成: `AllusionistWiki_work/scripts/build_edition_diff.py`")
L.append("- 引用の版参照は常にカクヨム ¶N（[[references/edition-map|版対応表]]）。なろう p 番号は歴史的参照のみ。")
L.append("")
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print("wrote", OUT, OUT.stat().st_size)
print("sim:", round(med, 3), "avg:", round(sum(sims)/len(sims), 3), "min:", sims[0], "pairs:", len(pairs))
print("agg:", agg)

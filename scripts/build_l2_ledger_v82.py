"""v8.2第二段: 一般語・代名詞・記述aliasの決定論是正（STRATEGY-normalization-v8.md §5 準拠）。
usage: python build_l2_ledger_v82.py <base_run_id> <out_run_id>
base=v8clean 等の台帳 run。出力: entities.json / review-queue.jsonl / audit/changes.json / run.json
"""
import json, io, os, re, sys, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
L2 = os.path.join(HERE, "..", "work", "allusionist_v2", "L2")
RUNS = os.path.join(L2, "runs")

base_id, out_id = sys.argv[1], sys.argv[2]
base_dir = os.path.join(RUNS, base_id)
out_dir = os.path.join(RUNS, out_id)
assert os.path.isdir(base_dir), base_dir
os.makedirs(os.path.join(out_dir, "audit"), exist_ok=True)

ents = json.load(io.open(os.path.join(base_dir, "entities.json"), encoding="utf-8"))
wrap = isinstance(ents, dict)
elist = ents.get("entities", list(ents.values())) if wrap else ents

HONORIFIC = ("くん", "殿", "さん", "ちゃん", "君", "様")
# v8 一般語 + G1 原因1・4 の拡張（裸の語のみ一致。敬称付き実名・タイトル複合は対象外）
GENERIC = {
    "アバター", "古代文字", "霊媒", "王", "幼馴染", "幼馴染み", "お姫様", "姫",
    "少女", "少年", "女性", "男性", "男", "女", "青年", "舞い手", "舞い手たち",
    "まことの名", "名", "亜竜人の少女", "店員", "曲芸団", "動物", "人狼",
    "妖精", "闇妖精", "巨人族", "小鬼族", "idel", "主人公",
    # G1 追加: 概念・一般語
    "陰陽", "両儀", "共通", "使い魔", "ペット", "呪文", "呪文", "呪符", "炸撃",
    "爆撃", "爆発", "類推", "類推", "立体幻像", "立体幻像の窓", "呪文使い",
    "魔法使い", "魔術師", "召喚士", "占影術", "心話", "裁定神", "権能", "宝珠",
    "レガリア", "聖絶", "象徴", "魔将", "大魔将", "守護", "眷族", "子孫",
    "生存者", "難民", "部隊", "軍団", "軍", "国防軍", "神殿", "教会", "修道院",
    "村", "街", "宮", "騎士", "女王", "王妃", "皇子", "神", "天使", "使徒",
    "司祭", "僧正", "僧", "賢者", "賢人", "勇者", "英雄", "浪人", "剣士",
    "武人", "職人", "商人", "使用人", "侍女", "護衛", "審判役", "審判", "使者",
    "使節団", "観測者", "戦士", "兵士", "元軍人", "父上", "店主", "店員さん",
    "貴婦人", "老女", "老婆", "老人", "坊や", "娘", "御者", "船长", "船長",
    "总帥", "総帥", "師", "弟子", "見習い", "隊長", "首領", "支配者", "造物主",
    "主", "神主", "神官", "魔女", "魔法", "呪力", "呪具", "魔導書", "呪紋",
    "邪視", "魔術", "魔法陣",
    # G2 追加: 親族・場所・術語・職業
    "地上", "大神院", "魔導書", "杖", "門", "ゲート", "吐息", "波濤の吐息",
    "姉妹", "母", "父", "お姉様", "お師様", "兄", "姉", "弟", "妹", "親",
    "子", "親族", "刺客", "傭兵", "探索者", "請負人", "戦闘", "破壊", "秩序",
    "混沌", "正義", "悪意", "記憶", "夢", "物語", "神話", "伝承", "歌",
    # 代名詞
    "俺", "私", "僕", "我", "某", "彼", "彼女", "あの人",
    # G3 追加: 列挙・称号・動物一般語・变体語
    "太陽", "太陰", "少陽", "少陰", "八卦", "太極",
    "虎", "狼", "蛇", "牛", "蝶", "蝙蝠", "鼠", "猿", "鳥", "烏",
}
# G3 原因対策: 称号で終わる役割句 / シナモリアキラ变体語
ROLE_SUFFIX = ("長", "団長", "総団長", "頭目", "頭", "守護者", "使い", "師匠",
               "戦士", "拳闘士", "工匠", "使者", "使用人", "侍女", "護衛",
               "支配者", "審判", "司祭", "女王", "王妃", "皇子", "王")
VARIANT_TOKENS = ("姫", "大蛇", "幻姿", "原型", "プロトタイプ", "王", "之子",
                  "幼姫", "カイン", "グレンデルヒ", "オルヴァ", "トロル",
                  "絡新婦", "火車", "鵺", "塗壁", "軍勢", "犬頭")
# v8.5: G4 原因対策（メタalias・記述句・部全体・一般語概念）
GENERIC |= {"語り手", "語り", "主人公", "召喚", "コール", "創造", "クラフト",
            "巨人", "嵐", "浄界", "浄土", "楽園", "再生", "再成", "暴力",
            "身体性", "物語性", "未来", "前世", "死亡", "生命",
            "エントリー", "参戦", "参加", "少女", "牛首族", "肉塊", "魔魚",
            "宝石", "翼", "翅", "生首", "腕", "声", "炎", "真名", "種族名"}
DESC_CONNECTIVES = ("という", "とは", "である", "による", "を指す")
PART_SUFFIXES = ("本館", "別館", "本殿", "上層", "下層", "別邸", "外郭",
                 "内郭")
PRON_RE = re.compile(r"^(俺|私|僕|我|某|俺様|彼|彼女)(（|\(|$)")
PAREN_RE = re.compile(r"^(?P<outer>.+?)[（(](?P<inner>.+)[)）]$")
SLASH_RE = re.compile(r"[/／]")
BARE_RE = re.compile(r"^[（(].+[)）]$")
DESC_RE = re.compile(r"[【（()「]")

def is_generic(nm: str) -> bool:
    core = re.sub(r"[（(].+?[)）]", "", nm).strip()
    return core in GENERIC or nm in GENERIC

def strip_title(nm: str) -> str:
    return re.sub(r"^【[^】]*】", "", nm).strip()

def is_descriptive(nm: str) -> bool:
    return len(nm) >= 14 or (len(nm) >= 12 and DESC_RE.search(nm))

# 既知の正式名集合（別实体括弧注記の検出用）
NAMES = set()
for e in elist:
    if e.get("canonical"):
        NAMES.add(e["canonical"])
    if e.get("primary_promoted"):
        NAMES.add(e["primary_promoted"])

changes = collections.Counter()
queue = []
for e in elist:
    keep = []
    for a in e.get("aliases", []):
        if isinstance(a, str):
            a = {"name": a, "source": "代表名", "confidence": "高", "reason": "", "cites": []}
        nm = a.get("name", "")
        src = a.get("source", "")
        reason = str(a.get("reason", ""))
        if nm == e.get("canonical"):
            keep.append(a)
            continue
        drop = None
        if src == "未根拠":
            drop = "unmerged:無根拠"
        elif src == "v4-章共起監査":
            drop = "unmerged:共起監査は要人手検証"
        elif src in ("v2-裁定", "v3-裁定", "v8-括弧分解") and (
                "分離証拠" in reason or "別個のキャラクター" in reason
                or "明確に区別" in reason):
            drop = "unmerged:分離証拠"
        elif src in ("v2-裁定", "v3-裁定") and a.get("confidence") == "蓋然性高":
            drop = "unmerged:蓋然性裁定"
        elif src in ("v2-裁定", "v3-裁定", "v8-括弧分解") and re.search(
                r"可能性|と見られ|推定", reason):
            drop = "unmerged:推測根拠"
        elif BARE_RE.match(nm) or PAREN_RE.match(nm):
            m = PAREN_RE.match(nm)
            outer, inner = (m.group("outer"), m.group("inner")) if m else ("", nm)
            outer = strip_title(outer)
            inner_clean = re.sub(r"[《《].*?[》》]", "", inner).strip()
            cross = (outer in NAMES and inner_clean in NAMES
                     and inner_clean != e.get("canonical") and outer != e.get("canonical"))
            if cross:
                drop = "label:別实体括弧注記"
            elif outer and outer != e.get("canonical") and len(inner_clean) <= 14 \
                    and not is_generic(outer) and not is_descriptive(outer) \
                    and not SLASH_RE.search(outer) and not BARE_RE.match(outer):
                a2 = dict(a)
                a2["name"] = outer
                a2["source"] = "v8-括弧分解"
                a2["confidence"] = "要検証"
                a2["reason"] = (a.get("reason", "") + " [v8: 括弧注記を分解し本体名へ正規化]")
                if outer not in [k.get("name") for k in keep]:
                    keep.append(a2)
                    changes["alias=括弧注記→本体名正規化"] += 1
                drop = None
            else:
                drop = "label:括弧注記"
        elif SLASH_RE.search(nm):
            drop = "label:スラッシュ複合"
        elif "・" in nm and len(nm) >= 6:
            drop = "label:記述列挙"
        elif ("という" in nm or "とは" in nm) and len(nm) >= 8:
            drop = "label:記述句"
        elif (not PAREN_RE.match(nm)) and len(nm) >= 10 and "の" in nm:
            drop = "label:記述句"
        elif e.get("canonical") and nm.startswith(e["canonical"]) and nm[
                len(e["canonical"]):] in ("本館", "別館", "本殿", "上層",
                                          "下層", "別邸"):
            drop = "label:部全体"
        elif e.get("canonical") and ("アキラ" in e.get("canonical")
                                     or "シナモリアキラ" in e.get("canonical")) \
                and any(t == nm or t.startswith(nm) or t in nm
                        for t in VARIANT_TOKENS if len(nm) >= 4):
            drop = "label:变体参照"
        elif (not PAREN_RE.match(nm)) and "の" in nm and nm.endswith(
                ("男", "少女", "美人", "師匠", "者", "翅", "集団", "達", "娘")):
            drop = "label:記述句"
        elif (not PAREN_RE.match(nm)) and len(nm) >= 3:
            bare_nm = nm.rstrip("".join(HONORIFIC) + "様")
            if bare_nm and bare_nm in NAMES and bare_nm != e.get("canonical"):
                drop = "label:别实体名alias"
        elif any(nm.endswith(suf) and len(nm) > len(suf)
                 and nm[: -len(suf)] not in NAMES
                 and (suf not in ("長", "王", "女王", "王妃", "皇子", "司祭",
                                  "審判", "支配者") or "の" in nm)
                 for suf in ROLE_SUFFIX):
            drop = "label:役割句"
        elif PRON_RE.match(nm):
            drop = "label:代名詞"
        elif is_generic(nm):
            drop = "label:一般語"
        elif is_descriptive(nm):
            drop = "label:記述フレーズ"
        elif src in ("v2-裁定", "v3-裁定") and not a.get("cites"):
            drop = "unmerged:cites無し裁定"
        if drop:
            changes[drop] += 1
            queue.append({"ent": e.get("id"), "canonical": e.get("canonical"),
                          "name": nm, "from": src, "conf": a.get("confidence"),
                          "reason": str(a.get("reason", ""))[:300], "why": drop})
        else:
            keep.append(a)
    e["aliases"] = keep

# primary 是正（v8 手順）+ v8.2 追加: primary が一般語なら实体ごと審査キュー
for e in elist:
    canon = e.get("canonical", "")
    names = [a.get("name") for a in e["aliases"] if a.get("name")]
    prim = None
    if canon.endswith(HONORIFIC) and len(canon) >= 3:
        bare = canon[: -1]
        if bare in names:
            prim = bare
    if prim is None and canon:
        cands = [n for n in names
                 if n != canon and n.startswith(canon) and len(n) > len(canon)
                 and not n.endswith(HONORIFIC) and not PAREN_RE.match(n)
                 and not SLASH_RE.search(n) and not is_generic(n)]
        if cands:
            prim = max(cands, key=len)
    if prim:
        e["primary_promoted"] = prim
        changes["primary昇格"] += 1
    if canon and is_generic(canon):
        e["review_flag"] = "general-primary"
        changes["entity:general-primary審査"] += 1
        queue.append({"ent": e.get("id"), "canonical": canon, "name": canon,
                      "from": "entity", "conf": "要検証",
                      "reason": "primary が一般語表層（概念層への移管判断）", "why": "entity:general-primary"})

json.dump({"schema": "l2-entities/3+v8.2", "generated": datetime.datetime.now().isoformat(),
           "derived_from": base_id, "entities": elist},
          io.open(os.path.join(out_dir, "entities.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
with io.open(os.path.join(out_dir, "review-queue.jsonl"), "w", encoding="utf-8") as f:
    for r in queue:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
io.open(os.path.join(out_dir, "audit", "changes.json"), "w", encoding="utf-8").write(
    json.dumps(dict(changes), ensure_ascii=False, indent=1))
run = {"run_id": out_id, "created": datetime.datetime.now().isoformat(),
       "kind": "ledger-cleanup-v8.2", "derived_from": base_id,
       "spec": "STRATEGY-normalization-v8.md §5",
       "changes": dict(changes), "entities": len(elist), "queue": len(queue)}
io.open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8").write(
    json.dumps(run, ensure_ascii=False, indent=1))
io.open(os.path.join(L2, "latest.txt"), "w", encoding="utf-8").write(out_id + "\n")
print("V82 DONE", dict(changes))
print("entities:", len(elist), "queued:", len(queue))

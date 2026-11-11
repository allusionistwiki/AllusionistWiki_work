"""v8 第一段: 決定論台帳是正（STRATEGY-normalization-v8.md §3 準拠）。
usage: python build_l2_ledger_v8.py <base_run_id> <out_run_id>
base/out は work/allusionist_v2/L2/runs 配下の run ID。
出力: entities.json(是正版) / review-queue.jsonl(降ろした無根拠・ラベル) / audit/changes.json / run.json
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
GENERIC = {
    "アバター", "古代文字", "霊媒", "王", "幼馴染", "幼馴染み", "お姫様", "姫",
    "少女", "少年", "女性", "男性", "男", "女", "青年", "舞い手", "舞い手たち",
    "まことの名", "名", "亜竜人の少女", "店員", "曲芸団", "動物", "人狼",
    "妖精", "闇妖精", "巨人族", "小鬼族", "idel", "主人公",
}
PRON_RE = re.compile(r"^(俺|私|僕|俺様|彼|彼女)\b|^[男女人](（|\()")
PAREN_RE = re.compile(r"^(?P<outer>.+?)[（(](?P<inner>.+)[)）]$")
SLASH_RE = re.compile(r"[/／]")
BARE_RE = re.compile(r"^[（(].+[)）]$")

def is_generic(nm: str) -> bool:
    core = re.sub(r"[（(].+?[)）]", "", nm).strip()
    return core in GENERIC or nm in GENERIC

def strip_title(nm: str) -> str:
    return re.sub(r"^【[^】]*】", "", nm).strip()

changes = collections.Counter()
queue = []
for e in elist:
    keep = []
    for a in e.get("aliases", []):
        if isinstance(a, str):
            a = {"name": a, "source": "代表名", "confidence": "高", "reason": "", "cites": []}
        nm = a.get("name", "")
        src = a.get("source", "")
        if nm == e.get("canonical"):
            keep.append(a)
            continue
        drop = None
        if src == "未根拠":
            drop = "unmerged:無根拠"
        elif BARE_RE.match(nm) or PAREN_RE.match(nm):
            m = PAREN_RE.match(nm)
            outer, inner = (m.group("outer"), m.group("inner")) if m else ("", nm)
            outer = strip_title(outer)
            inner_clean = re.sub(r"[《《].*?[》》]", "", inner).strip()
            # furigana 表記 (outer 名 + 短カタカナ/読み) は outer 本体へ正規化
            if outer and outer != e.get("canonical") and len(inner_clean) <= 14 and not is_generic(outer):
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
        elif PRON_RE.match(nm):
            drop = "label:一般呼称"
        elif is_generic(nm):
            drop = "label:一般語"
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

# primary 是正: 敬称 primary → 素名 / 部分文字列 primary → 上位正式名
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

json.dump({"schema": "l2-entities/3+v8clean", "generated": datetime.datetime.now().isoformat(),
           "derived_from": base_id, "entities": elist} if wrap else
          {"schema": "l2-entities/3+v8clean", "generated": datetime.datetime.now().isoformat(),
           "derived_from": base_id, "entities": elist},
          io.open(os.path.join(out_dir, "entities.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
with io.open(os.path.join(out_dir, "review-queue.jsonl"), "w", encoding="utf-8") as f:
    for r in queue:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
io.open(os.path.join(out_dir, "audit", "changes.json"), "w", encoding="utf-8").write(
    json.dumps(dict(changes), ensure_ascii=False, indent=1))
run = {"run_id": out_id, "created": datetime.datetime.now().isoformat(),
       "kind": "ledger-cleanup-v8", "derived_from": base_id,
       "spec": "STRATEGY-normalization-v8.md §3",
       "changes": dict(changes), "entities": len(elist), "queue": len(queue)}
io.open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8").write(
    json.dumps(run, ensure_ascii=False, indent=1))
io.open(os.path.join(L2, "latest.txt"), "w", encoding="utf-8").write(out_id + "\n")
print("V8-CLEAN DONE", dict(changes))
print("entities:", len(elist), "queued:", len(queue))

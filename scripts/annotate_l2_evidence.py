"""各変換（alias→canonical・親所属・状態判定）に確度・根拠・引用・検証点を付与する検証層。

決定論 post-process（LLM 不使用）。entities.json の aliases を
{name, confidence, source, reason, cites[], verify[]} 構造へ拡張し、
parent には confidence/reason/cites/verify、entity_status には
status_confidence/status_reason/status_verify を付与する。
監査用 conversion-evidence.jsonl を出力（変換全件・人手/機械検証に対応）。

根拠の来源（優先順）:
  代表名   : alias==canonical（事実観測の最多表記）
  v2-裁定  : adjudications_v2.jsonl（decision=alias・confidence/reason）— 全話証拠版
  明言共起 : L1 facts で subject=本名義 かつ object=canonical の同一 fact（¶ 引用）
  v3-裁定  : adjudications_v3.jsonl（alias_of・confidence/reason/quote）
  表記ゆれ : 正規化同一（NFKC・中点/空白除去・括弧注記解析）
  未根拠   : 上記いずれにも当たらない → confidence=要検証＋検証点を記録

Usage: python scripts/annotate_l2_evidence.py <run_id>
"""
import json
import re
import sys
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import (L2_RUNS, L1_INPUT_RUNS, norm_key, load_facts,
                      parse_paren)  # noqa

RUN = sys.argv[1]
OUT = L2_RUNS / RUN
CONF_ORDER = {"蓋然性高": 3, "要検証": 1}


def jl(p):
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def surface_of(v):
    return ((v.get("surface") if isinstance(v, dict) else v) or "").strip()


def cite_of(d):
    ep = d.get("episode")
    m = re.search(r"\d+", str(d.get("paragraph") or ""))
    if ep and m:
        return [ep, int(m.group())]
    return None


def best_by_norm(path, gate=None):
    m = {}
    for d in jl(path):
        for v in d.get("verdicts", []):
            nk = norm_key(v.get("norm", ""))
            if not nk:
                continue
            if gate and not gate(v):
                continue
            cur = m.get(nk)
            if cur is None or CONF_ORDER.get(v.get("confidence"), 0) > \
                    CONF_ORDER.get(cur.get("confidence"), 0):
                m[nk] = v
    return m


def quote_cite(v):
    q = v.get("quote")
    if isinstance(q, list) and len(q) == 2:
        n = re.sub(r"\D", "", str(q[1]))
        return [q[0], int(n) if n else 0]
    return None


def main():
    ent_path = OUT / "entities.json"
    doc = json.loads(ent_path.read_text(encoding="utf-8"))
    ents = doc["entities"]

    v2 = best_by_norm(OUT / "adjudications_v2.jsonl",
                      lambda v: v.get("decision") == "keep")
    v3all = best_by_norm(OUT / "adjudications_v3.jsonl")
    v3alias = {k: v for k, v in v3all.items() if v.get("category") == "alias_of"}

    cooc = collections.defaultdict(list)   # (subj_norm, obj_norm) → cites
    first_cite = {}                        # norm → 初出引用
    for d in load_facts(L1_INPUT_RUNS):
        s = surface_of(d.get("subject"))
        o = surface_of(d.get("object"))
        cite = cite_of(d)
        if not s or not cite:
            continue
        sn = norm_key(s)
        if sn not in first_cite:
            first_cite[sn] = cite
        if o:
            k = (sn, norm_key(o))
            if len(cooc[k]) < 3:
                cooc[k].append(cite)

    stats = collections.Counter()
    conf_dist = collections.Counter()
    rows = []

    for e in ents:
        canon = e["canonical"]
        cn = norm_key(canon)
        new_aliases = []
        for a in e.get("aliases", []):
            name = a["name"] if isinstance(a, dict) else a
            nk = norm_key(name)
            rec = {"name": name}
            if name == canon:
                fs = e.get("first_seen") or {}
                rec.update(
                    confidence="高", source="代表名",
                    reason="台帳代表表記（事実観測の最多表記・%d 件）" % e.get("fact_total", 0),
                    cites=[[fs["ch"], fs.get("para")]] if fs.get("ch") else [],
                    verify=[])
            elif nk in v2:
                v = v2[nk]
                rec.update(
                    confidence=v.get("confidence", "要検証"), source="v2-裁定",
                    reason=v.get("reason", ""),
                    cites=[first_cite[nk]] if nk in first_cite else [],
                    verify=([] if v.get("confidence") == "蓋然性高"
                            else ["裁定が要検証: 引用全文と両名義の全話使用状況の人手確認が必要"]))
            elif (nk, cn) in cooc:
                rec.update(
                    confidence="明言", source="明言共起",
                    reason="同一事実で本名義が %s を指す主語として観測" % canon,
                    cites=cooc[(nk, cn)],
                    verify=["根拠は同一文の共起: 本名義が他話で単独主語として使われる例の確認"])
            elif nk in v3alias:
                v = v3alias[nk]
                q = quote_cite(v)
                rec.update(
                    confidence=v.get("confidence", "要検証"), source="v3-裁定",
                    reason=v.get("reason", ""), cites=[q] if q else [],
                    verify=["v3 裁定: 両名義の全話使用状況確認が未実施"])
            elif nk == cn:
                rec.update(
                    confidence="表記一致", source="表記ゆれ",
                    reason="正規化同一（NFKC・中点/空白除去）による表記ゆれ",
                    cites=[first_cite[nk]] if nk in first_cite else [], verify=[])
            else:
                main_name, paren = parse_paren(name)
                if paren and norm_key(main_name) == cn:
                    rec.update(
                        confidence="表記一致", source="表記ゆれ",
                        reason="括弧注記（%s）付きの同一表記" % paren,
                        cites=[first_cite[nk]] if nk in first_cite else [], verify=[])
                else:
                    rec.update(
                        confidence="要検証", source="未根拠",
                        reason="裁定・共起の直接根拠なし",
                        cites=[first_cite[nk]] if nk in first_cite else [],
                        verify=["統合の可否: 両名義の全話使用状況の確認が必要",
                                "v1 機械群の名残の可能性がある"])
            new_aliases.append(rec)
            stats[rec["source"]] += 1
            conf_dist[rec["confidence"]] += 1
            if name != canon:
                rows.append({"alias": name, "entity_id": e["id"], "canonical": canon,
                             "kind": e.get("kind"), "confidence": rec["confidence"],
                             "source": rec["source"], "reason": rec["reason"],
                             "cites": rec["cites"], "verify": rec["verify"]})
        e["aliases"] = new_aliases

        p = e.get("parent")
        if p:
            v = v3all.get(norm_key(canon))
            if v:
                p["confidence"] = v.get("confidence", "要検証")
                p["reason"] = v.get("reason", "")
                q = quote_cite(v)
                if q:
                    p["cites"] = [q]
                p["verify"] = ["所属（側面）の妥当性: 本名義が他話で独立实体として扱われる例の確認"]
                stats["parent-根拠付与"] += 1
        st = e.get("entity_status")
        if st:
            v = v3all.get(norm_key(canon))
            if v:
                e["status_confidence"] = v.get("confidence", "要検証")
                e["status_reason"] = v.get("reason", "")
                e["status_verify"] = (["固有名詞・役職として固着した用法の逆例確認"]
                                      if st == "generic"
                                      else ["未裁定部分: 全話検索による实体性の再判定"])
                stats["status-根拠付与"] += 1

    doc["schema"] = "l2-entities/5"
    doc["count"] = len(ents)
    ent_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "conversion-evidence.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")

    print("conversions annotated:", len(rows))
    print("by source:", dict(stats))
    print("by confidence:", dict(conf_dist))
    print("open verification points:", sum(1 for r in rows if r["verify"]))
    print("=== ANNOTATE L2 EVIDENCE DONE ===")


if __name__ == "__main__":
    main()

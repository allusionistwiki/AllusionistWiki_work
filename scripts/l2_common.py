"""L2 共通ヘルパ（paths・facts 読み込み・正規化・paren 注記解析）。

L1⇒L2 実行計画（work/allusionist_v2/L2/README.md 2026-10-24 確定版）準拠。
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]            # AllusionistWiki_work
L2_DIR = ROOT / "work" / "allusionist_v2" / "L2"
L2_RUNS = L2_DIR / "runs"
L1_RUNS = ROOT / "work" / "allusionist_v2" / "L1" / "runs"
VAULT = ROOT.parent / "AllusionistLLMWiki2"
ENTITIES_DIR = VAULT / "wiki" / "entities"

L1_INPUT_RUNS = ["20261012T0000_baseline", "20261021T1727_9c2e"]  # P1 和集合

PREFIX_KIND = {
    "E_char": "character", "E_term": "terminology", "E_item": "item",
    "E_org": "organization", "E_motif": "motif", "E_phrase": "phrase",
}
KIND_PREFIX = {v: k for k, v in PREFIX_KIND.items()}

SUFFIXES = ("さん", "くん", "様", "氏", "先生", "殿", "ちゃん", "博士", "氏名")
PRONOUNS = {"俺", "私", "僕", "うち", "わらわ", "妾"}


def norm_key(s: str) -> str:
    """表記ゆれ統合キー: NFKC・中点/空白/波線除去・小文字化。"""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[・・\s・〜~・]+", "", s)
    return s.lower()


def parse_paren(s: str):
    """`主名（括弧注記）` を解析し (main, paren) を返す（注記なしは (s, None)）。"""
    m = re.match(r"^(.+?)[（(](.+?)[)）]\s*$", s)
    if m and len(m.group(2)) <= 20:
        return m.group(1).strip(), m.group(2).strip()
    return s, None


def strip_suffix(key: str) -> str:
    for suf in SUFFIXES:
        if key.endswith(suf) and len(key) > len(suf) + 1:
            return key[: -len(suf)]
    return key


def load_facts(run_ids=L1_INPUT_RUNS):
    """指定 L1 run の facts を yield する（dict に episode/subject/entity_type/paragraph/quote/fact_id/run を付与）。"""
    for rid in run_ids:
        fdir = L1_RUNS / rid / "facts"
        if not fdir.is_dir():
            raise FileNotFoundError(str(fdir))
        for fp in sorted(fdir.glob("*.jsonl")):
            for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                d["run"] = rid
                yield d


def load_seed_pages():
    """公開エンティティページ（S1 骨格）。_容姿 属性ページは同一キャラの属性として本体 stem に寄せる。"""
    seeds = {}
    for p in ENTITIES_DIR.rglob("*.md"):
        stem = p.stem
        if stem.endswith("_容姿"):
            continue
        if stem == "index":
            continue
        parts = stem.split("_", 2)
        if len(parts) < 3:
            continue
        prefix, kind_part, display = parts
        kind = PREFIX_KIND.get(f"{prefix}_{kind_part}")
        if not kind:
            continue
        seeds[stem] = {"id": stem, "kind": kind, "display": display,
                       "norm": norm_key(display), "path": str(p.relative_to(VAULT))}
    return seeds


def non_entity_reason(s: str):
    """非エンティティ機械フィルタ（P7）。理由を返し、通れば None。"""
    if s in PRONOUNS:
        return "pronoun"
    if len(s) > 25:
        return "too_long"
    if re.search(r"(する|した|される|である|だった|ている|ていく|てくる)$", s):
        return "predicate_form"
    if "「" in s and "」" in s:
        return "quoted_sentence"
    if "、" in s and len(s) > 15:
        return "list_phrase"
    if "。" in s:
        return "sentence"
    return None


def ep_sort_key(ep: str):
    m = re.search(r"(\d+)", ep or "")
    return int(m.group(1)) if m else 0

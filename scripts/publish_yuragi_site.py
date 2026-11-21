#!/usr/bin/env python
"""L1/full 監査済み run を YuragiWiki/content/ へ公開同期するスクリプト。

- units/topics/authors/chronology（L1 版）＋ full（制約なし版）を content/ 直下要素へ配置。
- ref（YJ-T031:1245 形式）を YuragiWiki raw repo の ③ 投稿ファイル URL へ変換。
- frontmatter title 付与（graph ノード名規定）。
- 来歴: 使用 run ID を各ページ frontmatter に記録。
"""
import json
import re
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
L1 = WORK / "work" / "yuragi" / "L1"
L0 = WORK / "work" / "yuragi" / "L0"
SITE = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki")
CONTENT = SITE / "content"
RAW_BBS = SITE / "raw" / "bbs"
BLOB = "https://github.com/allusionistwiki/YuragiWiki/blob/main/raw/bbs/"

UNITS_RUN = "20261117T2115_l1u"
UNITS_AUDIT = "20261120T1200_l11uaud2"
TOPICS_RUN = "20261119T1140_l1tp"
TOPICS_AUDIT = "20261120T1630_l11tpaud2"
AUTHORS_RUN = "20261119T2003_l1au"
AUTHORS_AUDIT = "20261120T1700_l11auaud2"
CHRONO_RUN = "20261118T0149_l1ch"
FULL_RUN = "20261121T2230_l1fullcn"
ENTITIES_RUN = None  # entities 生成後に設定（runs 内の最新 _l1en を自動検出）
ENTITIES_AUDIT = "20261121T1430_l11en4aud"  # entities 全量監査 PASS run


def jl(p: Path):
    out = []
    for l in p.read_bytes().decode("utf-8", "replace").splitlines():
        if l.strip():
            r = json.loads(l)
            if r.get("_meta"):
                continue
            out.append(r)
    return out


def meta_of(p: Path):
    for l in p.read_bytes().decode("utf-8", "replace").splitlines():
        if l.strip():
            r = json.loads(l)
            if r.get("_meta"):
                return r
    return None


def latest(prefix: str) -> Path:
    ds = sorted(d for d in (L0 / "runs").iterdir() if d.name.endswith(prefix))
    return ds[-1]


def main() -> int:
    led = latest("_l0c")
    units = {json.loads(l)["unit_id"]: json.loads(l) for l in (led / "units.jsonl").read_bytes().decode("utf-8").splitlines() if l.strip()}

    # L0 検索索引 → 実体 backlink・月別年表（決定論追記用）
    import unicodedata as _ud
    si = latest("_l0si")
    terms_rows = jl(si / "search" / "terms.jsonl")
    bydate = {r["ref"]: r["date_iso"] for r in jl(si / "search" / "by-date.jsonl") if r.get("date_iso")}
    _ecands = sorted(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1en"))
    ent_map = {}  # NFKC term -> slug
    for cn in _ecands:
        for p in sorted((L1 / "runs" / cn / "entities").glob("*.md")):
            tm = re.search(r'term:\s*"([^"]+)"', p.read_bytes().decode("utf-8", "replace"))
            term = tm.group(1) if tm else p.stem
            ent_map.setdefault(_ud.normalize("NFKC", term).strip(), p.stem)
    ent_units = {}  # slug -> (term, [(uid, count) 件数降順])
    term_refs = {}  # NFKC term -> refs
    for r in terms_rows:
        key = _ud.normalize("NFKC", r["term"]).strip()
        term_refs.setdefault(key, []).extend(r.get("refs", []))
        slug = ent_map.get(key)
        if not slug:
            continue
        cnt: dict[str, int] = {}
        for ref in r.get("refs", []):
            uid = ref.split(":")[0]
            cnt[uid] = cnt.get(uid, 0) + 1
        prev = ent_units.get(slug)
        if prev:
            merged = dict(prev[1])
            for uid_, c in cnt.items():
                merged[uid_] = max(merged.get(uid_, 0), c)
            cnt = merged
        ent_units[slug] = (key, sorted(cnt.items(), key=lambda x: (-x[1], x[0])))
    unit_ents: dict[str, list] = {}
    for slug, (term, pairs) in ent_units.items():
        for uid_, c in pairs:
            unit_ents.setdefault(uid_, []).append((c, term, slug))
    # 共起实体: 同一篇に共出現する実体ペアの篇数
    cooccur: dict[str, dict[str, int]] = {}
    for uid_, ents in unit_ents.items():
        slugs = [sl for _, _, sl in ents]
        for a in range(len(slugs)):
            for b in range(a + 1, len(slugs)):
                x, y = slugs[a], slugs[b]
                cooccur.setdefault(x, {}).setdefault(y, 0)
                cooccur[x][y] += 1
                cooccur.setdefault(y, {}).setdefault(x, 0)
                cooccur[y][x] += 1

    # ref → raw ファイル URL（③ 行から）
    ref_url = {}
    unit_dir_rel = {}
    for sf in RAW_BBS.glob("**/structured.jsonl"):
        rel = sf.parent.relative_to(RAW_BBS).as_posix()
        m = meta_of(sf)
        if m:
            unit_dir_rel[m["unit_id"]] = rel
        for r in jl(sf):
            if "ref" not in r:
                continue
            f = r.get("file")
            if f:
                ref_url[r["ref"]] = BLOB + rel + "/" + f

    LINK_RE = re.compile(r"YJ-[A-Za-z]+[0-9]+:[0-9]+")
    FULLSITE = "https://allusionistwiki.github.io/YuragiWiki/full/"

    # 投稿 permalink 地図: uid -> {post_no: ページ URL}
    post_page = {}
    for uid, u in units.items():
        rel = unit_dir_rel.get(uid)
        if not rel:
            continue
        nums = [r["post_no"] for r in jl(RAW_BBS / rel / "structured.jsonl")]
        post_page[uid] = {pno: ("" if (k := i // 100 + 1) == 1 else f"p{k}")
                          for i, pno in enumerate(nums)}

    def permalink(uid: str, n: int) -> str | None:
        seg = post_page.get(uid, {}).get(n)
        if seg is None:
            return None
        return f"{FULLSITE}{uid}/{seg}#post-{n}"

    def linkify(body: str, uid: str | None = None) -> str:
        def rep(mo):
            ref = mo.group(0)
            u = ref_url.get(ref)
            if not u:
                return ref
            return f"[{ref}]({u})"
        body = LINK_RE.sub(rep, body)
        # YJ-uid:N → full 版投稿 permalink（原文アンカー）
        def rep2(mo):
            uid_, n = mo.group(1), int(mo.group(2))
            pl = permalink(uid_, n)
            return f"[{uid_}:{n}]({pl})" if pl else mo.group(0)
        body = re.sub(r"(?<![\[/A-Za-z0-9-])(YJ-[A-Za-z0-9]+):(\d+)(?!/[A-Za-z])", rep2, body)
        # units 記事の「投稿N」→ 自篇 full permalink
        if uid:
            def rep3(mo):
                n = int(mo.group(1))
                pl = permalink(uid, n)
                return f"[投稿{n}]({pl})" if pl else mo.group(0)
            body = re.sub(r"投稿(\d+)", rep3, body)
        return body

    def emit(md: Path, dest: Path, title: str, extra_fm: dict, uid: str | None = None):
        txt = md.read_bytes().decode("utf-8", "replace")
        m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", txt, re.S)
        fm = m.group(1) if m else ""
        body = txt[m.end():] if m else txt
        title_m = re.search(r'^title:\s*"?([^"\n]+)"?', fm, re.M)
        t = title_m.group(1) if title_m else title
        fm2 = fm + "\n" + "".join(f'{k}: "{v}"\n' for k, v in extra_fm.items() if k not in fm)
        if "title:" not in fm:
            fm2 = f'title: "{t}"\n' + fm2
        body = linkify(body, uid if uid and dest.parent.name == "units" else None)
        # 原文の $ ペアは LaTeX math と誤認されるためエスケープ（Katex unicode 化防止）
        body = re.sub(r"(?<!\\)\$", r"\\\$", body)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f"---\n{fm2}---\n{body}".encode("utf-8"))

    # full（原文全文版・篇索引＋投稿 permalink 分页）
    for p in sorted((L1 / "runs" / FULL_RUN / "units").glob("*.md")):
        uid = p.stem
        t = units.get(uid, {}).get("title", uid)
        emit(p, CONTENT / "full" / p.name, t, {"link_audit": FULL_RUN})
        fp = CONTENT / "full" / p.name
        cur = fp.read_bytes().decode("utf-8", "replace")
        # 直下 pages の相対 depth 修正（../../units は full/<uid>/pK 用・直下では 1 過剰）
        cur = cur.replace("](../../units/", "](../units/")
        if "[[units/" not in cur:
            fp.write_bytes((cur.rstrip("\r\n") + f"\n\n---\n関連: [[units/{uid}|L1 版記事]]\n").encode("utf-8"))
    pages_dir = L1 / "runs" / FULL_RUN / "pages"
    if pages_dir.exists():
        for pp in sorted(pages_dir.glob("*/*.md")):
            uid = pp.parent.name
            t = units.get(uid, {}).get("title", uid)
            emit(pp, CONTENT / "full" / uid / pp.name, f"{t}（原文 {pp.stem}）",
                 {"link_audit": FULL_RUN, "unit": uid})

    # units（L1 版）
    for p in sorted((L1 / "runs" / UNITS_RUN / "units").glob("*.md")):
        uid = p.stem
        t = units.get(uid, {}).get("title", uid)
        emit(p, CONTENT / "units" / p.name, t, {"link_audit": UNITS_AUDIT}, uid=uid)
        up = CONTENT / "units" / p.name
        cur = up.read_bytes().decode("utf-8", "replace")
        if "[[full/" not in cur:
            cur = cur.rstrip() + f"\n\n---\n関連: [[full/{uid}|原文全文（制約なし版）]] ／ [[free/{uid}|自由記述記事]]\n"
        # 本篇で言及される実体（決定論 backlink）
        ents = sorted(unit_ents.get(uid, []), key=lambda x: (-x[0], x[1]))[:30]
        if ents:
            cur = cur.rstrip() + "\n\n## 本篇で言及される実体\n\n"
            cur += "".join(f"- [[entities/{sl}|{term}]]（{n} 件）\n" for n, term, sl in ents)
        up.write_bytes(cur.encode("utf-8"))

    # free（制約なし自由記述記事・LLM 全量監査 100% 収束）
    FREE_RUN = "20261119T0014_l1free"
    FREE_AUDIT = "20261121T1900_l11faud5"
    for p in sorted((L1 / "runs" / FREE_RUN / "units").glob("*.md")):
        uid = p.stem
        t = units.get(uid, {}).get("title", uid)
        emit(p, CONTENT / "free" / p.name, t, {"link_audit": FREE_AUDIT}, uid=uid)
        fp = CONTENT / "free" / p.name
        cur = fp.read_bytes().decode("utf-8", "replace")
        if "[[units/" not in cur:
            cur = cur.rstrip() + f"\n\n---\n関連: [[units/{uid}|L1 版記事]] ／ [[full/{uid}|原文全文]]\n"
        ents = sorted(unit_ents.get(uid, []), key=lambda x: (-x[0], x[1]))[:30]
        if ents:
            cur = cur.rstrip() + "\n\n## 本篇で言及される実体\n\n"
            cur += "".join(f"- [[entities/{sl}|{term}]]（{n} 件）\n" for n, term, sl in ents)
        fp.write_bytes(cur.encode("utf-8"))
    fidx = CONTENT / "free_index.md"
    fl = ["---", 'title: "自由記述索引"', "run: publish", "---", "", "# 自由記述記事（制約なし版）", "",
          "L1 版記事と原文をもとに、L1 の構造制約なしで自由記述した記事群（LLM 全量監査 100% 収束）。", ""]
    for p in sorted((CONTENT / "free").glob("*.md")):
        if p.stem == "index":
            continue
        uid = p.stem
        t = units.get(uid, {}).get("title", uid)
        fl.append(f"- [[free/{uid}|{t}]]")
    fidx.write_bytes("\n".join(fl).encode("utf-8"))
    # free/ フォルダノート（folderClickBehavior=link 時の受け皿）
    (CONTENT / "free" / "index.md").write_bytes(("\n".join(
        ["---", 'title: "自由記述版（トップ）"', "run: publish", "---", "",
         "# 自由記述版", "",
         "L1 版記事と原文をもとに、L1 の構造制約なしで記述した記事群（LLM 全量監査 100% 収束）。",
         "引用は原文からの逐語のみ・全記事 ref 付き。各記事から L1 版・原文全文版へ相互リンク付き。", "",
         "- 索引: [[free_index|自由記述索引]]",
         "- 見方: [[guide|読み方ガイド]]", ""])
    ).encode("utf-8"))

    # topics / authors
    for p in sorted((L1 / "runs" / TOPICS_RUN / "topics").glob("*.md")):
        fm = p.read_bytes().decode("utf-8", "replace")
        tm = re.search(r'term:\s*"([^"]+)"', fm)
        emit(p, CONTENT / "topics" / p.name, tm.group(1) if tm else p.stem, {"link_audit": TOPICS_AUDIT})
    for p in sorted((L1 / "runs" / AUTHORS_RUN / "authors").glob("*.md")):
        fm = p.read_bytes().decode("utf-8", "replace")
        am = re.search(r'author:\s*"([^"]+)"', fm)
        emit(p, CONTENT / "authors" / p.name, am.group(1) if am else p.stem, {"link_audit": AUTHORS_AUDIT})

    # ディレクトリ索引ページ（full/topics/authors — トップ導線の受け皿）
    idx_specs = [
        ("full", "full 篇索引（原文全文）",
         "各篇の投稿全文をそのまま掲載（投稿単位アンカー付き）。",
         lambda p: units.get(p.stem, {}).get("title", p.stem)),
        ("topics", "topics 索引",
         "話題・語句の横断記事（出現 3 以上）。",
         lambda p: re.search(r'title:\s*"([^"]+)"', (CONTENT / "topics" / p.name).read_bytes().decode("utf-8", "replace")).group(1)
         if re.search(r'title:\s*"([^"]+)"', (CONTENT / "topics" / p.name).read_bytes().decode("utf-8", "replace")) else p.stem),
        ("authors", "authors 索引",
         "主要投稿者記事（投稿 10 以上）。",
         lambda p: re.search(r'title:\s*"([^"]+)"', (CONTENT / "authors" / p.name).read_bytes().decode("utf-8", "replace")).group(1)
         if re.search(r'title:\s*"([^"]+)"', (CONTENT / "authors" / p.name).read_bytes().decode("utf-8", "replace")) else p.stem),
    ]
    for d, title, desc, lab in idx_specs:
        lines = ["---", f'title: "{title}"', "run: publish", "---", "", f"# {title}", "", desc, "",
                "見方: [[guide|読み方ガイド]]（版の関係・引用アンカー・来歴）", ""]
        for p in sorted((CONTENT / d).glob("*.md")):
            if p.stem == "index":
                continue
            lines.append(f"- [[{d}/{p.stem}|{lab(p)}]]")
        lines.append("")
        (CONTENT / d / "index.md").write_bytes("\n".join(lines).encode("utf-8"))

    # chronology
    cp = L1 / "runs" / CHRONO_RUN / "chrono" / "chronology.md"
    emit(cp, CONTENT / "chronology.md", "年表", {"link_audit": CHRONO_RUN})

    # 年表に決定論追記: 月別投稿数・主要語句の初出/最終言及（by-date 台帳照合）
    from collections import Counter
    ym = Counter(d[:7] for d in bydate.values())
    cl = ["## 月別投稿数", ""]
    for y in sorted({m[:4] for m in ym}):
        months = [f"{int(m[5:7])}月 {ym[m]}" for m in sorted(ym) if m.startswith(y)]
        cl.append(f"**{y} 年**　" + " ／ ".join(months) + "")
        cl.append("")
    tops = sorted(terms_rows, key=lambda r: -r["count"])[:40]
    cl += ["## 主要語句の初出・最終言及", "", "| 語句 | 初出 | 最終 |", "|---|---|---|"]
    for r in tops:
        refs = [x for x in r.get("refs", []) if x in bydate]
        if not refs:
            continue
        refs.sort(key=lambda x: bydate[x])
        def cell(ref):
            uid_, n = ref.split(":")
            pl = permalink(uid_, int(n))
            lab = f"{uid_} 投稿{n}（{bydate[ref][:10]}）"
            return f"[{lab}]({pl})" if pl else lab
        cl.append(f"| {r['term']} | {cell(refs[0])} | {cell(refs[-1])} |")
    cl.append("")
    cp_out = CONTENT / "chronology.md"
    cur = cp_out.read_bytes().decode("utf-8", "replace")
    cp_out.write_bytes((cur.rstrip() + "\n\n" + "\n".join(cl)).encode("utf-8"))

    # works（創作記述ページ・決定論組立・投稿 permalink 付き）
    wrun = None
    cands = sorted(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1works"))
    if cands:
        wrun = cands[-1]
        wentries = []
        for p in sorted((L1 / "runs" / wrun / "works").glob("*.md")):
            txt = p.read_bytes().decode("utf-8", "replace")
            tm = re.search(r'title:\s*"([^"]+)"', txt)
            am = re.search(r'author:\s*"([^"]+)"', txt)
            ym = re.search(r'type:\s*"([^"]+)"', txt)
            emit(p, CONTENT / "works" / p.name, (tm.group(1) if tm else p.stem),
                 {"link_audit": wrun})
            wentries.append((tm.group(1) if tm else p.stem,
                             am.group(1) if am else "",
                             ym.group(1) if ym else ""))
        for p in sorted((L1 / "runs" / wrun / "index").glob("*.md")):
            tm = re.search(r'title:\s*"([^"]+)"', p.read_bytes().decode("utf-8", "replace"))
            emit(p, CONTENT / "works_index" / p.name, tm.group(1) if tm else p.stem,
                 {"link_audit": wrun})
        top = CONTENT / "works_top.md"
        idx_lines = ["---", 'title: "創作索引（トップ）"', "run: publish", "---", "",
                     "# 創作記述索引", "",
                     "BBS 各スレッドに散在する創作的記述（詩・短編・設定文・劇中作品文等）の横断索引。",
                     "各作品ページには収録投稿の原文全文と投稿単位 permalink が付いています。", ""]
        seen_t = []
        for p in sorted((CONTENT / "works_index").glob("*.md")):
            tm = re.search(r'title:\s*"([^"]+)"', p.read_bytes().decode("utf-8", "replace"))
            if tm and tm.group(1) not in seen_t:
                seen_t.append(tm.group(1))
                idx_lines.append(f"- [[works_index/{p.stem}|{tm.group(1)}]]")
        idx_lines.append(
            "- [[widx_authors|作者索引]] — 掲載作品数順の作者別創作索引\n"
            "- [[widx_units|篇収容索引]] — 篇別の掲載創作一覧")
        idx_lines.append("")
        idx_lines.append(f"（作品ページ {len(wentries)}・収録創作群 7,621）")
        top.write_bytes("\n".join(idx_lines).encode("utf-8"))
        # works/ フォルダノート
        (CONTENT / "works" / "index.md").write_bytes(("\n".join(
            ["---", 'title: "作品ページ（トップ）"', "run: publish", "---", "",
             "# 作品ページ", "",
             "BBS 各スレッドに散在する創作的記述（詩・短編・設定文・劇中作品文等）の作品単位ページ。",
             "各ページに収録投稿の原文全文（逐語）と投稿単位 permalink 付き。", "",
             "- 横断索引: [[works_top|創作索引（トップ）]] ／ 类型別: works_index ／ 作者別: [[widx_authors/|創作作者索引]]",
             "- 見方: [[guide|読み方ガイド]]", ""])
        ).encode("utf-8"))

        # works 作者索引・篇収容索引（run *_l1widx）
        icands = sorted(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1widx"))
        if icands:
            irun = icands[-1]
            for p in sorted((L1 / "runs" / irun / "author_index").glob("*.md")):
                if p.stem == "index":
                    continue
                tm = re.search(r'title:\s*"([^"]+)"', p.read_bytes().decode("utf-8", "replace"))
                emit(p, CONTENT / "widx_authors" / p.name, tm.group(1) if tm else p.stem,
                     {"link_audit": irun})
            aidx = CONTENT / "widx_authors" / "index.md"
            al = ["---", 'title: "創作作者索引"', "run: publish", "---", "",
                  "# 創作作者索引（作品掲載数順）", ""]
            al += [f"- [[{p.stem}|{p.stem}]]"
                   for p in sorted((L1 / "runs" / irun / "author_index").glob("*.md"))
                   if p.stem != "index"]
            aidx.write_bytes("\n".join(al).encode("utf-8"))
            for p in sorted((L1 / "runs" / irun / "unit_index").glob("*.md")):
                emit(p, CONTENT / "widx_units" / p.name, p.stem, {"link_audit": irun})
            uidx = CONTENT / "widx_units" / "index.md"
            ul = ["---", 'title: "創作篇収容索引"', "run: publish", "---", "",
                  "# 創作篇収容索引", ""]
            ul += [f"- [[{p.stem}|{p.stem}]]"
                   for p in sorted((L1 / "runs" / irun / "unit_index").glob("*.md"))]
            uidx.write_bytes("\n".join(ul).encode("utf-8"))
            for stale in (CONTENT / "widx_authors.md", CONTENT / "widx_units.md"):
                stale.unlink(missing_ok=True)

    # entities（実体ページ・wiki 中核）
    import re as _re
    ent_run = ENTITIES_RUN
    if not ent_run:
        cands = sorted(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1en"))
        # 増分 run 運用: 最新 run に無い slug は親 run 群から継承（新しい slug Directory が同名に優先）
        ent_run = cands[-1] if cands else None
    ent_inherit = [c for c in reversed(cands[:-1])] if ent_run else []
    ent_slugs = {}
    if ent_run:
        import unicodedata
        def _slugify_norm(s):
            return unicodedata.normalize("NFKC", s).strip()
        src_dir = L1 / "runs" / ent_run / "entities"
        inherited = {}
        for irun in ent_inherit:
            for p in sorted((L1 / "runs" / irun / "entities").glob("*.md")):
                inherited.setdefault(p.stem, p)
        for p in sorted(src_dir.glob("*.md")):
            fm = p.read_bytes().decode("utf-8", "replace")
            tm = _re.search(r'term:\s*"([^"]+)"', fm)
            if tm:
                ent_slugs[_slugify_norm(tm.group(1))] = p.stem
        emit_slugs = {}
        for p in sorted(src_dir.glob("*.md")):
            fm = p.read_bytes().decode("utf-8", "replace")
            tm = _re.search(r'term:\s*"([^"]+)"', fm)
            term = tm.group(1) if tm else p.stem
            emit(p, CONTENT / "entities" / p.name, term, {"link_audit": ENTITIES_AUDIT})
            emit_slugs[p.stem] = term
        for stem, p in sorted(inherited.items()):
            if stem in emit_slugs:
                continue
            fm = p.read_bytes().decode("utf-8", "replace")
            tm = _re.search(r'term:\s*"([^"]+)"', fm)
            term = tm.group(1) if tm else stem
            emit(p, CONTENT / "entities" / p.name, term, {"link_audit": ENTITIES_AUDIT})
            emit_slugs[stem] = term
            tnorm = _slugify_norm(term)
            if tnorm not in ent_slugs:
                ent_slugs[tnorm] = stem
        # 関連する実体欄 → entity 相互リンク（長い語優先で置換）
        terms_sorted = sorted(ent_slugs, key=len, reverse=True)
        for p in sorted((CONTENT / "entities").glob("*.md")):
            art = p.read_bytes().decode("utf-8", "replace")
            m = _re.search(r"(##\s*関連する実体.*?)(?=\n##|\Z)", art, re.S)
            if not m:
                continue
            sec = m.group(1)
            self_slug = p.stem
            # 既存 wikilink をセンチネル保護
            _links: list[str] = []
            def _prot(mo):
                _links.append(mo.group(0))
                return "\u0000L%d\u0000" % (len(_links) - 1)
            sec = _re.sub(r"\[\[[^\]]*\]\]", _prot, sec)
            # 単一スキャン最長一致（語の入れ子再帰置換を構造的に起こさない）
            terms_here = [t for t in terms_sorted if ent_slugs[t] != self_slug]
            terms_len = sorted(terms_here, key=len, reverse=True)
            pat = "(" + "|".join(_re.escape(t) for t in terms_len) + ")"
            found: dict[str, tuple[str, str]] = {}
            def _mk(mo):
                t = mo.group(1)
                key = "\u0000K%d\u0000" % len(found)
                found[key] = (ent_slugs[t], t)
                return key
            sec = _re.sub(pat, _mk, sec)
            for key, (sl, t) in found.items():
                sec = sec.replace(key, f"[[entities/{sl}|{t}]]")
            sec = _re.sub(r"\u0000L(\d+)\u0000", lambda mo: _links[int(mo.group(1))], sec)
            new = art[:m.start(1)] + sec + art[m.end(1):]
            p.write_bytes(new.encode("utf-8"))
        # 言及篇一覧（決定論 backlink: 実体ページ → 篇）＋ 初出/最終言及日
        for p in sorted((CONTENT / "entities").glob("*.md")):
            info = ent_units.get(p.stem)
            if not info:
                continue
            art = p.read_bytes().decode("utf-8", "replace")
            if "## 言及篇" in art:
                continue
            pairs = info[1][:30]
            sec = "\n\n## 言及篇\n\n" + "".join(
                f"- [[units/{u}|{units.get(u, {}).get('title', u)}]]（{c} 件）\n"
                for u, c in pairs)
            ds = sorted(bydate[r][:10] for r in term_refs.get(info[0], []) if r in bydate)
            if ds:
                sec += f"\n初出 {ds[0]} ／ 最終言及 {ds[-1]}（{len(ds)} 件）\n"
            co = sorted(cooccur.get(p.stem, {}).items(), key=lambda kv: (-kv[1], kv[0]))[:15]
            if co:
                co_lines = "".join(
                    f"- [[entities/{s}|{ent_units[s][0]}]]（共起 {n} 篇）\n"
                    for s, n in co if s in ent_units)
                if co_lines:
                    sec += "\n## 共起実体\n\n" + co_lines
            p.write_bytes((art.rstrip() + sec).encode("utf-8"))
        # 类型別索引
        idx = ["---", 'title: "実体索引"', "run: publish", "---", "", "# 実体索引", ""]
        by_type = {}
        for p in sorted((CONTENT / "entities").glob("*.md")):
            if p.stem == "index":
                continue
            a = p.read_bytes().decode("utf-8", "replace")
            tm = _re.search(r'term:\s*"([^"]+)"', a)
            ty = _re.search(r'type:\s*"([^"]+)"', a)
            by_type.setdefault(ty.group(1) if ty else "その他", []).append((tm.group(1) if tm else p.stem, p.stem))
        for tname in sorted(by_type):
            idx.append(f"## {tname}")
            idx.append("")
            for term, sl in sorted(by_type[tname]):
                idx.append(f"- [[entities/{sl}|{term}]]")
            idx.append("")
        (CONTENT / "entities_index.md").write_bytes("\n".join(idx).encode("utf-8"))
        # entities/ フォルダノート
        (CONTENT / "entities" / "index.md").write_bytes(("\n".join(
            ["---", 'title: "実体索引（トップ）"', "run: publish", "---", "",
             "# 実体索引", "",
             "人物・物品・国・事件・概念など、作中実体のページ群（wiki 中核）。登場 2 以上を収録。",
             "各ページは概要・記述の流れ・関連実体・注目投稿（原文逐語リンク）・言及篇・共起実体を持ちます。", "",
             "- 类型別索引: [[entities_index|実体索引（类型別）]]",
             "- 見方: [[guide|読み方ガイド]]", ""])
        ).encode("utf-8"))

    AL_RUNS = ["20261122T1310_l1allud6"]
    try:
        _led0 = json.loads((WORK / "data/yuragi_allud_batches.json").read_text(encoding="utf-8"))
        for b0 in _led0.get("batches", []):
            if b0.get("status") == "done" and b0.get("run_dir") and b0["run_dir"] not in AL_RUNS:
                AL_RUNS.append(b0["run_dir"])
    except Exception:
        pass
    AL_RUN = "20261122T1310_l1allud6"
    n_allud_pages = 0
    KIND_ORDER = ["神話", "宗教", "文学", "音楽", "映像", "ゲーム", "歴史", "地理", "科学", "人物", "ブランド", "その他"]
    adirs = [d for d in (L1 / "runs" / r / "allusions" for r in AL_RUNS) if d.is_dir()]
    if adirs:
        units_meta = {}
        latest0 = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
        for l in (L0 / "runs" / latest0 / "units.jsonl").read_text(encoding="utf-8").splitlines():
            if l.strip():
                r0 = json.loads(l)
                if not r0.get("_meta"):
                    units_meta[r0["unit_id"]] = r0
        n_allud = 0
        n_supp_total = 0
        kind_total: dict = {}
        per_unit: dict = {}
        (CONTENT / "allusions").mkdir(parents=True, exist_ok=True)
        for adir in adirs:
            run_id = adir.parent.name
            supp: dict = {}
            sp_path = adir.parent / "suppressions.json"
            if sp_path.is_file():
                for s0 in json.loads(sp_path.read_text(encoding="utf-8")):
                    kk = str(s0.get("term", "")).strip().lower().replace("・", "").replace(" ", "")
                    supp[(str(s0.get("unit", "")), kk)] = s0
            for fp in sorted(adir.glob("*.jsonl")):
                uid = fp.stem
                if uid == "gate_drops":
                    continue
                items = [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
                seen0: dict = {}
                for it0 in items:
                    k0 = str(it0.get("term", "")).strip().lower().replace("・", "").replace(" ", "")
                    if k0 in seen0:
                        refs0 = {q.get("ref") for q in seen0[k0].get("quotes", [])}
                        seen0[k0]["quotes"] = (seen0[k0].get("quotes", []) +
                                               [q for q in it0.get("quotes", []) if q.get("ref") not in refs0][:8])
                        continue
                    seen0[k0] = dict(it0)
                items = []
                n_supp_unit = 0
                for k0, it0 in seen0.items():
                    s0 = supp.get((uid, k0))
                    if s0 and s0.get("action") == "drop":
                        n_supp_total += 1
                        n_supp_unit += 1
                        continue
                    if s0 and s0.get("action") == "fix_usage" and s0.get("new_usage"):
                        it0["usage"] = str(s0["new_usage"])
                    items.append(it0)
                if not items:
                    continue
                um = units_meta.get(uid, {})
                title = str(um.get("thread_title") or um.get("title") or uid)
                items.sort(key=lambda x: (KIND_ORDER.index(x.get("kind", "その他")) if x.get("kind") in KIND_ORDER else 99, x.get("term", "")))
                body = [f'---\ntitle: "実世界参照 — {uid}"\nrun: {run_id}\nlink_audit: "{run_id}"\nunit: "{uid}"\n---', "",
                        f"# 実世界参照 — {uid}", "",
                        f"{title} の記述中に見出された**実世界（作品世界の外）の参照**の抽出一覧。出典: 解析層 run `{run_id}`（LLM 抽出＋機械引用ゲート＋全件実読監査）。",
                        "",
                        f"→ 元: [[units/{uid}|{uid} 版記事]] ・ [[full/{uid}|原文全文]]",
                        "",
                        f"## 参照対象 {len(items)} 件" + (f"（全件実読監査で {n_supp_unit} 件を選外）" if n_supp_unit else ""), ""]
                unit_kinds: dict = {}
                for it in items:
                    term = str(it.get("term", ""))
                    kind = str(it.get("kind", "その他"))
                    conf = str(it.get("confidence", ""))
                    usage = str(it.get("usage", ""))
                    body.append(f"### {term}（{kind}・{conf}）")
                    body.append("")
                    body.append(usage)
                    body.append("")
                    for q in it.get("quotes", []):
                        ref = str(q.get("ref", ""))
                        qq = str(q.get("q", ""))
                        pno = ref.split(":")[-1] if ":" in ref else ""
                        body.append(f"> 「{qq}」 [[full/{uid}#post-{pno}|{ref}]]")
                    body.append("")
                    unit_kinds[kind] = unit_kinds.get(kind, 0) + 1
                    kind_total[kind] = kind_total.get(kind, 0) + 1
                body += ["---", "", "## 節内内訳", "",
                         " ・ ".join(f"{k}: {v}" for k, v in sorted(unit_kinds.items(), key=lambda x: -x[1])),
                         "", "### 関連", "", "- [[allusions_index|実世界参照 索引]]", "- [[guide|読み方ガイド]]", ""]
                (CONTENT / "allusions" / f"{uid}.md").write_text("\n".join(body), encoding="utf-8")
                n_allud += 1
                per_unit[uid] = len(items)
        n_allud_pages = n_allud
        if n_allud:
            ix = [f'---\ntitle: "実世界参照 索引"\nrun: {AL_RUN}\n---', "",
                  "# 実世界参照 索引", "",
                  "参加者が実世界の神話・宗教・文学・音楽・歴史・科学などを持ち込んで組んだ参照関係の横断索引。各項目は逐語引用＋ref アンカーで原文に接続（機械保証）。信頼度（明言/蓋然性高/推測）を各項目に付す。", "",
                  f"対象篇: {n_allud}（抽出 run {len(AL_RUNS)} 本・全件実読監査込）", "",
                  "| 類型 | 件数 |", "|---|---:|"]
            for k, v in sorted(kind_total.items(), key=lambda x: -x[1]):
                ix.append(f"| {k} | {v} |")
            ix += ["", "## 篇別", ""]
            for uid2 in sorted(per_unit):
                ix.append(f"- [[allusions/{uid2}|{uid2}]]（{per_unit[uid2]} 件）")
            ix += ["", "※ 対象名（term）の篇横断名寄せは監査収束後の次段階。", ""]
            (CONTENT / "allusions_index.md").write_text("\n".join(ix), encoding="utf-8")

    # nav（185 篇索引）
    nav = ["---", 'title: "篇索引"', "run: publish", "---", "", "# 篇索引（185 篇）", ""]
    for uid in sorted(units):
        u = units[uid]
        nav.append(f"- [[units/{uid}|{u.get('title', uid)}]]（{u.get('n_posts', '?')} 投稿）")
    nav.append("")
    nav.append("各篇の制約なし版: [[full/|full 索引]]")
    (CONTENT / "nav.md").write_bytes("\n".join(nav).encode("utf-8"))

    # license（top は全層生成後の最後に書く）
    lic = """---
title: "ライセンス"
run: publish
---

# ライセンス

- 各投稿の著作権・著作者人格権は**各投稿者**に帰属します。本 Wiki の解析・要約はファン活動としての二次著作です。
- L1 版（units/topics/authors/chronology）は引用（100 字以内）と ref アンカーによる紹介です。
- 制約なし版（full/）は原文全文を掲載しています。掲載を望まない投稿者は管理者までご連絡ください。削除要請には速やかに対応します。
- コーパス生データ（raw/）と解析来歴は [YuragiWiki repo](https://github.com/allusionistwiki/YuragiWiki) に置く。
"""
    (CONTENT / "license.md").write_bytes(lic.encode("utf-8"))

    counts = {
        "units": len(list((CONTENT / "units").glob("*.md"))),
        "full": len(list((CONTENT / "full").glob("*.md"))),
        "topics": len(list((CONTENT / "topics").glob("*.md"))),
        "authors": len(list((CONTENT / "authors").glob("*.md"))),
        "linked_refs": len(ref_url),
    }

    # ---- flicker 層（Hatena Flicker 日記・LLM 解析記事＋原文逐語・permalink 付き） ----
    FL = RAW_BBS / "hatena_flicker"
    fl_units: list = []
    FL_ART_RUN = "20261121T2350_l1flgen"
    FL_AUDIT = "20261122T0700_l1flaud12"
    if (FL / "units.jsonl").exists():
        fl_units = jl(FL / "units.jsonl")
        fldir = CONTENT / "flicker"
        fldir.mkdir(exist_ok=True)
        for u in fl_units:
            uid = u["unit_id"]
            d = FL / u["path"]
            recs = jl(d / "structured.jsonl")
            art = L1 / "runs" / FL_ART_RUN / "flicker" / f"{uid}.md"
            parts = [f'---\ntitle: "{u["title"]}"\nrun: {FL_ART_RUN}\n'
                     f'link_audit: "{FL_AUDIT}"\n'
                     f'permaLink: "flicker/{uid}.html"\n---',
                     "",
                     f'# {u["title"]}',
                     "",
                     f'出典: <{u["url"]}>（Hatena Flicker）／収録 {u["n_posts"]} 件'
                     f'（{u.get("first")}〜{u.get("last")}）・各投稿に permalink 付き。',
                     f'元データ: [raw units]({BLOB}hatena_flicker/{u["path"]}/posts/)',
                     ""]
            if art.exists():
                atxt = art.read_bytes().decode("utf-8")
                m = re.match(r"^---\r?\n.*?\r?\n---\r?\n", atxt, re.S)
                parts.append(atxt[m.end():].strip())
                parts.append("")
            parts.append("## 日記原文（全文・逐語）")
            parts.append("")
            for rec in recs:
                body = (d / "posts" / f"p{rec['post_no']:04d}.md").read_bytes().decode("utf-8")
                parts.append(f'<a id="post-{rec["post_no"]}"></a>')
                parts.append(f'**{rec["date_iso"]} {rec["time"]}** '
                             f'[permalink]({rec["url"]})')
                parts.append("")
                parts.append(body)
                parts.append("")
            (fldir / f"{uid}.md").write_bytes("\n".join(parts).encode("utf-8"))
        idx = ["---", 'title: "日記索引（Hatena Flicker）"', "run: flicker",
               'permaLink: "flicker/index.html"', "---", "",
               "# 日記索引（Hatena Flicker）", "",
               "『ゆらぎの神話』関連 Hatena Flicker 日記（作者別・原文逐語・投稿 permalink 付き）。", ""]
        for u in sorted(fl_units, key=lambda x: -x["n_posts"]):
            idx.append(f"- [[flicker/{u['unit_id']}|{u['author']}]] — {u['n_posts']} 件"
                       f"（{u.get('first')}〜{u.get('last')}）")
        idx.append("")
        (CONTENT / "flicker_index.md").write_bytes("\n".join(idx).encode("utf-8"))
        # flicker/ フォルダノート
        (CONTENT / "flicker" / "index.md").write_bytes(("\n".join(
            ["---", 'title: "日記（Hatena Flicker）（トップ）"', "run: publish", "---", "",
             "# 日記（Hatena Flicker）", "",
             "『ゆらぎの神話』関連の Hatena Flicker 日記を作者別に収録（原文逐語・投稿 permalink 付き）。",
             "各作者ページは LLM 解析記事（全量監査 100% 収束）＋日記原文の全文を持ちます。", "",
             "- 索引: [[flicker_index|日記索引]]",
             "- 見方: [[guide|読み方ガイド]]", ""])
        ).encode("utf-8"))
        counts["allusions"] = n_allud_pages
        counts["flicker"] = len(fl_units)
        counts["flicker_posts"] = sum(u["n_posts"] for u in fl_units)

    # ---- top / guide / stats / about（全層生成後の最終書き込み・決定論） ----
    from collections import Counter as _Counter
    stats = json.loads((led / "stats.json").read_text(encoding="utf-8"))
    n_units = len(list((CONTENT / "units").glob("*.md")))
    n_full = len(list((CONTENT / "full").glob("*.md")))
    n_free = len([p for p in (CONTENT / "free").glob("*.md") if p.stem != "index"])
    n_topics = len([p for p in (CONTENT / "topics").glob("*.md") if p.stem != "index"])
    n_auth = len([p for p in (CONTENT / "authors").glob("*.md") if p.stem != "index"])
    n_ent = len([p for p in (CONTENT / "entities").glob("*.md") if p.stem != "index"])
    n_works = len([p for p in (CONTENT / "works").glob("*.md") if p.stem != "index"])
    n_fl = len(fl_units)
    n_fl_posts = sum(u.get("n_posts", 0) for u in fl_units)

    def _fm_get(path, key):
        a = path.read_bytes().decode("utf-8", "replace")
        m = re.search(rf'^{key}:\s*"?([^"\n]+)"?', a, re.M)
        return m.group(1) if m else ""

    def _lab(s):  # wikilink 表示名サニタイズ
        return s.replace("|", "｜").replace("[", "〔").replace("]", "〕")

    srcc, srcposts = _Counter(), _Counter()
    for u in units.values():
        s = u.get("source", "?")
        srcc[s] += 1
        srcposts[s] += u.get("n_posts", 0)
    ent_types = _Counter(_fm_get(p, "type") for p in (CONTENT / "entities").glob("*.md") if p.stem != "index")
    work_types = _Counter(_fm_get(p, "type") for p in (CONTENT / "works").glob("*.md"))
    auth_list = []
    for p in (CONTENT / "authors").glob("*.md"):
        if p.stem == "index":
            continue
        nm = _fm_get(p, "author")
        n = int(_fm_get(p, "n") or 0)
        auth_list.append((n, nm, p.stem))
    auth_list.sort(key=lambda x: (-x[0], x[2]))
    monthly = _Counter(d[:7] for d in bydate.values())
    date_lo = min(bydate.values())[:10]
    date_hi = max(bydate.values())[:10]

    def top_cell(d):
        return f"{d[:4]}年{int(d[5:7])}月"

    top = f"""---
title: "ゆらぎの神話 BBS 実況 Wiki"
description: "多人数で神話を創る試みの BBS 実況記録（{n_units} 篇・{stats['posts']:,} 投稿）を解析し、原文引用と出典リンク付きで公開する Wiki"
run: publish
---

# ゆらぎの神話 BBS 実況 Wiki

> [!info]
> 『ゆらぎの神話』— 複数 BBS の参加者が力を借りて神話を創った試みの記録。
> 本 Wiki は、したらば映画板 7039・mixi コミュ「架空の神話を作ろう」・はてなふりかーポータル の
> 実況・議論スレッド {n_units} 篇・{stats['posts']:,} 投稿を、解析パイプライン
> （L0 台帳 → 検索 → LLM 生成 → **LLM 全量品質監査 100%**）で整理し、
> 原文からの逐語引用＋ ref 出典リンク付きで公開しています。読み方は [[guide|読み方ガイド]]。

## はじめに

- [[guide|読み方ガイド]] — 版の関係・引用アンカー・来歴の読み方
- [[stats|統計]] — コーパスの全体像（出典別・月別・上位投稿者）
- [[about|この Wiki について]] — 出典・パイプライン・ライセンス帰属
- [[entities_index|実体索引]] — 人物・物品・国・事件・概念（世界の核・{n_ent} 件）
- [[works_top|創作索引]] — スレに散在する詩・短編・設定文（{n_works:,} 作品）
- [[nav|篇索引]] — 全 {n_units} 篇
- [[chronology|年表]] — 月別投稿数・主要語句の初出/最終言及（{date_lo} 〜 {date_hi}）

## 節

| 節 | 内容 | 規模 | 入口 |
|---|---|---|---|
| 篇記事（units） | L1 版の要約・整理記事 | {n_units} 篇 | [[nav|篇索引]] |
| 原文全文（full） | 投稿全文そのまま・投稿単位 permalink | {n_full} 篇 | [[full/index|full 索引]] |
| 自由記述（free） | 制約なし自由記述記事 | {n_free} 篇 | [[free_index|自由記述索引]] |
| 実体（entities） | 人物・物品・国・事件・概念 | {n_ent} 件 | [[entities_index|类型別索引]] |
| 創作（works） | 散在する詩・短編・設定文 | {n_works:,} 作品 | [[works_top|創作索引]] |
| 話題（topics） | 話題・語句（出現 3 以上） | {n_topics} 件 | [[topics/index|topics 索引]] |
| 投稿者（authors） | 主要投稿者（投稿 10 以上） | {n_auth} 名 | [[authors/index|authors 索引]] |
| 日記（flicker） | Hatena Flicker 関連日記 | {n_fl} 作者・{n_fl_posts} 投稿 | [[flicker_index|日記索引]] |
| 年表 | 月別集計・語句初出 | {date_lo} 〜 {date_hi} | [[chronology|年表]] |

## 版（三つの面）

- **L1 版（当サイト主要面）**: 要約・整理記事。引用は 100 字以内＋ ref アンカー（原文ファイルへのリンク付き）。
- **自由記述版（制約なし）**: [[free_index|free]] — L1 と原文をもとに構造制約なしで記述。引用は原文からの逐語のみ・全記事 ref 付き。
- **原文全文版**: [[full/index|full]] — 各篇の投稿全文をそのまま掲載（投稿単位アンカー付き）。

三版は相互リンクで結ばれています。投稿の著作権は各投稿者に帰属します（[[license|ライセンス]]・削除対応方針）。

## 統計（L0 台帳 {led.name}）

- 篇 {stats['units']} ／ 投稿 {stats['posts']:,} ／ 投稿群 {stats['chains']:,}（LLM 要約付き）／ 投稿者 {stats['authors']:,} 名 ／ 本文 {stats['chars_body']:,} 字
- 創作記述 → 作品ページ {n_works:,}・収録投稿は permalink 付き原文逐語
- 実体 {n_ent}（登場 2 以上）・自由記述記事 {n_free}・全記事 LLM 全量監査 100% 収束
- 来歴: 解析・生成・監査は AllusionistWiki_work repo（作業データ公開）で実施。各記事 frontmatter に run ID 記録。
"""
    (CONTENT / "index.md").write_bytes(top.encode("utf-8"))

    guide = """---
title: "読み方ガイド"
description: "版の関係・引用アンカー・ref 出典リンク・来歴の読み方"
run: publish
---

# 読み方ガイド

## 三つの版

各篇（スレッド）は三つの面で読めます。ページ間で相互リンクされています。

| 面 | 場所 | 内容 |
|---|---|---|
| L1 版 | `units/` | 概要・流れ・主要話題・注目投稿（引用 100 字以内）に整理した記事 |
| 自由記述版 | `free/` | L1 の構造制約なしに記述した記事（引用は原文逐語のみ・全記事 ref 付き） |
| 原文全文版 | `full/` | 投稿全文をそのまま掲載。`#post-N` アンカー付き（多数投稿の篇は p2・p3… に分页） |

## 引用と出典リンク

- **ref 形式 `YJ-T001:123`**: 「篇 YJ-T001 の投稿 123」を指す原文参照。リンク先は原文データ
  （GitHub の raw/ ③ 投稿チャンクファイル）です。
- **投稿 permalink**: 原文全文版の各投稿は `.../full/YJ-T001/p3#post-257` 形式の固定 URL を持ちます
  （`p3` は分页、`#post-257` は投稿アンカー）。L1 版・創作ページからの引用リンクもここを指します。
- **実体ページ**: 概要・記述の流れ・関連する実体・注目投稿・言及篇（その実体を語っているスレッド）・
  共起実体（同一篇に共出現する実体）を持ちます。

## 来歴（provenance）

- 全記事の frontmatter に生成 run ID（`run:`）と全量品質監査 run ID（`link_audit:`）を記録しています。
- 解析・生成・監査の工程は [AllusionistWiki_work](https://github.com/allusionistwiki/AllusionistWiki_work)
  の `work/yuragi/`（L0 台帳 → L1 生成 → 監査）に run 単位で保存され、来歴をたどれます。
- 生成はローカル LLM、品質監査は全記事 100% を LLM 監査して収束させています
  （引用の逐語性・ref の実在・日本語の質を検定）。

## 原文と著作権

- 原文データ（BBS 投稿文）の著作権は**各投稿者**に帰属します。本 Wiki はファン活動としての
  解析・紹介です（[[license|ライセンス]]）。
- 掲載を望まない投稿者はリポジトリ管理者までご連絡ください。削除要請には速やかに対応します。
- 生データ・編集方針は [YuragiWiki repo](https://github.com/allusionistwiki/YuragiWiki)（README・EDITING.md）。
"""
    (CONTENT / "guide.md").write_bytes(guide.encode("utf-8"))

    # 統計ダッシュボード（決定論）
    rows_src = ""
    src_meta = {
        "jbbs": ("したらば映画板 7039「ゆらぎの神話BBS」", "https://jbbs.shitaraba.net/movie/7039/"),
        "mixi": ("mixi コミュ「架空の神話を作ろう」", "https://mixi.jp/view_community.pl?id=373088"),
        "hatena": ("はてなふりかー（portal BBS）", "http://flicker.g.hatena.ne.jp/"),
    }
    for s in sorted(srcc, key=lambda x: -srcposts[x]):
        name, url = src_meta.get(s, (s, ""))
        rows_src += f"| [{name}]({url}) | {srcc[s]} | {srcposts[s]:,} |\n" if url else f"| {name} | {srcc[s]} | {srcposts[s]:,} |\n"
    year_rows = ""
    for y in sorted({m[:4] for m in monthly}):
        tot = sum(v for m, v in monthly.items() if m.startswith(y))
        peak = max((v, m) for m, v in monthly.items() if m.startswith(y))
        year_rows += f"| {y} | {tot:,} | {top_cell(peak[1])}（{peak[0]:,} 件） |\n"
    ent_type_rows = "".join(f"| {t} | {c:,} |\n" for t, c in ent_types.most_common())
    work_type_rows = "".join(f"| {t} | {c:,} |\n" for t, c in work_types.most_common(15))
    auth_rows = "".join(f"| [[authors/{sl}|{_lab(nm)}]] | {n:,} |\n" for n, nm, sl in auth_list[:20])
    top_terms = "".join(
        f"| {_lab(r['term'])} | {r['count']:,} |\n"
        for r in sorted(terms_rows, key=lambda r: -r["count"])[:15])
    fl_rows = "".join(
        f"| [[flicker/{u['unit_id']}|{_lab(u['author'])}]] | {u['n_posts']} |（{u.get('first')}〜{u.get('last')}）|\n"
        for u in sorted(fl_units, key=lambda x: -x["n_posts"])[:10])
    fl_note = ("| 作者 | 投稿 | 期間 |\n|---|---|---|\n" + fl_rows) if fl_rows else ""
    stats_md = f"""---
title: "統計"
description: "コーパス統計ダッシュボード（出典別・年別・上位投稿者・类型分布）"
run: publish
---

# 統計

L0 台帳 {led.name} 由来の決定論集計。詳細は [[chronology|年表]]・[[nav|篇索引]]。

## 出典別

| 出典 | 篇 | 投稿 |
|---|---|---|
{rows_src.rstrip()}

## 年別投稿数

| 年 | 投稿数 | 峰值月 |
|---|---|---|
{year_rows.rstrip()}

## 上位投稿者（top 20）

| 投稿者 | 投稿数 |
|---|---|
{auth_rows.rstrip()}

## 実体の类型分布

| 类型 | 件数 |
|---|---|
{ent_type_rows.rstrip()}

## 創作の类型分布（top 15）

| 类型 | 作品数 |
|---|---|
{work_type_rows.rstrip()}

## 主要語句（出現数 top 15）

| 語句 | 出現 |
|---|---|
{top_terms.rstrip()}
{("\n## 日記（Flicker）上位作者" + chr(10) + chr(10) + fl_note) if fl_note else ""}"""
    (CONTENT / "stats.md").write_bytes(stats_md.encode("utf-8"))

    about = f"""---
title: "この Wiki について"
description: "出典・解析パイプライン・ライセンス帰属・編集方針"
run: publish
---

# この Wiki について

## 何の Wiki か

『ゆらぎの神話』— 2005 年頃から複数 BBS で行われた「多人数で神話を創る試み」の実況・議論の記録を、
機械台帳と LLM 解析（全量品質監査付き）で整理したファン解析 Wiki です。
掲載記事は二次著作（紹介・解析）で、引用を通じて原文（一次資料）へ直接接続します。

## 出典（取得 2026-10-12）

- [したらば映画板 7039「ゆらぎの神話BBS」](https://jbbs.shitaraba.net/movie/7039/) — {srcc.get('jbbs', 0)} 篇
- [mixi コミュ「架空の神話を作ろう」](https://mixi.jp/view_community.pl?id=373088)（2005-10-22 開設）— {srcc.get('mixi', 0)} 篇
- [はてなふりかー（portal）](http://flicker.g.hatena.ne.jp/) — {srcc.get('hatena', 0)} 篇
- 関連 Hatena Flicker 日記 {n_fl} 作者（{n_fl_posts} 投稿）

mixi コミュ規約は記述の再利用・分散を明示的に許容しています（「元の設定を考えた人の許可を得る必要は全く
ありません」「誰でも引用可能な神話」）。原文データの出典・取得日は repo README に記録しています。

## 解析パイプライン

1. **L0 台帳**: 生 BBS データを SHA1 検証付きで取り込み、投稿単位チャンク（②）と
   structured.jsonl（③）へ正規化（{stats['posts']:,} 投稿・sha1 ラウンドトリップ検証）。
2. **検索索引**: 語句・日付・篇の転引索引（L0 検索台帳）。
3. **LLM 生成**: ローカル LLM で篇記事・実体・投稿者・創作・日記記事を生成。
4. **全量品質監査**: 全記事を LLM 監査（引用の逐語性・ref 実在・日本語品質）し、
   flagged 件を修復して 100% 収束。
5. **公開同期**: 監査済み run から決定論 publish（本文の機械的変換なし）で本サイトへ反映。

- 作業データ: [AllusionistWiki_work](https://github.com/allusionistwiki/AllusionistWiki_work) の `work/yuragi/`
  （run 単位・追加専用・来歴連鎖）。
- 原文データ: [YuragiWiki repo](https://github.com/allusionistwiki/YuragiWiki) の `raw/bbs/`。
- 全記事の frontmatter に生成 run ID・監査 run ID を記録（来歴）。

## ライセンス帰属

- wiki テキスト（解析・記述ページ）: CC0
- `raw/`（BBS 投稿文）・原文全文版の引用: **著作権は各投稿者に帰属**。
  出典を明記して公開し、削除要請に対応します（[[license|ライセンス]]）。

## 編集方針

今後の編集・拡張の規約は repo ルートの
[EDITING.md](https://github.com/allusionistwiki/YuragiWiki/blob/main/EDITING.md)（追加専用 run・
全量監査収束の原則・公開ゲート・拡張路線）。
"""
    (CONTENT / "about.md").write_bytes(about.encode("utf-8"))

    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

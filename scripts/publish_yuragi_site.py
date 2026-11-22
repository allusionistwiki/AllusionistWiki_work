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

UNITS_RUN = "20261122T0630_l1cnglyph"
UNITS_AUDIT = "20261120T1200_l11uaud2"
TOPICS_RUN = "20261119T1140_l1tp"
TOPICS_AUDIT = "20261120T1630_l11tpaud2"
AUTHORS_RUN = "20261119T2003_l1au"
AUTHORS_AUDIT = "20261120T1700_l11auaud2"
CHRONO_RUN = "20261118T0149_l1ch"
FULL_RUN = "20261122T0630_l1cnglyph"
ENTITIES_RUN = "20261122T0630_l1cnglyph"
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
    # 共起実体: 同一篇に共出現する実体ペアの篇数
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
        # 恒久 YAML ゲート: frontmatter 二重引用内の " を ' へ（Quartz 解析崩壊防止）
        fm = re.sub(r'^([\w-]+):[ \t]*"(.*)"[ \t]*$',
                    lambda mm: (f'{mm.group(1)}: "{mm.group(2).replace(chr(34), chr(39))}"'
                                if '"' in mm.group(2) else mm.group(0)), fm, flags=re.M)
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

    # full（原文全文版・篇索引＋投稿 permalink 分頁）
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
        # 実世界参照（allusion）page への相互リンクは allusion 生成後（Lane B4）
        up.write_bytes(cur.encode("utf-8"))

    # free（制約なし自由記述記事・LLM 全量監査 100% 収束）
    FREE_RUN = "20261122T0630_l1cnglyph"
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
        # 恒久: works 面全面掃除→供給一元化＋normkey 重複は品質優先（unit ref・リンク数）で単一化
        import unicodedata as _uw
        def _nkW(s):
            s = _uw.normalize("NFKC", str(s)).lower()
            for ch in ("・", "：", ":", "/", "?", "!", "　", "\\", "＆", "＃", "％", "_", "[", "]", "ー"):
                s = s.replace(ch, "")
            return s
        for _ow in (CONTENT / "works").glob("*.md"):
            _ow.unlink()
        _wpick: dict = {}
        for _wr in cands:
            for p in sorted((L1 / "runs" / _wr / "works").glob("*.md")):
                txt = p.read_bytes().decode("utf-8", "replace")
                _score = len(txt) + 500 * txt.count("[[full/") + 120 * txt.count("[[")
                _nk = _nkW(p.stem)
                cur0 = _wpick.get(_nk)
                if cur0 is None or _score > cur0[0]:
                    _wpick[_nk] = (_score, p, _wr, txt)
        for _nk, (_score, p, _wr, txt) in sorted(_wpick.items()):
            tm = re.search(r'title:\s*"([^"]+)"', txt)
            am = re.search(r'author:\s*"([^"]+)"', txt)
            ym = re.search(r'type:\s*"([^"]+)"', txt)
            emit(p, CONTENT / "works" / p.name, (tm.group(1) if tm else p.stem),
                 {"link_audit": _wr})
            wentries.append((tm.group(1) if tm else p.stem,
                              am.group(1) if am else "",
                              ym.group(1) if ym else ""))
        # 索引は完全再生成: site 全件走査の最新 index 供給 run のみ採用（旧ページ全掃除）
        for _oldix in (CONTENT / "works_index").glob("*.md"):
            _oldix.unlink()
        for _ix_run in reversed(cands):
            _id = L1 / "runs" / _ix_run / "index"
            if not _id.is_dir():
                continue
            for p in sorted(_id.glob("*.md")):
                tm = re.search(r'title:\s*"([^"]+)"', p.read_bytes().decode("utf-8", "replace"))
                emit(p, CONTENT / "works_index" / p.name, tm.group(1) if tm else p.stem,
                     {"link_audit": _ix_run})
            break
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
             "- 横断索引: [[works_top|創作索引（トップ）]] ／ 類型別: works_index ／ 作者別: [[widx_authors/|創作作者索引]]",
             "- 見方: [[guide|読み方ガイド]]", ""])
        ).encode("utf-8"))

        # works 作者索引・篇収容索引（run *_l1widx）
        icands = sorted(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1widx"))
        if icands:
            irun = icands[-1]
            # 作者・篇収容索引は完全再生成（旧ページ全掃除後に最新供給源のみ）
            for _d in ("widx_authors", "widx_units"):
                for _old in (CONTENT / _d).glob("*.md"):
                    _old.unlink()
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
    cands = sorted(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1en"))
    # 増分 run 運用: 最新 *_l1en run が本体、無い run の slug は後方 *_l1en 群＋基底 ENTITIES_RUN から継承
    if cands:
        ent_run = cands[-1]
    ent_inherit = list(reversed(cands[:-1]))
    if ent_run and ENTITIES_RUN and ENTITIES_RUN not in cands:
        ent_inherit.append(ENTITIES_RUN)
    ent_slugs = {}
    # 恒久: entities 面は全面掃除→供給 run 一元再生成（残留ファイルによる幽霊公開を根絶）
    for _p in (CONTENT / "entities").glob("*.md"):
        if _p.stem != "index":
            _p.unlink()
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
        _meta_re = _re.compile(r"抽出対象外|抽出対象とはしない")
        for p in sorted(src_dir.glob("*.md")):
            fm = p.read_bytes().decode("utf-8", "replace")
            tm = _re.search(r'term:\s*"([^"]+)"', fm)
            term = tm.group(1) if tm else p.stem
            if _meta_re.search(fm):
                _out = CONTENT / "entities" / p.name
                if _out.exists():
                    _out.unlink()  # メタ自己除外記述記事は公開面から除去
                continue
            emit(p, CONTENT / "entities" / p.name, term, {"link_audit": ENTITIES_AUDIT})
            emit_slugs[p.stem] = term
        for stem, p in sorted(inherited.items()):
            if stem in emit_slugs:
                continue
            fm = p.read_bytes().decode("utf-8", "replace")
            if _meta_re.search(fm):
                _out = CONTENT / "entities" / stem + ".md"
                if _out.exists():
                    _out.unlink()
                continue
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
        # 類型別索引
        idx = ["---", 'title: "実体索引"', "run: publish", "---", "", "# 実体索引", ""]
        _ae_n = len(list((CONTENT / "allusion_entities").glob("*.md")))
        n_ent = len([p for p in (CONTENT / "entities").glob("*.md") if p.stem != "index"])
        idx += [
            f"実体ページ **{n_ent}** 件（作中実体＝引用逐語検証・CN_CHAR 監査通過分のみ）＋実世界参照実体 [[allusion_entities/|{_ae_n} 名]]。",
            "",
            "生成方式: ①LLM 精密版（高密度上位実体・監査済）②決定論組立（台帳逐語引用＋ref・原文実在検証通過分）。",
            "抽出は二系統（allusion 側＝実世界参照／作中側＝創作物）で漏れを防ぐ。統合は候補提示まで、実統合は全話使用状況確認を要する。",
            "",
        ]
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

        # Lane N: 創作(works)⇄実体 漏れなき相互リンク＋実体索引の体系化（決定論）
        def _slugN(s0: str) -> str:
            s0 = str(s0)
            for a0, b0 in [("/", "_"), ("・", "_"), ("：", "_"), (":", "_"), ("?", "_"), ("!", "_"), ("　", "_"),
                           ("[", "【"), ("]", "】")]:
                s0 = s0.replace(a0, b0)
            return s0
        works_pages = [p for p in (CONTENT / "works").glob("*.md") if p.stem != "index"]
        w_titles: dict = {}
        w_texts: dict = {}
        for wp in works_pages:
            wt = wp.read_bytes().decode("utf-8", "replace")
            tm = _re.search(r'title:\s*"([^"]+)"', wt)
            w_titles[wp.stem] = tm.group(1) if tm else wp.stem
            w_texts[wp.stem] = wt
        w_cats: dict = {}
        for cp in sorted((CONTENT / "works_index").glob("*.md")):
            ct = cp.read_bytes().decode("utf-8", "replace")
            for mo in _re.finditer(r"\[\[works/([^\]|]+)", ct):
                w_cats.setdefault(mo.group(1), cp.stem)
        wlinks: dict = {}
        for wslug, wt in w_texts.items():
            hits = [sl for sl, term in ent_slugs.items()
                    if term and (term in w_titles.get(wslug, "") or term in wt)]
            wlinks[wslug] = hits
        # 実体ページへ 関連創作 欄を決定論付与
        by_ent_works: dict = {}
        for wslug, hits in wlinks.items():
            for sl in hits:
                by_ent_works.setdefault(sl, []).append(wslug)
        for sl in list(ent_slugs.values()):
            p = CONTENT / "entities" / f"{sl}.md"
            if not p.is_file():
                continue
            a = p.read_bytes().decode("utf-8", "replace")
            if "## 関連創作" in a:
                # 既存欄は常に除去して再構築（供給 slug 变更による坏 link を恒久防止）
                a = _re.sub(r"\n+## 関連創作.*?(?=\n## |\Z)", "", a, flags=_re.S)
                a = _re.sub(r"\n+## 関連創作.*$", "", a, flags=_re.S)
            ws = sorted(by_ent_works.get(sl, []))
            if ws:
                sec = "\n\n## 関連創作（作品ページ）\n\n" + "".join(
                    f"- [[works/{k}|{w_titles.get(k, k)}]]\n" for k in ws[:30])
                if len(ws) > 30:
                    sec += f"\n（全 {len(ws)} 作品・全一覧は[[entities_map/index|実体索引 体系版]]参照）\n"
                p.write_bytes((a.rstrip() + sec).encode("utf-8"))
        # 体系版索引: entities_map/（類型別・ページ分割 60 件・創作 cross-ref 付き）
        emap = CONTENT / "entities_map"
        emap.mkdir(exist_ok=True)
        for old in emap.glob("*.md"):
            old.unlink()
        emap_idx = ["---", 'title: "実体索引 体系版"', "run: publish", "---", "",
                    "# 実体索引 体系版（類型別細分）", "",
                    "実体を類型別に細分し、各実体の関連創作（作品ページ）への被リンク数を併記。", ""]
        for tname in sorted(by_type):
            slugs0 = [(t, s) for t, s in by_type[tname]]
            pages = [slugs0[i:i + 60] for i in range(0, len(slugs0), 60)]
            for pi, grp in enumerate(pages, 1):
                fn = f"{_slugN(tname)}_{pi}.md" if len(pages) > 1 else f"{_slugN(tname)}.md"
                body = ["---", f'title: "実体索引 体系版 {tname}"', "run: publish", "---", "",
                        f"# 類型: {tname}（{len(slugs0)} 件・{pi}/{len(pages)} ページ）", ""]
                for term, sl0 in grp:
                    nw = len(by_ent_works.get(sl0, []))
                    body.append(f"- [[entities/{sl0}|{term}]]" + (f" — 創作 {nw} 本" if nw else ""))
                nav = ["", "---", ""]
                for q in range(1, len(pages) + 1):
                    f2 = f"{_slugN(tname)}_{q}.md" if len(pages) > 1 else f"{_slugN(tname)}.md"
                    nav.append(f"[[entities_map/{f2}|{q}]]" if q != pi else f"**{q}**")
                body += [" ".join(nav), "", "[[entities_map/index|体系版 トップ]] ／ [[entities_index|実体索引]]", ""]
                (emap / fn).write_text("\n".join(body), encoding="utf-8")
            emap_idx.append(f"- [[entities_map/{_slugN(tname)}|{tname}]]（{len(by_type[tname])} 件）")
        # 創作 cross-ref（全 6453 作品を被リンク有無に関わらず全列挙・類型群）
        emap_idx += ["", "## 創作 全作品 cross-ref（漏れなき収録保証）", ""]
        unlinked = sorted(k for k, v in wlinks.items() if not v)
        groups: dict = {}
        for wslug in sorted(w_titles):
            g = w_cats.get(wslug, "その他創作")
            groups.setdefault(g, []).append(wslug)
        for g, ws0 in sorted(groups.items(), key=lambda x: -len(x[1])):
            emap_idx.append(f"### {g}（{len(ws0)} 作品）")
            emap_idx.append("")
            for i0 in range(0, len(ws0), 60):
                emap_idx.append("　" + " ／ ".join(
                    f"[[works/{k}|{w_titles[k]}]]" for k in ws0[i0:i0 + 60]))
                emap_idx.append("")
        emap_idx += ["", f"（実体から直接リンクされない作品 {len(unlinked)} 本も本書記に漏れなく収録。各作品は [[works_index/{w_cats.get(unlinked[0], 'その他創作')}|類型索引]]・[[works_top|創作索引]]・[[widx_authors|作者索引]]・[[widx_units|篇索引]] からも到達可能です）", ""] if unlinked else ["", "（全作品が実体ページから被リンクされています）", ""]
        (emap / "index.md").write_text("\n".join(emap_idx), encoding="utf-8")
        ei = CONTENT / "entities_index.md"
        ec0 = ei.read_text(encoding="utf-8")
        if "体系版" not in ec0:
            ei.write_text(ec0.rstrip() + "\n\n→ 体系版（類型別細分・創作 cross-ref 全作品収録）: [[entities_map/index|実体索引 体系版]]\n", encoding="utf-8")
        # entities/ フォルダノート
        (CONTENT / "entities" / "index.md").write_bytes(("\n".join(
            ["---", 'title: "実体索引（トップ）"', "run: publish", "---", "",
             "# 実体索引", "",
             "人物・物品・国・事件・概念など、作中実体のページ群（wiki 中核）。登場 2 以上を収録。",
             "各ページは概要・記述の流れ・関連実体・注目投稿（原文逐語リンク）・言及篇・共起実体を持ちます。", "",
             "- 類型別索引: [[entities_index|実体索引（類型別）]]",
             "- 見方: [[guide|読み方ガイド]]", ""])
        ).encode("utf-8"))

    AL_RUNS = ["20261122T0630_l1cnglyph"]
    try:
        _led0 = json.loads((WORK / "data/yuragi_allud_batches.json").read_text(encoding="utf-8"))
        for b0 in _led0.get("batches", []):
            if b0.get("status") == "done" and b0.get("run_dir") and b0["run_dir"] not in AL_RUNS:
                AL_RUNS.append(b0["run_dir"])
    except Exception:
        pass
    AL_RUN = "20261122T0630_l1cnglyph"
    n_allud_pages = 0
    AE_N = len(list((CONTENT / "allusion_entities").glob("*.md")))
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
        allud_month: dict = {}
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
                        if ref in bydate:
                            allud_month[bydate[ref][:7]] = allud_month.get(bydate[ref][:7], 0) + 1
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
                  f"対象篇: {n_allud}（抽出 run {len(AL_RUNS)} 本・全件実読監査込）",
                  f"参照項目累計: {sum(per_unit.values())} 件", "",
                  "| 類型 | 件数 |", "|---|---:|"]
            for k, v in sorted(kind_total.items(), key=lambda x: -x[1]):
                ix.append(f"| {k} | {v} |")
            ix += ["", "## 参照密度ランキング（上位 20 篇）", ""]
            for uidr, nr in sorted(per_unit.items(), key=lambda x: -x[1])[:20]:
                ix.append(f"- [[allusions/{uidr}|{uidr}]] — {nr} 件")
            ix += ["", "## 篇別", ""]
            for uid2 in sorted(per_unit):
                ix.append(f"- [[allusions/{uid2}|{uid2}]]（{per_unit[uid2]} 件）")
            ix += ["", "- 対象名の篇横断名寄せ: [[allusions_terms|実世界参照 対象名索引]]",
                   "- 主題別分類: [[allusions_map|実世界参照 主題分類索引]]", ""]
            (CONTENT / "allusions_index.md").write_text("\n".join(ix), encoding="utf-8")
        # Lane B4: units 記事から allusion 面への相互リンク（allusion 生成後に決定論で付与）
        for uid3 in sorted(per_unit):
            up3 = CONTENT / "units" / f"{uid3}.md"
            if up3.is_file():
                c3 = up3.read_text(encoding="utf-8", errors="replace")
                if f"allusions/{uid3}" not in c3:
                    up3.write_text(c3.rstrip() + f"\n\n→ 実世界参照（allusion）: [[allusions/{uid3}|この篇の実世界参照一覧]]\n", encoding="utf-8")
        # Lane B1: 対象名（term）の篇横断索引（決定論・正規化キー統合・2 篇以上を収録）
        term_ix: dict = {}
        for adir2 in adirs:
            for fp2 in sorted(adir2.glob("*.jsonl")):
                if fp2.stem == "gate_drops":
                    continue
                sp2 = adir2.parent / "suppressions.json"
                supp2: dict = {}
                if sp2.is_file():
                    for s2 in json.loads(sp2.read_text(encoding="utf-8")):
                        kk2 = str(s2.get("term", "")).strip().lower().replace("・", "").replace(" ", "")
                        supp2[(str(s2.get("unit", "")), kk2)] = s2
                for l2 in fp2.read_text(encoding="utf-8").splitlines():
                    if not l2.strip():
                        continue
                    it2 = json.loads(l2)
                    t2 = str(it2.get("term", "")).strip()
                    k2 = t2.strip().lower().replace("・", "").replace(" ", "")
                    if supp2.get((fp2.stem, k2), {}).get("action") == "drop":
                        continue
                    e2 = term_ix.setdefault(k2, {"disp": t2, "units": set(), "kinds": {}})
                    e2["units"].add(fp2.stem)
                    kd = str(it2.get("kind", "その他"))
                    e2["kinds"][kd] = e2["kinds"].get(kd, 0) + 1
        multi = [(v["disp"], k, v) for k, v in term_ix.items() if len(v["units"]) >= 2]
        multi.sort(key=lambda x: (-len(x[2]["units"]), x[0]))
        tx = [f'---\ntitle: "実世界参照 対象名索引"\nrun: publish\n---', "", "# 実世界参照 対象名索引（篇横断）", "",
              "同一の実世界対象が複数篇で参照されている名寄せ索引。正規化名（・・空白除去・小文字化）で機械統合し、suppressions 裁定を反映。", "",
              f"対象名: {len(multi)}（全対象名 {len(term_ix)}・2 篇以上）", ""]
        for disp0, k0, v0 in multi:
            us = "・".join(f"[[allusions/{u}|{u}]]" for u in sorted(v0["units"]))
            kd = "・".join(f"{a}{b}" for a, b in sorted(v0["kinds"].items(), key=lambda x: -x[1])[:3])
            tx.append(f"- **{disp0}**（{len(v0['units'])} 篇・{kd}）: {us}")
        tx.append("")
        tx.append("- 索引トップ: [[allusions_index|実世界参照 索引]]")
        (CONTENT / "allusions_terms.md").write_text("\n".join(tx), encoding="utf-8")
        # Lane B5: 主題分類索引（kind 最頻＋語彙キーで決定論桶分け）
        def _bucket(disp: str, kinds: dict) -> str:
            t = disp.lower()
            kw = [
                ("神話・宗教・悪魔", ("神話", "神々", "神", "悪魔", "天使", "仏", "シャイタン", "ゴエティア", "カバラ", "ヴェーダ", "神群")),
                ("文学作品", ("小説", "詩", "文学", "全集", "文庫")),
                ("映像・漫画・アニメ", ("映画", "アニメ", "漫画", "特撮", "ライダー", "戦隊", "ドラマ")),
                ("ゲーム・TRPG", ("ゲーム", "RPG", "ドラクエ", "ファイナルファンタジー", "モンスタ", "ギャザリング", "TRPG")),
                ("音楽・芸能", ("バンド", "歌手", "作曲家", "曲", "歌", "声優", "芸人", "落語")),
                ("学術・科学概念", ("理論", "仮説", "法則", "数", "素粒子", "心理学", "物理学", "化学", "生物学", "医学", "解釈")),
                ("ネットサービス・ソフトウェア", ("サイト", "掲示板", "ブラウザ", "ソフト", "SNS", "動画", "ウィキ", "Wikipedia", "mixi", "はてな")),
                ("歴史・実在人物", ("武将", "作家", "画家", "王", "皇帝", "戦争", "革命", "時代")),
                ("地名・地理", ("市", "県", "島", "大陸", "国立公園", "海峡", "タワー", "寺", "都市", "国")),
                ("ブランド・商品", ("株式会社", "ブランド", "製品", "商品", "ソフト株式会社")),
            ]
            best = max(kinds.items(), key=lambda x: x[1])[0] if kinds else "その他"
            kmap = {"神話": "神話・宗教・悪魔", "宗教": "神話・宗教・悪魔", "科学": "学術・科学概念",
                    "文学": "文学作品", "人物": "歴史・実在人物", "歴史": "歴史・実在人物",
                    "ゲーム": "ゲーム・TRPG", "地理": "地名・地理", "映像": "映像・漫画・アニメ",
                    "ブランド": "ブランド・商品", "音楽": "音楽・芸能"}
            if best in kmap:
                return kmap[best]
            for name, keys in kw:
                if any(k.lower() in t for k in keys):
                    return name
            return best
        buckets: dict = {}
        for k2, v2 in term_ix.items():
            b = _bucket(v2["disp"], v2["kinds"])
            buckets.setdefault(b, []).append((v2["disp"], len(v2["units"]), sorted(v2["units"])))
        mx = [f'---\ntitle: "実世界参照 主題分類"\nrun: publish\n---', "",
              "# 実世界参照 主題分類索引", "",
              "対象名を kind 最頻値と語彙キーで決定論分類（機械分類・裁定 drop 反映済）。", ""]
        for b in sorted(buckets, key=lambda x: -len(buckets[x])):
            names = sorted(buckets[b], key=lambda x: -x[1])
            mx.append(f"## {b}（{len(names)} 名）")
            mx.append("")
            for disp2, nu, us2 in names[:60]:
                show = "・".join(f"[[allusions/{u}|{u}]]" for u in us2[:4])
                more = f" 外{len(us2)}篇" if len(us2) > 4 else ""
                mx.append(f"- **{disp2}**（{nu} 篇）: {show}{more}")
            if len(names) > 60:
                mx.append(f"- …他 {len(names)-60} 名")
            mx.append("")
        mx.append("- 索引トップ: [[allusions_index|実世界参照 索引]]")
        (CONTENT / "allusions_map.md").write_text("\n".join(mx), encoding="utf-8")
        # Lane B6: 各 allusion 篇へ「篇横断対象名」セクションを決定論付与（全対象名の 2 篇以上）
        multi_keys = {k0 for k0, v0 in term_ix.items() if len(v0["units"]) >= 2}
        for uid6 in sorted(per_unit):
            up6 = CONTENT / "allusions" / f"{uid6}.md"
            if not up6.is_file():
                continue
            c6 = up6.read_text(encoding="utf-8", errors="replace")
            if "篇横断対象名" in c6:
                continue
            myterms = []
            for adir6 in adirs:
                f6 = adir6 / f"{uid6}.jsonl"
                if not f6.is_file():
                    continue
                s6 = adir6.parent / "suppressions.json"
                sup6: dict = {}
                if s6.is_file():
                    for s in json.loads(s6.read_text(encoding="utf-8")):
                        kk = str(s.get("term", "")).strip().lower().replace("・", "").replace(" ", "")
                        sup6[(str(s.get("unit", "")), kk)] = s
                for l6 in f6.read_text(encoding="utf-8").splitlines():
                    if not l6.strip():
                        continue
                    it6 = json.loads(l6)
                    t6 = str(it6.get("term", "")).strip()
                    k6 = t6.strip().lower().replace("・", "").replace(" ", "")
                    if k6 not in multi_keys:
                        continue
                    if sup6.get((uid6, k6), {}).get("action") == "drop":
                        continue
                    nu6 = len(term_ix[k6]["units"])
                    if t6 not in [x[0] for x in myterms]:
                        myterms.append((t6, nu6))
            myterms.sort(key=lambda x: (-x[1], x[0]))
            if not myterms:
                continue
            top6 = "・".join(f"{d}（{n}）" for d, n in myterms[:15])
            up6.write_text(c6.rstrip() + f"\n\n### 篇横断対象名（2 篇以上）\n\n- {top6}\n\n→ 名寄せ: [[allusions_terms|対象名索引]] ／ 主題: [[allusions_map|主題分類索引]]\n", encoding="utf-8")

        # Lane C1: topics 記事 ⇄ allusion 対象名の相互参照（決定論・監査 drop 反映済索引照合）
        for tp in sorted((CONTENT / "topics").glob("*.md")):
            if tp.stem == "index":
                continue
            tc = tp.read_text(encoding="utf-8", errors="replace")
            if "実世界参照（allusion）" in tc:
                continue
            ttm = re.search(r'term:\s*"([^"]+)"', tc)
            tk = (ttm.group(1) if ttm else tp.stem).strip().lower().replace("・", "").replace(" ", "")
            ent = term_ix.get(tk)
            if not ent:
                continue
            us = sorted(ent["units"])
            links = "・".join(f"[[allusions/{u6}|{u6}]]" for u6 in us[:12])
            more = f" 他 {len(us) - 12} 篇" if len(us) > 12 else ""
            tp.write_text(tc.rstrip() + f"\n\n### 実世界参照（allusion）\n\n- 「{ent['disp']}」は実世界対象として {len(us)} 篇に抽出: {links}{more}\n\n→ 索引: [[allusions_index|実世界参照 索引]] ／ 名寄せ: [[allusions_terms|対象名索引]]\n", encoding="utf-8")

        # Lane C3: 年表へ実世界参照の月別密度を追記（監査項目引用ポストの実日付から決定論集計）
        if allud_month:
            cp4 = CONTENT / "chronology.md"
            if cp4.is_file():
                c4 = cp4.read_text(encoding="utf-8", errors="replace")
                if "実世界参照の密度" not in c4:
                    ml = ["", "## 実世界参照の密度（月別）", "",
                          "監査収束済 allusion 項目の引用ポスト（ref の実日付）を全件集計。参加者が持ち込む実世界参照の総量変化が読み取れる。", ""]
                    for y4 in sorted({m4[:4] for m4 in allud_month}):
                        months4 = [f"{int(m4[5:7])}月 {allud_month[m4]}" for m4 in sorted(allud_month) if m4.startswith(y4)]
                        ml.append(f"**{y4} 年**　" + " ／ ".join(months4))
                        ml.append("")
                    cp4.write_text(c4.rstrip() + "\n" + "\n".join(ml) + "\n", encoding="utf-8")

        # Lane D: 実世界参照 対象名の実体化（2 篇以上・決定論・drop 反映・引用付き）
        ents_q: dict = {}
        for adir7 in adirs:
            s7 = adir7.parent / "suppressions.json"
            sup7: dict = {}
            if s7.is_file():
                for s in json.loads(s7.read_text(encoding="utf-8")):
                    kk7 = str(s.get("term", "")).strip().lower().replace("・", "").replace(" ", "")
                    sup7[(str(s.get("unit", "")), kk7)] = s
            for fp7 in sorted(adir7.glob("*.jsonl")):
                if fp7.stem == "gate_drops":
                    continue
                for l7 in fp7.read_text(encoding="utf-8").splitlines():
                    if not l7.strip():
                        continue
                    it7 = json.loads(l7)
                    t7 = str(it7.get("term", "")).strip()
                    k7 = t7.strip().lower().replace("・", "").replace(" ", "")
                    if sup7.get((str(it7.get("unit", "")), k7), {}).get("action") == "drop":
                        continue
                    e7 = ents_q.setdefault(k7, {"disp": t7, "units": {}, "usage": "", "kinds": {}})
                    u7 = str(it7.get("unit", ""))
                    e7["units"].setdefault(u7, [])
                    for q7 in it7.get("quotes", []):
                        if len(e7["units"][u7]) < 2:
                            e7["units"][u7].append((str(q7.get("ref", "")), str(q7.get("q", ""))))
                    if not e7["usage"]:
                        e7["usage"] = str(it7.get("usage", "")).strip()
                    kd7 = str(it7.get("kind", "その他"))
                    e7["kinds"][kd7] = e7["kinds"].get(kd7, 0) + 1

        def _slug7(s: str) -> str:
            s = str(s).strip()
            for a, b in [("/", "_"), ("\\", "_"), ("&", "＆"), ("#", "＃"), ("%", "％"),
                         ("・", "_"), ("：", "_"), (":", "_"), ("?", "_"), ("!", "_"), ("　", "_"),
                         ("[", "【"), ("]", "】")]:
                s = s.replace(a, b)
            return s

        ae = CONTENT / "allusion_entities"
        ae.mkdir(exist_ok=True)
        # 恒久: AE 面も全面掃除→台帳一元再生成（残留幽霊ページを根絶）
        for _ap in ae.glob("*.md"):
            _ap.unlink()
        used_slugs: dict = {}
        d_multi = {k7: v7 for k7, v7 in ents_q.items() if len(v7["units"]) >= 2}
        d_single = {k7: v7 for k7, v7 in ents_q.items() if len(v7["units"]) == 1}
        for k7, v7 in sorted(d_multi.items(), key=lambda x: (-len(x[1]["units"]), x[0])):
            kinds7 = v7["kinds"]
            best7 = max(kinds7.items(), key=lambda x: x[1])[0] if kinds7 else "その他"
            us7 = sorted(v7["units"].items())
            disp7 = v7["disp"]
            slug7 = _slug7(disp7)
            used_slugs[slug7] = used_slugs.get(slug7, 0) + 1
            if used_slugs[slug7] > 1:
                slug7 = f"{slug7}_{used_slugs[slug7]}"
            body7 = [f'---\ntitle: "{disp7}"\nrun: publish\n---', "",
                     f"# {disp7}（実世界参照 実体）", "",
                     f"分類: {best7} ／ 篇横断: {len(us7)} 篇", ""]
            if v7["usage"]:
                body7 += [v7["usage"], ""]
            body7 += ["## 使用状況（引用逐語・ref 付き）", ""]
            for u7, ql7 in us7:
                body7.append(f"### [[allusions/{u7}|{u7}]]")
                body7.append("")
                for r7, q7 in ql7[:2]:
                    pno7 = r7.split(":")[-1] if ":" in r7 else ""
                    body7.append(f"> 「{q7[:200]}」 [[full/{u7}#post-{pno7}|{r7}]]")
                body7.append("")
            body7 += ["---", "",
                      "→ [[allusion_entities/|実世界参照 実体索引]] ／ [[allusions_index|実世界参照 索引]] ／ [[allusions_terms|対象名索引]]", ""]
            (ae / f"{slug7}.md").write_text("\n".join(body7), encoding="utf-8")
        # 単篇のみの対象名も実体記事化（決定論・逐語引用＋ref・LLM 生成なし）
        for k7, v7 in sorted(d_single.items()):
            kinds7 = v7["kinds"]
            best7 = max(kinds7.items(), key=lambda x: x[1])[0] if kinds7 else "その他"
            us7 = sorted(v7["units"].items())
            disp7 = v7["disp"]
            slug7 = _slug7(disp7)
            used_slugs[slug7] = used_slugs.get(slug7, 0) + 1
            if used_slugs[slug7] > 1:
                slug7 = f"{slug7}_{used_slugs[slug7]}"
            u7, ql7 = us7[0]
            body7 = [f'---\ntitle: "{disp7}"\nrun: publish\n---', "",
                     f"# {disp7}（実世界参照 実体）", "",
                     f"分類: {best7} ／ 出現: 1 篇（{u7}）", ""]
            if v7["usage"]:
                body7 += [v7["usage"], ""]
            body7 += ["## 使用状況（引用逐語・ref 付き）", ""]
            for r7, q7 in ql7[:3]:
                pno7 = r7.split(":")[-1] if ":" in r7 else ""
                body7.append(f"> 「{q7[:200]}」 [[full/{u7}#post-{pno7}|{r7}]]")
            body7 += ["", "---", "",
                      "→ [[allusion_entities/|実世界参照 実体索引]] ／ [[allusions_index|実世界参照 索引]]", ""]
            (ae / f"{slug7}.md").write_text("\n".join(body7), encoding="utf-8")
        byk: dict = {}
        for k7, v7 in ents_q.items():
            kinds7 = v7["kinds"]
            best7 = max(kinds7.items(), key=lambda x: x[1])[0] if kinds7 else "その他"
            byk.setdefault(best7, []).append((v7["disp"], len(v7["units"])))
        ix7 = [f'---\ntitle: "実世界参照 実体索引"\nrun: publish\n---', "",
               "# 実世界参照 実体索引（全対象名 実体化）", "",
               f"作中に持ち込まれた**実世界の対象名**の実体化: **{len(ents_q)} 名（全対象名を記事化）** — 2 篇以上 {len(d_multi)} 名／単篇のみ {len(d_single)} 名。各ページは使用状況の逐語引用＋ref 出典付き（決定論生成・drop 反映済）。", "",
               "収録基準: 監査収束済の全実世界対象名。2 篇以上は篇横断一覧、単篇は該当篇の使用状況と引用を収録。"]
        for b7 in sorted(byk, key=lambda x: -len(byk[x])):
            ix7.append("")
            ix7.append(f"## {b7}（{len(byk[b7])} 名）")
            ix7.append("")
            for d7, n7 in sorted(byk[b7], key=lambda x: (-x[1], x[0])):
                ix7.append(f"- [[allusion_entities/{_slug7(d7)}|{d7}]]（{n7} 篇）")
        ix7 += ["", "- 篇側索引: [[allusions_index|実世界参照 索引]]", "- 名寄せ: [[allusions_terms|対象名索引]]", "- 主題分類: [[allusions_map|主題分類索引]]", ""]
        (ae / "index.md").write_text("\n".join(ix7), encoding="utf-8")
        ep = CONTENT / "entities_index.md"
        if ep.is_file():
            ec = ep.read_text(encoding="utf-8", errors="replace")
            if "実世界参照 実体" not in ec:
                ep.write_text(ec.rstrip() + f"\n\n## 実世界参照 実体（{len(ents_q)} 名・全対象名）\n\n上記は作中実体群。実世界参照の対象名（神話・文学作品・実在人物・ゲーム 他）は [[allusion_entities/|実世界参照 実体索引]] に**全件実体化**しています（2 篇以上 {len(d_multi)} 名＋単篇 {len(d_single)} 名・逐語引用＋ref 付き）。創作記述は works 面（作品ページ）で実体化済。\n", encoding="utf-8")

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
    # Lane T: entities ⇄ allusion_entities 同一名クロスリンク（決定論・frontmatter term 完全一致）
    try:
        import re as _re2
        _ent_ix = {}
        for _p in (CONTENT / "entities").glob("*.md"):
            if _p.stem == "index":
                continue
            _tm = _re2.search(r'term:\s*"([^"]+)"', _p.read_text(encoding="utf-8", errors="replace"))
            if _tm:
                _ent_ix.setdefault(_tm.group(1).strip(), _p.stem)
        _ae_ix = {}
        for _p in (CONTENT / "allusion_entities").glob("*.md"):
            if _p.stem == "index":
                continue
            _txt_ae = _p.read_text(encoding="utf-8", errors="replace")
            _tm = _re2.search(r'term:\s*"([^"]+)"', _txt_ae)
            if not _tm:
                _tm = _re2.search(r'title:\s*"([^"]+)"', _txt_ae)
            if _tm:
                _ae_ix.setdefault(_tm.group(1).strip(), _p.stem)
        _n_cross = 0
        _sep = chr(10)
        for _term in _ent_ix.keys() & _ae_ix.keys():
            _es, _as = _ent_ix[_term], _ae_ix[_term]
            _pe = CONTENT / "entities" / (_es + ".md")
            _pa = CONTENT / "allusion_entities" / (_as + ".md")
            _te = _pe.read_text(encoding="utf-8", errors="replace")
            if "同一名（別面）" not in _te:
                _tail = _sep * 2 + "## 同一名（別面）" + _sep * 2 + "実世界参照面に同一名の独立記事: [[allusion_entities/" + _as + "|" + _term + "]]（作中创作面と実世界参照面の住み分け）" + _sep
                _pe.write_text(_te.rstrip() + _tail, encoding="utf-8")
                _n_cross += 1
            _ta = _pa.read_text(encoding="utf-8", errors="replace")
            if "同一名（別面）" not in _ta:
                _tail2 = _sep * 2 + "## 同一名（別面）" + _sep * 2 + "作中実体面に同一名の独立記事: [[entities/" + _es + "|" + _term + "]]" + _sep
                _pa.write_text(_ta.rstrip() + _tail2, encoding="utf-8")
                _n_cross += 1
        # topics ⇄ 実体面（entities/allusion_entities）同一名セクション
        _n_top = 0
        for _tp in (CONTENT / "topics").glob("*.md"):
            if _tp.stem == "index":
                continue
            _tt = _tp.read_text(encoding="utf-8", errors="replace")
            _tm2 = _re2.search(r'term:\s*"([^"]+)"', _tt)
            if not _tm2:
                _tm2 = _re2.search(r'title:\s*"([^"]+)"', _tt)
            if not _tm2:
                continue
            _w = _tm2.group(1).strip()
            _ex = _ent_ix.get(_w)
            _ax = _ae_ix.get(_w)
            if not (_ex or _ax):
                continue
            if "実体面（同一名）" in _tt:
                continue
            _sep2 = chr(10)
            _link = []
            if _ex:
                _link.append("[[entities/" + _ex + "|作中実体面]]")
            if _ax:
                _link.append("[[allusion_entities/" + _ax + "|実世界参照面]]")
            _tp.write_text(_tt.rstrip() + _sep2 * 2 + "## 実体面（同一名）" + _sep2 * 2 + "／ ".join(_link) + _sep2, encoding="utf-8")
            _n_top += 1
        print("laneT topics-cross:", _n_top)
        print("laneT cross-links:", _n_cross)
    except Exception as _e:
        print("laneT skip:", type(_e).__name__, _e)

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
- [[allusions_index|実世界参照索引]] — 作中に持ち込まれた実世界の神話・宗教・文学・ゲーム等の横断参照（{n_allud_pages} 篇・全件実読監査込）

## 節

| 節 | 内容 | 規模 | 入口 |
|---|---|---|---|
| 篇記事（units） | L1 版の要約・整理記事 | {n_units} 篇 | [[nav|篇索引]] |
| 原文全文（full） | 投稿全文そのまま・投稿単位 permalink | {n_full} 篇 | [[full/index|full 索引]] |
| 自由記述（free） | 制約なし自由記述記事 | {n_free} 篇 | [[free_index|自由記述索引]] |
| 実体（entities） | 人物・物品・国・事件・概念 | {n_ent} 件 | [[entities_index|類型別索引]] |
| 創作（works） | 散在する詩・短編・設定文 | {n_works:,} 作品 | [[works_top|創作索引]] |
| 話題（topics） | 話題・語句（出現 3 以上） | {n_topics} 件 | [[topics/index|topics 索引]] |
| 投稿者（authors） | 主要投稿者（投稿 10 以上） | {n_auth} 名 | [[authors/index|authors 索引]] |
| 日記（flicker） | Hatena Flicker 関連日記 | {n_fl} 作者・{n_fl_posts} 投稿 | [[flicker_index|日記索引]] |
| 年表 | 月別集計・語句初出 | {date_lo} 〜 {date_hi} | [[chronology|年表]] |
| 実世界参照（allusions） | 作中の実世界対象（神話・宗教・文学・映像・ゲーム・ブランド 他）への横断参照。逐語引用＋ ref 出典 | {n_allud_pages} 篇 | [[allusions_index|実世界参照索引]] |
| 実世界参照 実体 | 対象名を全件記事化（使用状況引用付き） | {AE_N} 名 | [[allusion_entities/|実世界参照 実体索引]] |

## 版（三つの面）

- **L1 版（当サイト主要面）**: 要約・整理記事。引用は 100 字以内＋ ref アンカー（原文ファイルへのリンク付き）。
- **自由記述版（制約なし）**: [[free_index|free]] — L1 と原文をもとに構造制約なしで記述。引用は原文からの逐語のみ・全記事 ref 付き。
- **原文全文版**: [[full/index|full]] — 各篇の投稿全文をそのまま掲載（投稿単位アンカー付き）。

三版は相互リンクで結ばれています。投稿の著作権は各投稿者に帰属します（[[license|ライセンス]]・削除対応方針）。

## 統計（L0 台帳 {led.name}）

- 篇 {stats['units']} ／ 投稿 {stats['posts']:,} ／ 投稿群 {stats['chains']:,}（LLM 要約付き）／ 投稿者 {stats['authors']:,} 名 ／ 本文 {stats['chars_body']:,} 字
- 創作記述 → 作品ページ {n_works:,}・収録投稿は permalink 付き原文逐語
- 実体ページ {n_ent}（作中実体＝引用逐語検証・CN_CHAR 監査通過分）＋ 実世界参照実体 {AE_N} 名（対象名全件記事化）・自由記述記事 {n_free}・全記事 LLM 全量監査 100% 収束
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
| 原文全文版 | `full/` | 投稿全文をそのまま掲載。`#post-N` アンカー付き（多数投稿の篇は p2・p3… に分頁） |

## 実世界参照層（allusions）

作中に参加者が持ち込んだ**実世界の対象**（神話・宗教・文学・映像・ゲーム・ブランド・地名・学術概念 他）への参照を、`allusions/` 面に対象名単位で横断索引化しています。各項目は原文逐語引用＋ ref 出典リンク付きで、機械抽出後に**全件実読監査**（実在参照の明示があるか／作中命名・類別語・場面小道具の区別）を通ったものだけを公開しています。

- 篇横断の名寄せ: [[allusions_terms|対象名索引]]（2 篇以上の対象名）
- 主題分類: [[allusions_map|主題分類索引]]（神話・文学・学術・ゲーム 等の機械分類）
- 対象名の記事化: [[allusion_entities/|実世界参照 実体索引]]（全対象名 {AE_N} 名・使用状況の逐語引用＋ref 付き）
- 各篇記事末尾から「この篇の実世界参照一覧」へ相互リンク済み

## 引用と出典リンク

- **ref 形式 `YJ-T001:123`**: 「篇 YJ-T001 の投稿 123」を指す原文参照。リンク先は原文データ
  （GitHub の raw/ ③ 投稿チャンクファイル）です。
- **投稿 permalink**: 原文全文版の各投稿は `.../full/YJ-T001/p3#post-257` 形式の固定 URL を持ちます
  （`p3` は分頁、`#post-257` は投稿アンカー）。L1 版・創作ページからの引用リンクもここを指します。
- **実体ページ（二層）**: ①精密版（高密度上位語・LLM 生成＋全量監査）は概要・記述の流れ・関連実体・注目投稿・言及篇・共起実体を持ちます。②網羅版（決定論組立）は台帳由来の篇横断使用状況＋逐語引用＋ref 出典を持ち、引用がすべて原文に実在することを機械検証（NFKC 照合）・簡体字混入検査（CN_CHAR）を通過した分のみ収録しています。同一名で作中面／実世界参照面がある場合は相互リンク付き。

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
description: "コーパス統計ダッシュボード（出典別・年別・上位投稿者・類型分布）"
run: publish
---

# 統計

L0 台帳 {led.name} 由来の決定論集計。詳細は [[chronology|年表]]・[[nav|篇索引]]。

## 出典別

| 出典 | 篇 | 投稿 |
|---|---|---|
{rows_src.rstrip()}

## 年別投稿数

| 年 | 投稿数 | 最多月 |
|---|---|---|
{year_rows.rstrip()}

## 上位投稿者（top 20）

| 投稿者 | 投稿数 |
|---|---|
{auth_rows.rstrip()}

## 実体の類型分布

| 類型 | 件数 |
|---|---|
{ent_type_rows.rstrip()}

## 創作の類型分布（top 15）

| 類型 | 作品数 |
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

    # Lane V: AE 対象名 ⇄ works 作品名 被引用クロリンク（同Title 完全一致・決定論）
    import unicodedata as _uv
    def _vkey(s):
        return _uv.normalize("NFKC", str(s)).strip()
    wk_by_title = {}
    for _wp in (CONTENT / "works").glob("*.md"):
        if _wp.stem == "index":
            continue
        _tm = _re.search(r'title:\s*"([^"]+)"', _wp.read_text(encoding="utf-8", errors="replace"))
        if _tm:
            wk_by_title.setdefault(_vkey(_tm.group(1)), _wp.stem)
    _v_linked = 0
    for _ap in sorted((CONTENT / "allusion_entities").glob("*.md")):
        if _ap.stem == "index":
            continue
        _at = _ap.read_text(encoding="utf-8", errors="replace")
        _tm2 = _re.search(r'title:\s*"([^"]+)"', _at)
        if not _tm2:
            continue
        _k = _vkey(_tm2.group(1))
        _wslug = wk_by_title.get(_k)
        if not _wslug or "## 作中で参照される創作" in _at:
            continue
        _ap.write_text(_at.rstrip() + f"\n\n## 作中で参照される創作\n\n- 同名の創作ページ: [[works/{_wslug}|{_tm2.group(1)}]]（作中の創作作品としての言及。実世界参照としての解析は本ページ参照）\n", encoding="utf-8")
        _v_linked += 1
        _wp = CONTENT / "works" / f"{_wslug}.md"
        _wt = _wp.read_text(encoding="utf-8", errors="replace")
        if "## 実世界参照 実体" not in _wt:
            _wp.write_text(_wt.rstrip() + f"\n\n## 実世界参照 実体\n\n- 本作名と同一の対象名が実世界参照として解析されています: [[allusion_entities/{_ap.stem}|{_tm2.group(1)}]]\n", encoding="utf-8")
    counts["laneV_crosslink"] = _v_linked

    # 恒久 CN 安全網: 生成された全コンテンツページを日本語標準字体へ正規化（簡体字混入 0 を保証）。
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cn_gate import jp_fix as _jp
    for _p in CONTENT.rglob("*.md"):
        _t0 = _p.read_text(encoding="utf-8", errors="replace")
        _t1 = _jp(_t0)
        if _t1 != _t0:
            _p.write_text(_t1, encoding="utf-8")

    # 恒久 リンク修復網: 全 wiki リンクを現実ファイルへ検証・remap（slug 旧来流残留を根絶）
    import unicodedata as _udx
    _folders = {}
    for _d in CONTENT.iterdir():
        if _d.is_dir():
            _folders[_d.name] = {q.stem: q for q in _d.glob("*.md")}
    _folders["."] = {q.stem for q in CONTENT.glob("*.md")} if False else {q.stem: q for q in CONTENT.glob("*.md")}

    # グリフ変異ペア自動検出: 同一 stem で CJK 異字体が 1 字だけ異なるファイル組を相互正規化
    from collections import Counter as _C2
    _all_stems = []
    for _d, _mp in _folders.items():
        _all_stems.extend(_mp.keys())
    _variant = {}
    _by_len = {}
    for _s in _all_stems:
        _k0 = _udx.normalize("NFKC", _s).lower()
        _by_len.setdefault((len(_k0), _k0.replace("_", "")[:2] + _k0.replace("_", "")[-2:]), []).append(_s)
    for _grp in _by_len.values():
        for _i in range(len(_grp)):
            for _j in range(_i + 1, len(_grp)):
                _a, _b = _grp[_i], _grp[_j]
                _na, _nb = _udx.normalize("NFKC", _a).lower(), _udx.normalize("NFKC", _b).lower()
                if len(_na) != len(_nb):
                    continue
                _diff = [(x, y) for x, y in zip(_na, _nb) if x != y]
                if len(_diff) == 1 and all(ord(x) > 0x2000 for x, y in _diff):
                    (x, y) = _diff[0]
                    # canonical: 出現数の多いグリフへ統一
                    _cx = sum(1 for s2 in _all_stems if x in _udx.normalize("NFKC", s2).lower())
                    _cy = sum(1 for s2 in _all_stems if y in _udx.normalize("NFKC", s2).lower())
                    _tgt = x if _cx >= _cy else y
                    _src = y if _cx >= _cy else x
                    _variant[_src] = _tgt

    def _normkey(s):
        s = _udx.normalize("NFKC", s)
        for _vc, _vt in _variant.items():
            if _vc in s:
                s = s.replace(_vc, _vt)
        for ch in ("・", "：", ":", "/", "?", "!", "　", "\\", "＆", "＃", "％", "_", "ー"):
            s = s.replace(ch, "")
        return s.lower()

    _idx = {f: {_normkey(k): k for k in d} for f, d in _folders.items()}
    import re as _rx
    _fixed = _dropped = 0
    # 対象は解析面のみ（full/works/allusions の原文マークアップ [[語]] は編集しない）
    _scan_targets = []
    for _fd in ("entities", "entities_map", "allusion_entities"):
        _scan_targets.extend((CONTENT / _fd).glob("*.md"))
    _scan_targets.extend(CONTENT.glob("*.md"))
    for _p in _scan_targets:
        _t = _p.read_text(encoding="utf-8", errors="replace")
        if "[[" not in _t:
            continue
        def _rep(mo):
            nonlocal _fixed, _dropped
            if mo.group(2).startswith("#"):
                return mo.group(0)  # ページ内アンカーは対象外
            tgt = mo.group(2).split("#")[0].strip()
            pipe = mo.group(3) or ""
            parts = tgt.split("/", 1)
            fld = "." if len(parts) == 1 else parts[0]
            base = parts[-1]
            dmap = _folders.get(fld)
            if dmap is None:
                return mo.group(1)  # 対象フォルダ自体が無ければ原文維持（表示のみ）
            if base in dmap:
                return mo.group(0)
            lk = _normkey(base)
            ik = _idx.get(fld, {}).get(lk)
            if ik is None and lk:
                cand = [k for k in _idx.get(fld, {}) if lk in k]
                if len(cand) == 1:
                    ik = cand[0]
                elif not cand and len(lk) >= 4:
                    pref = lk[: len(lk) - 1]
                    cand = [k for k in _idx.get(fld, {}) if k.startswith(pref)]
                    if len(cand) == 1:
                        ik = cand[0]
            if ik:
                _fixed += 1
                return f"{mo.group(1)}{fld if fld != '.' else ''}{'' if fld=='.' else '/'}{ik}{pipe}]]"
            # クロス検索: 他フォルダに正体があれば remap、無ければ表示テキスト化（壊リンク 0 保証）
            if fld != ".":
                lk2 = _normkey(base)
                for f2, d2 in _idx.items():
                    if f2 == fld:
                        continue
                    ik2 = d2.get(lk2)
                    if ik2 is None and lk2:
                        cd2 = [k for k in d2 if lk2 in k]
                        if len(cd2) == 1:
                            ik2 = cd2[0]
                    if ik2:
                        _fixed += 1
                        pfx2 = "" if f2 == "." else f2 + "/"
                        return f"{mo.group(1)}{pfx2}{ik2}{pipe}]]"
                _dropped += 1
                disp2 = (pipe[1:] if pipe else base)
                return disp2
            return mo.group(0)  # 原文マークアップ（引用中の [[語]]）は表示テキストとして保持
        _t2 = _rx.sub(r"(\[\[)([^\]|]+)(\|[^\]]*)?\]\]", _rep, _t)
        if _t2 != _t:
            _p.write_text(_t2, encoding="utf-8")
    print(f"[linkfix] remapped={_fixed} dropped={_dropped}")

    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

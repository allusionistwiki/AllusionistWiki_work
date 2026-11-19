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
UNITS_AUDIT = "20261117T2300_l1aud"
TOPICS_RUN = "20261119T1140_l1tp"
TOPICS_AUDIT = "20261119T1141_l11tpaud"
AUTHORS_RUN = "20261119T2003_l1au"
AUTHORS_AUDIT = "20261119T2025_l11auaud"
CHRONO_RUN = "20261118T0149_l1ch"
FULL_RUN = "20261118T1948_l1full"
ENTITIES_RUN = None  # entities 生成後に設定（runs 内の最新 _l1en を自動検出）


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

    # ref → raw ファイル URL（③ 行から）
    ref_url = {}
    unit_dir_rel = {}
    for sf in RAW_BBS.glob("**/structured.jsonl"):
        rel = sf.parent.relative_to(RAW_BBS).as_posix()
        m = meta_of(sf)
        if m:
            unit_dir_rel[m["unit_id"]] = rel
        for r in jl(sf):
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
            up.write_bytes((cur.rstrip("\r\n") + f"\n\n---\n関連: [[full/{uid}|原文全文（制約なし版）]] ／ [[free/{uid}|自由記述記事]]\n").encode("utf-8"))

    # free（制約なし自由記述記事・LLM 全量監査 100% 収束）
    FREE_RUN = "20261119T0014_l1free"
    FREE_AUDIT = "20261119T0009_l11freeaud"
    for p in sorted((L1 / "runs" / FREE_RUN / "units").glob("*.md")):
        uid = p.stem
        t = units.get(uid, {}).get("title", uid)
        emit(p, CONTENT / "free" / p.name, t, {"link_audit": FREE_AUDIT}, uid=uid)
        fp = CONTENT / "free" / p.name
        cur = fp.read_bytes().decode("utf-8", "replace")
        if "[[units/" not in cur:
            fp.write_bytes((cur.rstrip("\r\n") + f"\n\n---\n関連: [[units/{uid}|L1 版記事]] ／ [[full/{uid}|原文全文]]\n").encode("utf-8"))
    fidx = CONTENT / "free_index.md"
    fl = ["---", 'title: "自由記述索引"', "run: publish", "---", "", "# 自由記述記事（制約なし版）", "",
          "L1 版記事と原文をもとに、L1 の構造制約なしで自由記述した記事群（LLM 全量監査 100% 収束）。", ""]
    for p in sorted((CONTENT / "free").glob("*.md")):
        uid = p.stem
        t = units.get(uid, {}).get("title", uid)
        fl.append(f"- [[free/{uid}|{t}]]")
    fidx.write_bytes("\n".join(fl).encode("utf-8"))

    # topics / authors
    for p in sorted((L1 / "runs" / TOPICS_RUN / "topics").glob("*.md")):
        fm = p.read_bytes().decode("utf-8", "replace")
        tm = re.search(r'term:\s*"([^"]+)"', fm)
        emit(p, CONTENT / "topics" / p.name, tm.group(1) if tm else p.stem, {"link_audit": TOPICS_AUDIT})
    for p in sorted((L1 / "runs" / AUTHORS_RUN / "authors").glob("*.md")):
        fm = p.read_bytes().decode("utf-8", "replace")
        am = re.search(r'author:\s*"([^"]+)"', fm)
        emit(p, CONTENT / "authors" / p.name, am.group(1) if am else p.stem, {"link_audit": AUTHORS_AUDIT})

    # chronology
    cp = L1 / "runs" / CHRONO_RUN / "chrono" / "chronology.md"
    emit(cp, CONTENT / "chronology.md", "年表", {"link_audit": CHRONO_RUN})

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
            aidx = CONTENT / "widx_authors.md"
            al = ["---", 'title: "創作作者索引"', "run: publish", "---", "",
                  "# 創作作者索引（作品掲載数順）", ""]
            al += [f"- [[widx_authors/{p.stem}|{p.stem}]]"
                   for p in sorted((L1 / "runs" / irun / "author_index").glob("*.md"))
                   if p.stem != "index"]
            aidx.write_bytes("\n".join(al).encode("utf-8"))
            for p in sorted((L1 / "runs" / irun / "unit_index").glob("*.md")):
                emit(p, CONTENT / "widx_units" / p.name, p.stem, {"link_audit": irun})
            uidx = CONTENT / "widx_units.md"
            ul = ["---", 'title: "創作篇収容索引"', "run: publish", "---", "",
                  "# 創作篇収容索引", ""]
            ul += [f"- [[widx_units/{p.stem}|{p.stem}]]"
                   for p in sorted((L1 / "runs" / irun / "unit_index").glob("*.md"))]
            uidx.write_bytes("\n".join(ul).encode("utf-8"))

    # entities（实体ページ・wiki 中核）
    import re as _re
    ent_run = ENTITIES_RUN
    if not ent_run:
        cands = sorted(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1en"))
        ent_run = cands[-1] if cands else None
    ent_slugs = {}
    if ent_run:
        import unicodedata
        def _slugify_norm(s):
            return unicodedata.normalize("NFKC", s).strip()
        src_dir = L1 / "runs" / ent_run / "entities"
        for p in sorted(src_dir.glob("*.md")):
            fm = p.read_bytes().decode("utf-8", "replace")
            tm = _re.search(r'term:\s*"([^"]+)"', fm)
            if tm:
                ent_slugs[_slugify_norm(tm.group(1))] = p.stem
        for p in sorted(src_dir.glob("*.md")):
            fm = p.read_bytes().decode("utf-8", "replace")
            tm = _re.search(r'term:\s*"([^"]+)"', fm)
            ty = _re.search(r'type:\s*"([^"]+)"', fm)
            term = tm.group(1) if tm else p.stem
            emit(p, CONTENT / "entities" / p.name, term, {"link_audit": ent_run})
        # 関連する实体欄 → entity 相互リンク（長い語優先で置換）
        terms_sorted = sorted(ent_slugs, key=len, reverse=True)
        for p in sorted((CONTENT / "entities").glob("*.md")):
            art = p.read_bytes().decode("utf-8", "replace")
            m = _re.search(r"(##\s*関連する实体.*?)(?=\n##|\Z)", art, re.S)
            if not m:
                continue
            sec = m.group(1)
            self_slug = p.stem
            for t in terms_sorted:
                sl = ent_slugs[t]
                if sl == self_slug:
                    continue
                link = f"[[entities/{sl}|{t}]]"
                # 既存リンク化済み（|語]] 形）は置換しない
                sec = _re.sub(r"(?<!\|)" + _re.escape(t) + r"(?!\]\])", link, sec)
            new = art[:m.start(1)] + sec + art[m.end(1):]
            p.write_bytes(new.encode("utf-8"))
        # 类型別索引
        idx = ["---", 'title: "实体索引"', "run: publish", "---", "", "# 实体索引", ""]
        by_type = {}
        for p in sorted((CONTENT / "entities").glob("*.md")):
            a = p.read_bytes().decode("utf-8", "replace")
            tm = _re.search(r'term:\s*"([^"]+)"', a)
            ty = _re.search(r'type:\s*"([^"]+)"', a)
            by_type.setdefault(ty.group(1) if ty else "其他", []).append((tm.group(1) if tm else p.stem, p.stem))
        for tname in sorted(by_type):
            idx.append(f"## {tname}")
            idx.append("")
            for term, sl in sorted(by_type[tname]):
                idx.append(f"- [[entities/{sl}|{term}]]")
            idx.append("")
        (CONTENT / "entities_index.md").write_bytes("\n".join(idx).encode("utf-8"))

    # nav（185 篇索引）
    nav = ["---", 'title: "篇索引"', "run: publish", "---", "", "# 篇索引（185 篇）", ""]
    for uid in sorted(units):
        u = units[uid]
        nav.append(f"- [[units/{uid}|{u.get('title', uid)}]]（{u.get('n_posts', '?')} 投稿）")
    nav.append("")
    nav.append("各篇の制約なし版: [[full/|full 索引]]")
    (CONTENT / "nav.md").write_bytes("\n".join(nav).encode("utf-8"))

    # top
    stats = json.loads((led / "stats.json").read_text(encoding="utf-8"))
    top = f"""---
title: "ゆらぎの神話 BBS 実況 Wiki トップ"
run: publish
---

# ゆらぎの神話 BBS 実況 Wiki

『ゆらぎの神話』関連 BBS（japan board / はてな / mixi）の実況・議論スレッド 185 篇・48,891 投稿を、
解析パイプライン（L0 台帳 → 検索 → LLM 生成 → LLM 全量品質監査 100%）で構築した Wiki です。

## 版

- **L1 版（当サイト主要面）**: 要約・整理記事。引用は 100 字以内＋ ref アンカー（原文ファイルへのリンク付き）。
- **自由記述版（制約なし）**: [[free_index|free（自由記述記事）]] — L1 と原文をもとに構造制約なしで記述。引用は原文からの逐語のみ・全記事 ref 付き。
- **原文全文版**: [[full/index|full（原文全文同梱）]] — 各篇の投稿全文をそのまま掲載（投稿単位アンカー付き）。投稿の著作権は各投稿者に帰属します（[[license|ライセンス]]）。

## 節

- [[entities_index|实体索引]] — 人物・物品・国などの作中实体（wiki 中核）
- [[works_top|創作索引]] — 散在する創作的記述（詩・短編・設定文等）の横断索引
- [[free_index|自由記述索引]] — 制約なし自由記述記事（L1＋原文に基づく）
- [[nav|篇索引]] — 185 篇
- [[topics/index|topics 索引]] — 話題・語句 429（出現 3 以上）
- [[authors/index|authors 索引]] — 主要投稿者 95（投稿 10 以上）
- [[chronology|年表]]
- [[full/index|制約なし版 篇索引]]

## 統計（L0 台帳 {led.name}）

- 篇 185 / 投稿 48,891 / 投稿群 16,271（LLM 要約付き）/ 語句 6,224
- 創作記述 7,621 群 → 作品ページ 6,453・収録投稿 26,710 件（permalink 付き原文逐語）
- 实体 321・自由記述記事 185・全記事 LLM 全量監査 100% 収束
- 来歴: 解析・生成・監査は AllusionistWiki_work repo（非公開運用層）で実施。各記事 frontmatter に run ID 記録。
"""
    (CONTENT / "index.md").write_bytes(top.encode("utf-8"))

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
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

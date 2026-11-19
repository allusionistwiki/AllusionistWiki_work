"""works 作者索引・篇収容创作索引（决定论生成）.

work/yuragi/L1/runs/<rid>/author_index/<slug>.md  : 作者別作品一覧
work/yuragi/L1/runs/<rid>/unit_index/<uid>.md     : 篇別掲載创作一覧
run id: <ts>_l1widx
"""
import json, re, time
from collections import defaultdict
from pathlib import Path

L1 = Path("work/yuragi/L1")
WORKS_RUN = sorted(p.name for p in (L1/"runs").glob("*_l1works"))[-1]
RID = time.strftime("%Y%m%dT%H%M") + "_l1widx"
OUT = L1/"runs"/RID
(OUT/"author_index").mkdir(parents=True, exist_ok=True)
(OUT/"unit_index").mkdir(parents=True, exist_ok=True)

def yq(v):
    v = str(v).replace("\\", "\\\\").replace('"', "'")
    v = re.sub(r"[\r\n]+", " ", v)
    return f'"{v}"'

def slugify(s):
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:80] or "x"

rows = [json.loads(l) for l in (L1/"works.jsonl").read_bytes().decode("utf-8", "replace").splitlines() if l.strip()]
cr = [r for r in rows if r.get("creative")]

# works ページ slug 対応表: (work, author) -> slug（build_yuragi_works と同一規則: 連番は title 照合で決める）
pages = {}
used = set()
for p in sorted((L1/"runs"/WORKS_RUN/"works").glob("*.md")):
    t = p.read_bytes().decode("utf-8", "replace")
    m = re.search(r'^title:\s*"(.*)"', t, re.M)
    a = re.search(r'^author:\s*"(.*)"', t, re.M)
    if m and a:
        pages.setdefault((m.group(1), a.group(1)), p.stem)

def work_link(r):
    slug = pages.get((r.get("work") or "無題", r.get("author")))
    return slug

by_author = defaultdict(list)
by_unit = defaultdict(list)
for r in cr:
    by_author[r.get("author") or "?"].append(r)
    by_unit[r.get("uid")].append(r)

# 作者索引
authors_sorted = sorted(by_author.items(), key=lambda kv: -len(kv[1]))
used_slug = set()
idx_slugs = {}
for i, (au, rs) in enumerate(authors_sorted):
    s = slugify(au)
    base = s
    n = 2
    while s in used_slug:
        s = f"{base}_{n}"; n += 1
    used_slug.add(s)
    idx_slugs[au] = s
    cnt = defaultdict(int)
    for r in rs:
        cnt[(r.get("work") or "無題")] += 1
    lines = [f"---\ntitle: {yq('創作作者索引: '+au)}\nauthor: {yq(au)}\nrun: {RID}\n---",
             "", f"# 創作作者索引: {au}", "", f"（収録創作群: {len(rs)} ／ 作品数: {len(cnt)}）", ""]
    for (w, c) in sorted(cnt.items(), key=lambda kv: -kv[1]):
        slug = pages.get((w, au))
        if slug:
            lines.append(f"- [[works/{slug}|{w}]]（{c} 群）")
        else:
            lines.append(f"- {w}（{c} 群）")
    (OUT/"author_index"/f"{s}.md").write_bytes("\n".join(lines).encode("utf-8"))

# 作者索引トップ
top = [f"---\ntitle: \"創作作者索引\"\nrun: {RID}\n---", "", "# 創作作者索引（作品掲載数順）", ""]
for au, rs in authors_sorted:
    top.append(f"- [[author_index/{idx_slugs[au]}|{au}]]（{len(rs)} 群）")
(OUT/"author_index"/"index.md").write_bytes("\n".join(top).encode("utf-8"))

# 篇収容创作索引
units = sorted(by_unit)
for uid in units:
    rs = by_unit[uid]
    lines = [f"---\ntitle: {yq('創作収容: '+uid)}\nrun: {RID}\n---",
             "", f"# 創作収容: {uid}", "",
             f"[[units/{uid}|L1 版記事]] ／ [[free/{uid}|自由記述版]] ／ [[full/{uid}|原文全文]]",
             f"（掲載創作群: {len(rs)}）", ""]
    cnt = defaultdict(int)
    for r in rs:
        cnt[(r.get("work") or "無題", r.get("author"))] += 1
    for ((w, a), c) in sorted(cnt.items(), key=lambda kv: -kv[1]):
        slug = pages.get((w, a))
        if slug:
            lines.append(f"- [[works/{slug}|{w}]]（{a}・{c} 群）")
        else:
            lines.append(f"- {w}（{a}・{c} 群）")
    (OUT/"unit_index"/f"{uid}.md").write_bytes("\n".join(lines).encode("utf-8"))

print(json.dumps({"rid": RID, "works_run": WORKS_RUN, "authors": len(authors_sorted), "units": len(units), "creative_chains": len(cr)}, ensure_ascii=False))

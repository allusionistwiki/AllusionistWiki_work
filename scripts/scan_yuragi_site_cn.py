# -*- coding: utf-8 -*-
"""YuragiWiki site content CN 再スキャン（常時監査）。

Method: cn_gate._CN_STRICT + cp932 round-trip;
frontmatter+quoted(nested)+fenced/inline code+html comments/tags+URL+[[wiki]]+md link targets stripped;
JP_SHARED excluded. 出力: 集計 JSON（cn_scan_latest.json に書換可）。
Usage: python scan_yuragi_site_cn.py <site_content_dir> [out.json]
"""
import json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cn_gate

def strip_noise(text: str) -> str:
    # frontmatter
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    if m:
        text = text[m.end():]
    text = re.sub(r"```.*?```", " ", text, flags=re.S)   # fenced code
    text = re.sub(r"`[^`\n]*`", " ", text)               # inline code
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)  # html comments
    text = re.sub(r"<[^>\n]{1,200}>", " ", text)         # html tags
    text = re.sub(r"https?://[^\s)）\"'<>]+", " ", text) # URLs
    text = re.sub(r"\[\[[^\]]*\]\]", " ", text)          # wiki links
    text = re.sub(r"(\[[^\]]*\]\()[^)]*(\))", r"\1 \2", text)  # md link targets
    # nested quotes: peel innermost 「…」/『…」 repeatedly
    for pat in (r"「[^「」]*」", r"『[^『』]*』"):
        prev = None
        while prev != text:
            prev = text
            text = re.sub(pat, lambda mm: " ".join(c if c.isascii() else " " for c in mm.group(0)), text)
    return text

def main():
    content = Path(sys.argv[1])
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    scanned = 0
    hits_total = 0
    rare_total = 0
    char_counts: dict[str, int] = {}
    files_with_hits = 0
    top_files: list[dict] = []
    for p in sorted(content.rglob("*.md")):
        scanned += 1
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        scan = strip_noise(text)
        hits = [c for c in scan if c in cn_gate._CN_STRICT]
        rare = [c for c in scan if cn_gate._non_jis(c) and c not in cn_gate._CN_STRICT and not c.isspace()]
        n = len(hits) + len(rare)
        if n:
            files_with_hits += 1
            top_files.append({"file": str(p.relative_to(content)), "hits": n})
            for c in hits + rare:
                char_counts[c] = char_counts.get(c, 0) + 1
        hits_total += len(hits)
        rare_total += len(rare)
    top_files.sort(key=lambda d: -d["hits"])
    report = {
        "scanned_files": scanned,
        "cn_total": hits_total + rare_total,
        "cn_strict_total": hits_total,
        "non_jis_rare_total": rare_total,
        "char_counts": char_counts,
        "top_files": top_files[:20],
        "files_with_hits": files_with_hits,
        "method": "cn_gate._CN_STRICT + cp932 round-trip; frontmatter+quoted(nested)+fenced/inline code+html comments/tags+URL+[[wiki]]+md link targets stripped; JP_SHARED excluded",
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    print(json.dumps(report, ensure_ascii=False))
    if out_path:
        Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()

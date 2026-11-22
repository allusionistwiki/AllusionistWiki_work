# -*- coding: utf-8 -*-
"""CN_CHAR ゲート: 生成記事への中国語（簡体字等 JIS 圏外）文字混入検出。

AllusionistWiki 恒久監査基準: 日本語記事に 的・实・网・时・长・门・话・语・们・这 等の
JIS 圏外／簡体字が混入したら不合格（引用「」内は原文逐語なので除外してよいが、
生成本文に出たら drop）。
"""
import re

# 頻出簡体字／日本漢字として成立しない形（JIS X 0208 に無い或いは日本で使われない形）
CN_CHARS = set(
    "实网长们说话语这来对让从马书见观记讲难灭显变认产问间维网页击术树战运进签简历"
    "录录尽与习乡义乐习乱争亚亏亿伞传伤伞体闪岛饭馆驶骂烧烂爱牺党严历历宪"
    "阶图圈园团帅师帐帐币厂广庆庐库应庙废异弃弹当录彻凤链举旧时尽层属岁岁"
    "师帐币厂广庆庐库应庙废异弃弹当录彻凤链举旧时尽层属岁显变认产问间维网页"
    "击术树战运进签简历录尽与习乡义乐乱争亚亏亿伞传伤体闪岛饭馆驶骂烧烂爱牺党严宪"
    "阶图圈园团帅师张帐币厂广庆庐库应庙废异弃弹当录彻凤链举旧时尽层属岁显变"
)
# 「的」は日本語でも使う（的・まと）が、記事本文での中国語的用法は混入の兆候。別扱いで warn のみ。
WARN_CHARS = set("的")


def find_cn(text: str, allow_in_quotes: bool = True):
    """(cn_hits, warn_hits) を返す。allow_in_quotes=True なら「…」内の命中は除外。"""
    scan = text
    if allow_in_quotes:
        scan = re.sub(r"「[^」]*」", lambda m: "".join(ch if ch.isascii() else " " for ch in m.group(0)), scan)
        scan = re.sub(r"『[^』]*』", lambda m: "".join(ch if ch.isascii() else " " for ch in m.group(0)), scan)
    hits = [ch for ch in scan if ch in CN_CHARS]
    warn = [ch for ch in scan if ch in WARN_CHARS]
    return hits, warn


def is_cn_free(text: str) -> bool:
    hits, _ = find_cn(text)
    return len(hits) == 0


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        t = open(path, encoding="utf-8", errors="replace").read()
        h, w = find_cn(t)
        print(path, "CN_hits:", len(h), "".join(sorted(set(h)))[:40], "warn:", len(w))

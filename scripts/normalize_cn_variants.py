"""Targeted variant normalization: CN-only simplified chars -> Japanese-standard JIS glyphs.

Scope: L1 article bodies ONLY, prose regions OUTSIDE frontmatter and OUTSIDE 「...」 quotes
(quotes are verbatim-corpus-gated and stay untouched). This is a 字体变体 (glyph-variant)
normalization to standard Japanese kanji — NOT the forbidden 的-deletion style rewrite.
"""
import re
import sys
from pathlib import Path

MAP = {
    "\u5b9e": "\u5b9f",  # 实 -> 実
    "\u6c14": "\u6c17",  # 气 -> 気
    "\u65f6": "\u6642",  # 时 -> 時
    "\u95e8": "\u9580",  # 门 -> 門
    "\u5f00": "\u958b",  # 开 -> 開
    "\u8bed": "\u8a9e",  # 语 -> 語
    "\u8bdd": "\u8a71",  # 话 -> 話
    "\u8bf4": "\u8aaa",  # 说 -> 説
    "\u8bf7": "\u8acb",  # 请 -> 請
    "\u8c22": "\u8b1d",  # 谢 -> 謝
    "\u8fc7": "\u904e",  # 过 -> 過
    "\u4e49": "\u7fa9",  # 义 -> 義
    "\u4e60": "\u7fd2",  # 习 -> 習
    "\u4e61": "\u90f7",  # 乡 -> 鄕
    "\u4e50": "\u697d",  # 乐 -> 楽
    "\u9f50": "\u9f4a",  # 齐 -> 斉
    "\u5934": "\u982d",  # 头 -> 頭
    "\u56fe": "\u5716",  # 图 -> 図
    "\u5706": "\u5713",  # 圆 -> 圓
    "\u5458": "\u54e1",  # 员 -> 員
    "\u8d44": "\u8cc7",  # 资 -> 資
    "\u8d27": "\u8ca7",  # 货 -> 貨
    "\u90ae": "\u90f5",  # 邮 -> 郵
    "\u8bd1": "\u8a33",  # 译 -> 譯
    "\u8bae": "\u8b70",  # 议 -> 議
    "\u519b": "\u8ecd",  # 军 -> 軍
    "\u961f": "\u968a",  # 队 -> 隊
    "\u4e30": "\u8c4a",  # 丰 -> 豊
    "\u827a": "\u85dd",  # 艺 -> 芸
    "\u8282": "\u7bc0",  # 节 -> 節
    "\u4e1b": "\u531b",  # 丛 -> 叢
    "\u5170": "\u862d",  # 兰 -> 蘭
    "\u6807": "\u6a19",  # 标 -> 標
    "\u7f51": "\u7db2",  # 网 -> 網
}
CN = re.compile("[" + "".join(MAP) + "]")
QU = re.compile(r"「[^「」]*」")


def norm_prose(text: str) -> tuple[str, int]:
    # protect quotes with sentinels
    quotes: list[str] = []
    def mask(m: re.Match) -> str:
        quotes.append(m.group(0))
        return f"\x00Q{len(quotes) - 1}\x01"
    marked = QU.sub(mask, text)
    n = 0
    def rep(m: re.Match) -> str:
        nonlocal n
        n += 1
        return MAP[m.group(0)]
    out = CN.sub(rep, marked)
    for i, q in enumerate(quotes):
        out = out.replace(f"\x00Q{i}\x01", q)
    return out, n


def main() -> int:
    scope = sys.argv[2]
    run = Path(sys.argv[1])
    keys = sys.argv[3:]
    total = 0
    for k in keys:
        p = run / scope / f"{k}.md"
        if not p.exists():
            print("MISS", k)
            continue
        raw = p.read_bytes().decode("utf-8", "replace")
        parts = raw.split("---", 2)
        if len(parts) < 3:
            print("NOFM", k)
            continue
        fm, body = parts[0] + "---" + parts[1] + "---", parts[2]
        nb, n = norm_prose(body)
        if n:
            p.write_bytes((fm + nb).encode("utf-8"))
        total += n
        print(k, n)
    print("total_chars_normalized", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())

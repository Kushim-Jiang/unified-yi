"""把《论滇川黔桂彝族文字》第六章对比表 XLSX 转成 book/u4.tsv 和 rs/u4.tsv。

果吉·宁哈《论滇川黔桂彝族文字》(民族出版社, 1988) 第六章是手写的《滇川黔桂彝文
单字对比研究表》：一行一个字头（正体字），后面滇、川、黔、桂四栏各记这个字的
异体、出处代号和读音，另有部首列和备注列。印刷页 119–324，共 943 条。

表头约定：no, cp_hex, glyph, page, no, srcref, 部首, 字义, 滇, 川, 黔, 桂, 备注, 原书截图

输出列：glyph_unified, src_ref, pronunciation, meaning, note
        以及 rs/ 的 glyph_unified, radical, other_stroke

- src_ref = `U4-{页码:03d}{页内序号:02d}`，页内序号按表中顺序逐页累加
  （整理表里空行已略去，不能直接用 `no` 列）。
- 四省区读音合成一列，写作「滇 … ｜ 川 … ｜ 黔 … ｜ 桂 …」，某省区没有记录就
  不写该段。段内保持原表的「／」「；」分组。
- 部首原表只给字形（码位 U+F6400–U+F6424，属 YiHeadwords-U4 字体），没有笔画
  数，所以 rs/u4.tsv 的 other_stroke 留空。
- 正体字是 PUA 码位（U+F6000 起），与 yi.ttf 里的字冲突，只能用
  YiHeadwords-U4 字体渲染（SOURCE_META 的 font="yiheadu4"）。

用法：
    python utils/import_u4.py <整理表.xlsx>               # 写入 book/ 和 rs/
    python utils/import_u4.py <整理表.xlsx> --out <目录>   # 先输出到别处核对
"""

import argparse
import re
from pathlib import Path

from openpyxl import load_workbook

SHEET = "U4"
REGIONS = ["滇", "川", "黔", "桂"]
HEADER = ["no", "cp_hex", "glyph", "page", "no", "srcref", "部首", "字义", "滇", "川", "黔", "桂", "备注", "原书截图"]
OUT_HEADER = ["glyph_unified", "src_ref", "pronunciation", "meaning", "note"]
RS_HEADER = ["glyph_unified", "radical", "other_stroke"]
PLACEHOLDER_GLYPH = "\uff1f"  # 原表没有填正体字时占位（同 u3）


def clean(value) -> str:
    """单元格 → 单行字符串（制表符/换行会破坏 TSV）。"""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\r\n]+", "", text)
    return text.replace("\t", " ").strip()


def read_rows(wb) -> list[list[str]]:
    ws = wb[SHEET]
    rows = ws.iter_rows(values_only=True)
    header = [clean(c) for c in next(rows)]
    if header[: len(HEADER)] != HEADER:
        raise SystemExit(f"unexpected header in '{SHEET}': {header}")
    out = []
    for row in rows:
        if row is None or all(c is None for c in row):
            continue
        out.append([clean(c) for c in row])
    return out


def join_readings(row: list[str]) -> str:
    """把滇/川/黔/桂四栏合成一列，省区名做标签。"""
    offset = HEADER.index("滇")
    parts = []
    for i, region in enumerate(REGIONS):
        text = row[offset + i]
        if text:
            parts.append(f"{region} {text}")
    return " ｜ ".join(parts)


def build_entries(rows: list[list[str]], prefix: str) -> tuple[list[list[str]], list[list[str]]]:
    page_seq: dict[int, int] = {}
    entries = []
    rs_entries = []
    for row in rows:
        glyph, page = row[2], row[3]
        if not page.isdigit():
            raise SystemExit(f"row without page in {prefix}: {row[:8]}")
        page_no = int(page)
        page_seq[page_no] = page_seq.get(page_no, 0) + 1
        srcref = f"{prefix}-{page_no:03d}{page_seq[page_no]:02d}"
        glyph = glyph or PLACEHOLDER_GLYPH
        entries.append([glyph, srcref, join_readings(row), row[7], row[12]])
        if glyph != PLACEHOLDER_GLYPH:
            rs_entries.append([glyph, row[6], ""])
    return entries, rs_entries


def write_tsv(path: Path, header: list[str], entries: list[list[str]]):
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("\t".join(header) + "\r\n")
        for row in entries:
            f.write("\t".join(row) + "\r\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "book")
    ap.add_argument("--rs-out", type=Path, default=Path(__file__).parent.parent / "rs")
    args = ap.parse_args()

    wb = load_workbook(args.xlsx, read_only=True, data_only=True)
    if SHEET not in wb.sheetnames:
        raise SystemExit(f"sheet '{SHEET}' not found, available: {wb.sheetnames}")
    entries, rs_entries = build_entries(read_rows(wb), SHEET)
    wb.close()

    target = args.out / f"{SHEET.lower()}.tsv"
    write_tsv(target, OUT_HEADER, entries)
    print(f"{target}: {len(entries)} entries")

    rs_target = args.rs_out / f"{SHEET.lower()}.tsv"
    write_tsv(rs_target, RS_HEADER, rs_entries)
    print(f"{rs_target}: {len(rs_entries)} entries")


if __name__ == "__main__":
    main()

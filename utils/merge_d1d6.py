"""把《彝汉字典》D1–D6 整理包 XLSX 转成 book/*.tsv。

整理包的 sheet 名就是来源编号（D1–D6），对应仓库中的同号来源：

    d1  彝汉字典（楚雄本）1995        d2  彝汉简明词典 1984
    d3  汉彝词典（楚雄本）2006        d4  滇南彝文字典 2005
    d5  古彝文常用字典 2014           d6  简明彝汉字典（禄劝版）2014

表头约定：no, cp_hex, glyph, page, no, srcref, 代表音, 含义, 备注, 原书截图
输出列：glyph_unified, src_ref, pronunciation, meaning, note

src_ref 由页码和页内阅读顺序生成：`{来源}-{页码:03d}{页内序号:02d}`。
整理表里有 30 行原表漏收、后来补入的字头没有条号（`no` 列为空），它们在表里
按书中位置排好，所以页内序号逐页累加，不取 `no` 列。

用法：
    python utils/merge_d1d6.py <整理表.xlsx>                # 写入 book/
    python utils/merge_d1d6.py <整理表.xlsx> --out <目录>    # 先输出到别处核对
"""

import argparse
import re
from pathlib import Path

from openpyxl import load_workbook

SHEETS = ["D1", "D2", "D3", "D4", "D5", "D6"]
HEADER = ["no", "cp_hex", "glyph", "page", "no", "srcref", "代表音", "含义", "备注", "原书截图"]
OUT_HEADER = ["glyph_unified", "src_ref", "pronunciation", "meaning", "note"]


def clean(value) -> str:
    """单元格 → 单行字符串（制表符/换行会破坏 TSV）。"""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\r\n]+", "", text)
    return text.replace("\t", " ").strip()


def read_rows(wb, sheet: str) -> list[list[str]]:
    ws = wb[sheet]
    rows = ws.iter_rows(values_only=True)
    header = [clean(c) for c in next(rows)]
    if header[: len(HEADER)] != HEADER:
        raise SystemExit(f"unexpected header in '{sheet}': {header}")
    out = []
    for row in rows:
        if row is None or all(c is None for c in row):
            continue
        out.append([clean(c) for c in row])
    return out


def build_entries(rows: list[list[str]], prefix: str) -> list[list[str]]:
    """按页内阅读顺序生成 src_ref。

    页内序号逐页累加：整理表里补入的字头没有条号，但位置是按书中顺序排的。
    """
    page_seq: dict[int, int] = {}
    entries = []
    for row in rows:
        glyph, page = row[2], row[3]
        srcref = row[5]
        if not srcref:
            if not page.isdigit():
                raise SystemExit(f"row without page in {prefix}: {row[:8]}")
            page_no = int(page)
            page_seq[page_no] = page_seq.get(page_no, 0) + 1
            srcref = f"{prefix}-{page_no:03d}{page_seq[page_no]:02d}"
        entries.append([glyph, srcref, row[6], row[7], row[8]])
    return entries


def convert(xlsx: Path) -> dict[str, list[list[str]]]:
    wb = load_workbook(xlsx, read_only=True, data_only=True)
    missing = [s for s in SHEETS if s not in wb.sheetnames]
    if missing:
        raise SystemExit(f"sheets not found: {missing}, available: {wb.sheetnames}")
    result = {}
    for sheet in SHEETS:
        rows = read_rows(wb, sheet)
        result[sheet.lower()] = build_entries(rows, sheet)
    wb.close()
    return result


def write_tsv(path: Path, entries: list[list[str]]):
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("\t".join(OUT_HEADER) + "\r\n")
        for row in entries:
            f.write("\t".join(row) + "\r\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "book")
    ap.add_argument("--only", nargs="*", help="只输出指定来源，如 d1 d3")
    args = ap.parse_args()

    data = convert(args.xlsx)
    for source, entries in data.items():
        if args.only and source not in args.only:
            continue
        target = args.out / f"{source}.tsv"
        write_tsv(target, entries)
        print(f"{target}: {len(entries)} entries")


if __name__ == "__main__":
    main()

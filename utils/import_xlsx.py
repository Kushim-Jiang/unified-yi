"""把外部整理的字典 XLSX 转成 book/*.tsv。

表头约定：no, cp_hex, glyph, page, no, srcref, 代表音, 含义, 备注, 原书截图
输出列：glyph_unified, src_ref, pronunciation, meaning, note

用法：
    python utils/import_xlsx.py <xlsx 路径> <sheet 名> <src_ref 前缀> [--out book]

例：
    python utils/import_xlsx.py Q1.xlsx Q1 Q1
    python utils/import_xlsx.py 核对包.xlsx 通用规范彝文常用字字典 U3
"""

import argparse
import re
from pathlib import Path

from openpyxl import load_workbook

PLACEHOLDER_GLYPH = "\uff1f"  # 字典未印字头时占位

HEADER = ["no", "cp_hex", "glyph", "page", "no", "srcref", "代表音", "含义", "备注", "原书截图"]
OUT_HEADER = ["glyph_unified", "src_ref", "pronunciation", "meaning", "note"]


def clean(value) -> str:
    """单元格 → 单行字符串（制表符/换行会破坏 TSV）。"""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\r\n]+", "", text)
    return text.replace("\t", " ").strip()


def cell(row: tuple, index: int) -> str:
    return clean(row[index])


def strip_parenthetical(text: str) -> str:
    """去掉括号里的附注，如 q3 的 "pu³⁴（bux）" → "pu³⁴"。"""
    return re.sub(r"\s*[（(][^）)]*[）)]", "", text).strip()


def convert(xlsx: Path, sheet: str, prefix: str, ipa_only: bool = False) -> list[list[str]]:
    wb = load_workbook(xlsx, read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        raise SystemExit(f"sheet '{sheet}' not found, available: {wb.sheetnames}")
    ws = wb[sheet]
    rows = ws.iter_rows(values_only=True)
    header = [clean(c) for c in next(rows)]
    if header[: len(HEADER)] != HEADER:
        raise SystemExit(f"unexpected header in '{sheet}': {header}")

    out = []
    skipped = []
    for row in rows:
        if row is None or all(c is None for c in row):
            continue
        glyph = cell(row, 2)
        srcref = cell(row, 5)
        if not srcref:
            page = cell(row, 3)
            no = cell(row, 4)
            if not page.isdigit() or not no.isdigit():
                # 整页缺扫描件之类的占位行，不是条目
                skipped.append(cell(row, 8))
                continue
            srcref = f"{prefix}-{int(page):03d}{int(no):02d}"
        pronunciation = cell(row, 6)
        if ipa_only:
            pronunciation = strip_parenthetical(pronunciation)
        out.append([glyph or PLACEHOLDER_GLYPH, srcref, pronunciation, cell(row, 7), cell(row, 8)])
    wb.close()
    if skipped:
        print(f"[skip] {len(skipped)} non-entry row(s): {skipped}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("sheet")
    ap.add_argument("prefix")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "book")
    ap.add_argument("--ipa-only", action="store_true", help="去掉 pronunciation 列括号里的拼音附注")
    args = ap.parse_args()

    rows = convert(args.xlsx, args.sheet, args.prefix, ipa_only=args.ipa_only)
    target = args.out / f"{args.prefix.lower()}.tsv"
    with target.open("w", encoding="utf-8", newline="") as f:
        f.write("\t".join(OUT_HEADER) + "\r\n")
        for row in rows:
            f.write("\t".join(row) + "\r\n")
    print(f"{target}: {len(rows)} entries")


if __name__ == "__main__":
    main()

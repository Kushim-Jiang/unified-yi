"""
部首-笔画相似度计算模块

基于 rs/ 目录下的部首（radical）和笔画数（stroke count）数据，
计算两个彝文字符在字形结构上的相似度。

数据格式 (rs/{source}.tsv):
    glyph_unified  radical  other_stroke

rs_order.yaml 列出了所有部首的排列顺序。
"""

from pathlib import Path
from typing import Optional

import yaml

# ─── 数据加载 ──────────────────────────────────────────────────


def _get_rs_dir() -> Path:
    """获取 rs/ 数据目录。"""
    return Path(__file__).parent.parent.parent / "rs"


def load_rs_data(source: str) -> dict[str, dict]:
    """
    加载指定来源的部首-笔画数据。
    返回 {glyph: {radical, other_stroke}} 的字典。
    radical 和 other_stroke 字段支持逗号分隔（多个部首）。
    """
    rs_dir = _get_rs_dir()
    filepath = rs_dir / f"{source}.tsv"
    if not filepath.exists():
        return {}
    with filepath.open(encoding="utf-8") as f:
        lines = f.readlines()
    data = {}
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            data[parts[0]] = {
                "radical": parts[1],
                "other_stroke": parts[2],  # may be comma-separated
            }
    return data


def load_radical_order() -> list[str]:
    """
    从 rs_order.yaml 加载部首排列顺序。
    返回按顺序排列的部首 glyph 列表。
    """
    rs_dir = _get_rs_dir()
    filepath = rs_dir / "rs_order.yaml"
    if not filepath.exists():
        return []
    with filepath.open(encoding="utf-8") as f:
        order_dict = yaml.safe_load(f) or {}
    return list(order_dict.keys())


# ─── 全局缓存 ──────────────────────────────────────────────────

_RS_CACHE: dict[str, dict[str, dict]] = {}
_RADICAL_ORDER: Optional[list[str]] = None
_RADICAL_INDEX: Optional[dict[str, int]] = None


def _get_rs_cache(source: str) -> dict[str, dict]:
    if source not in _RS_CACHE:
        _RS_CACHE[source] = load_rs_data(source)
    return _RS_CACHE[source]


def _get_radical_order() -> list[str]:
    global _RADICAL_ORDER
    if _RADICAL_ORDER is None:
        _RADICAL_ORDER = load_radical_order()
    return _RADICAL_ORDER


def _get_radical_index() -> dict[str, int]:
    global _RADICAL_INDEX
    if _RADICAL_INDEX is None:
        radicals = _get_radical_order()
        _RADICAL_INDEX = {r: i for i, r in enumerate(radicals)}
    return _RADICAL_INDEX


# ─── 相似度计算 ────────────────────────────────────────────────


def radical_similarity(rad1: Optional[str], rad2: Optional[str]) -> float:
    """
    计算两个部首之间的相似度。

    策略：
    - 相同部首 → 1.0
    - 都在部首表中但不同 → 基于在 rs_order 中的位置距离计算（相邻部首至少 0.3）
    - 一个不在部首表中 → 0.0
    - 都为空 → 0.0
    """
    if rad1 is None or rad2 is None:
        return 0.0
    if rad1 == rad2:
        return 1.0

    idx = _get_radical_index()
    total = len(idx)
    if total == 0:
        return 0.0

    i1 = idx.get(rad1)
    i2 = idx.get(rad2)

    if i1 is None or i2 is None:
        return 0.0

    # 距离越近相似度越高：similarity = 1 - (distance / max_distance)
    # 但设置一个 floor: 即使最远的部首，至少给 0.15（它们共享"彝文部首"身份）
    distance = abs(i1 - i2)
    max_distance = total - 1
    linear_sim = 1.0 - (distance / max_distance)
    # 映射到 [0.15, 1.0] 范围（不同部首最低 0.15）
    sim = 0.15 + 0.85 * linear_sim
    return round(sim, 4)


def stroke_similarity(stroke1: Optional[int], stroke2: Optional[int]) -> float:
    """
    计算两个笔画数的相似度。

    笔画越接近相似度越高。使用指数衰减。
    """
    if stroke1 is None or stroke2 is None:
        return 0.5  # 未知时给中性值
    diff = abs(stroke1 - stroke2)
    if diff == 0:
        return 1.0
    # 指数衰减：差 1 笔 → 0.7, 差 2 → 0.49, 差 5 → 0.17
    sim = max(0.0, 0.70**diff)
    return round(sim, 4)


def _first_stroke(stroke_val: str | int | None) -> int | None:
    """从可能逗号分隔的笔画字段中提取第一个笔画数。"""
    if stroke_val is None:
        return None
    if isinstance(stroke_val, int):
        return stroke_val
    parts = str(stroke_val).split(",")
    first = parts[0].strip()
    return int(first) if first.isdigit() else None


def radical_stroke_similarity(
    rad1: Optional[str] = None,
    stroke1: str | int | None = None,
    rad2: Optional[str] = None,
    stroke2: str | int | None = None,
) -> dict:
    """
    综合部首和笔画的相似度。
    radical 和 stroke 字段支持逗号分隔（多个部首），此时取第一个用于比较。

    权重：部首 70%，笔画 30%
    （部首承载了主要的字形结构信息）
    """
    # 取第一个 radical（逗号分隔时）
    r1 = rad1.split(",")[0].strip() if rad1 and "," in rad1 else rad1
    r2 = rad2.split(",")[0].strip() if rad2 and "," in rad2 else rad2
    s1 = _first_stroke(stroke1)
    s2 = _first_stroke(stroke2)

    r_sim = radical_similarity(r1, r2)
    s_sim = stroke_similarity(s1, s2)

    combined = 0.70 * r_sim + 0.30 * s_sim

    return {
        "radical_similarity": round(r_sim, 4),
        "stroke_similarity": round(s_sim, 4),
        "combined_score": round(combined, 4),
    }


def get_char_rs(source: str, glyph: str) -> Optional[dict]:
    """
    获取某个字符（按 glyph）的部首-笔画信息。
    优先匹配 glyph，也尝试按 src_ref 查找。
    """
    cache = _get_rs_cache(source)
    if glyph in cache:
        return cache[glyph]
    # 尝试在其他来源的 rs 数据中查找同一字形
    for src_key in _RS_CACHE:
        if src_key == source:
            continue
        src_cache = _get_rs_cache(src_key)
        if glyph in src_cache:
            return src_cache[glyph]
    return None


def radical_order_index(radical: Optional[str]) -> int:
    """
    获取部首在 rs_order.yaml 中的排列序号。
    不在列表中返回 -1。
    """
    if radical is None:
        return -1
    idx = _get_radical_index()
    return idx.get(radical, -1)


def find_similar_by_radical_stroke(
    target_glyph: str,
    target_source: str,
    candidates: list[dict],
    top_k: int = 20,
    min_score: float = 0.1,
) -> list[dict]:
    """
    在候选列表中找出与目标字符部首-笔画最接近的项。

    candidates 中每项需有 'glyph' 和 'source' 字段。
    """
    target_rs = get_char_rs(target_source, target_glyph)

    results = []
    for cand in candidates:
        cand_glyph = cand.get("glyph", "")
        cand_source = cand.get("source", "")
        cand_rs = get_char_rs(cand_source, cand_glyph)

        if target_rs and cand_rs:
            sim_info = radical_stroke_similarity(
                target_rs.get("radical"),
                target_rs.get("other_stroke"),
                cand_rs.get("radical"),
                cand_rs.get("other_stroke"),
            )
        elif target_rs or cand_rs:
            # 只有一个有 RS 数据，不能判断
            sim_info = {"radical_similarity": 0.0, "stroke_similarity": 0.5, "combined_score": 0.15}
        else:
            # 都没有 RS 数据
            sim_info = {"radical_similarity": 0.0, "stroke_similarity": 0.5, "combined_score": 0.15}

        if sim_info["combined_score"] >= min_score:
            results.append(
                {
                    **cand,
                    "rs_similarity": sim_info["combined_score"],
                    "rs_similarity_detail": sim_info,
                }
            )

    results.sort(key=lambda x: x["rs_similarity"], reverse=True)
    return results[:top_k]

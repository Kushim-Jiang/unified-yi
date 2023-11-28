"""
语义相似度计算模块

通过中文释义的字符重叠度来衡量两个词的语义相似度。
使用 Jaccard 相似度（交集/并集）和 Dice 系数。
"""

import re


def clean_meaning(text: str) -> str:
    """清洗释义文本，只保留中文字符。"""
    if not text:
        return ""
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    return "".join(chinese_chars)


def char_set_similarity(text1: str, text2: str) -> dict:
    """计算两个中文字符串的字符集相似度。"""
    chars1 = set(text1)
    chars2 = set(text2)

    if not chars1 and not chars2:
        return {"jaccard": 1.0, "dice": 1.0, "overlap": 1.0}
    if not chars1 or not chars2:
        return {"jaccard": 0.0, "dice": 0.0, "overlap": 0.0}

    intersection = chars1 & chars2
    union = chars1 | chars2

    jaccard = len(intersection) / len(union)
    dice = 2 * len(intersection) / (len(chars1) + len(chars2))
    overlap = len(intersection) / min(len(chars1), len(chars2))

    return {
        "jaccard": round(jaccard, 4),
        "dice": round(dice, 4),
        "overlap": round(overlap, 4),
        "common_chars": "".join(sorted(intersection)),
    }


def meaning_similarity(mean1: str, mean2: str) -> dict:
    """计算两个释义的语义相似度。"""
    clean1 = clean_meaning(mean1)
    clean2 = clean_meaning(mean2)

    result = char_set_similarity(clean1, clean2)

    common_count = len(result.get("common_chars", ""))
    max_len = max(len(clean1), len(clean2))
    ratio = common_count / max_len if max_len > 0 else 0.0

    result["char_overlap_ratio"] = round(ratio, 4)
    result["combined_score"] = round(0.6 * result["jaccard"] + 0.4 * result["overlap"], 4)
    return result


def find_similar_by_meaning(
    target_meaning: str,
    candidates: list[dict],
    top_k: int = 20,
    min_score: float = 0.1,
) -> list[dict]:
    """在候选列表中找出与 target_meaning 语义最接近的项。"""
    results = []
    for cand in candidates:
        cand_mean = cand.get("meaning") or cand.get("mean", "")
        sim_info = meaning_similarity(target_meaning, cand_mean)
        if sim_info["combined_score"] >= min_score:
            results.append({**cand, "similarity": sim_info["combined_score"], "similarity_detail": sim_info})
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


def combined_similarity(
    target_pron: str,
    target_meaning: str,
    candidates: list[dict],
    top_k: int = 20,
    pron_weight: float = 0.5,
) -> list[dict]:
    """综合发音距离和语义相似度。"""
    from ipa_distance import syllable_distance

    results = []
    for cand in candidates:
        cand_pron = cand.get("pronunciation") or cand.get("pron", "")
        cand_mean = cand.get("meaning") or cand.get("mean", "")

        dist_info = syllable_distance(target_pron, cand_pron)
        pron_sim = 1.0 - dist_info["combined_distance"]

        mean_info = meaning_similarity(target_meaning, cand_mean)
        mean_sim = mean_info["combined_score"]

        combined = pron_weight * pron_sim + (1 - pron_weight) * mean_sim

        results.append(
            {
                **cand,
                "combined_score": round(combined, 4),
                "pron_similarity": round(pron_sim, 4),
                "mean_similarity": round(mean_sim, 4),
                "pron_distance_detail": dist_info,
                "mean_similarity_detail": mean_info,
            }
        )

    results.sort(key=lambda x: x["combined_score"], reverse=True)
    return results[:top_k]

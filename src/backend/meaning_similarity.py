"""
语义相似度计算模块

通过中文释义的字符重叠度来衡量两个词的语义相似度。
使用 Jaccard 相似度（交集/并集）和 Dice 系数。
拼音部分（如果有）的权重高于汉字部分。
"""

import re


def extract_pinyin(text: str) -> str:
    """提取释义中的拼音部分（前置拉丁字母）。

    支持的分隔符：：: 。
    """
    if not text:
        return ""
    # 匹配开头的拼音：拉丁字母（含 /），直到 ：: 或 。
    match = re.match(r"^([a-zA-Z\u00C0-\u024F]+(?:/[a-zA-Z\u00C0-\u024F]+)*)\s*[：:。]", text)
    if match:
        return match.group(1)
    return ""


def clean_meaning(text: str) -> str:
    """清洗释义文本，只保留中文字符，排除（自动）（使动）等语法标记。"""
    if not text:
        return ""
    # 去掉（自动）（使动）等语法标记
    text = re.sub(r"[（(][^）)]*[自动使动量词][^）)]*[）)]", "", text)
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


def _pinyin_edit_distance(py1: str, py2: str) -> int:
    """计算两个拼音字符串的编辑距离（Levenshtein）。"""
    m, n = len(py1), len(py2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if py1[i - 1] == py2[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[m][n]


def pinyin_similarity(py1: str, py2: str) -> float:
    """比较两个拼音字符串的相似度。

    拼音格式如 a 或 o/wo（多个读音用 / 分隔）。
    使用编辑距离计算模糊匹配：shēn → shen, shen → sheng 都能部分匹配。
    """
    if not py1 and not py2:
        return 1.0  # 都没有拼音 → 中性
    if not py1 or not py2:
        return 0.0  # 一个有拼音一个没有 → 不匹配

    # 标准化：去声调、转小写
    def normalize(py: str) -> str:
        py = py.lower()
        # 去掉声调符号（¯ ˊ ˇ ˋ）
        py = py.replace("\u0304", "").replace("\u0301", "").replace("\u030c", "").replace("\u0300", "")
        return py

    parts1 = py1.split("/")
    parts2 = py2.split("/")

    best = 0.0
    for p1 in parts1:
        n1 = normalize(p1)
        for p2 in parts2:
            n2 = normalize(p2)
            # 编辑距离相似度 = 1 - (edit_dist / max_len)
            max_len = max(len(n1), len(n2))
            if max_len == 0:
                sim = 1.0
            else:
                dist = _pinyin_edit_distance(n1, n2)
                sim = 1.0 - (dist / max_len)
            best = max(best, sim)
    return best


def meaning_similarity(mean1: str, mean2: str) -> dict:
    """计算两个释义的语义相似度。

    拼音部分（如有）权重高于汉字部分：
    - 拼音 60%，汉字 40%（当两者都有拼音时）
    - 仅汉字时退化为汉字相似度
    """
    py1 = extract_pinyin(mean1)
    py2 = extract_pinyin(mean2)
    clean1 = clean_meaning(mean1)
    clean2 = clean_meaning(mean2)

    # 汉字相似度
    hanzi_result = char_set_similarity(clean1, clean2)
    common_count = len(hanzi_result.get("common_chars", ""))
    max_len = max(len(clean1), len(clean2))
    ratio = common_count / max_len if max_len > 0 else 0.0
    hanzi_result["char_overlap_ratio"] = round(ratio, 4)

    # 拼音相似度
    py_sim = pinyin_similarity(py1, py2)

    # 综合：拼音权重更高
    has_py1 = bool(py1)
    has_py2 = bool(py2)

    if has_py1 or has_py2:
        # 任一方有拼音 → 拼音占 60%，汉字占 40%
        hanzi_score = hanzi_result["char_overlap_ratio"]
        # 如果汉字为空但另一方有汉字，惩罚
        if not clean1 or not clean2:
            hanzi_score = 0.0
        combined_score = 0.60 * py_sim + 0.40 * hanzi_score
    else:
        # 都没拼音 → 纯汉字比较
        combined_score = 0.6 * hanzi_result["jaccard"] + 0.4 * hanzi_result["overlap"]

    result = hanzi_result
    result["pinyin_similarity"] = round(py_sim, 4)
    result["combined_score"] = round(combined_score, 4)
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

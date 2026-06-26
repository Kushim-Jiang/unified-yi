"""
IPA 距离计算模块

计算两个 IPA 音节的相似度距离：
1. 辅音距离 — 基于发音特征（部位、方式、声带振动等）
2. 元音距离 — 基于发音特征（高度、前后、圆唇等）
3. 声调距离 — 基于调值数字差异
4. 音节距离 — 综合以上三者
"""

import re
from typing import Optional, Tuple

# ─── IPA 辅音特征表 ───────────────────────────────────────────

CONSONANT_FEATURES = {
    # 双唇音 Bilabial
    "p": {"place": 0, "manner": "plosive", "voicing": -1, "nasal": 0, "aspirated": 0},
    "pʰ": {"place": 0, "manner": "plosive", "voicing": -1, "nasal": 0, "aspirated": 1},
    "b": {"place": 0, "manner": "plosive", "voicing": 1, "nasal": 0, "aspirated": 0},
    "bʰ": {"place": 0, "manner": "plosive", "voicing": 1, "nasal": 0, "aspirated": 1},
    "m": {"place": 0, "manner": "nasal", "voicing": 1, "nasal": 1, "aspirated": 0},
    "m̥": {"place": 0, "manner": "nasal", "voicing": -1, "nasal": 1, "aspirated": 0},
    "ɓ": {"place": 0, "manner": "implosive", "voicing": 1, "nasal": 0, "aspirated": 0},
    "ʙ": {"place": 0, "manner": "trill", "voicing": 1, "nasal": 0, "aspirated": 0},
    # 唇齿音 Labiodental
    "f": {"place": 1, "manner": "fricative", "voicing": -1, "nasal": 0, "aspirated": 0},
    "v": {"place": 1, "manner": "fricative", "voicing": 1, "nasal": 0, "aspirated": 0},
    "ɱ": {"place": 1, "manner": "nasal", "voicing": 1, "nasal": 1, "aspirated": 0},
    "ʋ": {"place": 1, "manner": "approximant", "voicing": 1, "nasal": 0, "aspirated": 0},
    # 齿音 Dental
    "θ": {"place": 2, "manner": "fricative", "voicing": -1, "nasal": 0, "aspirated": 0},
    "ð": {"place": 2, "manner": "fricative", "voicing": 1, "nasal": 0, "aspirated": 0},
    "t̪": {"place": 2, "manner": "plosive", "voicing": -1, "nasal": 0, "aspirated": 0},
    "d̪": {"place": 2, "manner": "plosive", "voicing": 1, "nasal": 0, "aspirated": 0},
    "n̪": {"place": 2, "manner": "nasal", "voicing": 1, "nasal": 1, "aspirated": 0},
    # 齿龈音 Alveolar
    "t": {"place": 3, "manner": "plosive", "voicing": -1, "nasal": 0, "aspirated": 0},
    "tʰ": {"place": 3, "manner": "plosive", "voicing": -1, "nasal": 0, "aspirated": 1},
    "d": {"place": 3, "manner": "plosive", "voicing": 1, "nasal": 0, "aspirated": 0},
    "dʰ": {"place": 3, "manner": "plosive", "voicing": 1, "nasal": 0, "aspirated": 1},
    "n": {"place": 3, "manner": "nasal", "voicing": 1, "nasal": 1, "aspirated": 0},
    "n̥": {"place": 3, "manner": "nasal", "voicing": -1, "nasal": 1, "aspirated": 0},
    "r": {"place": 3, "manner": "trill", "voicing": 1, "nasal": 0, "aspirated": 0},
    "ɾ": {"place": 3, "manner": "tap", "voicing": 1, "nasal": 0, "aspirated": 0},
    "ɺ": {"place": 3, "manner": "tap", "voicing": 1, "nasal": 0, "lateral": 1},
    "s": {"place": 3, "manner": "fricative", "voicing": -1, "nasal": 0, "aspirated": 0},
    "sʰ": {"place": 3, "manner": "fricative", "voicing": -1, "nasal": 0, "aspirated": 1},
    "z": {"place": 3, "manner": "fricative", "voicing": 1, "nasal": 0, "aspirated": 0},
    "zʰ": {"place": 3, "manner": "fricative", "voicing": 1, "nasal": 0, "aspirated": 1},
    "ɬ": {"place": 3, "manner": "fricative", "voicing": -1, "nasal": 0, "lateral": 1},
    "ɮ": {"place": 3, "manner": "fricative", "voicing": 1, "nasal": 0, "lateral": 1},
    "l": {"place": 3, "manner": "lateral", "voicing": 1, "nasal": 0, "lateral": 1},
    "l̥": {"place": 3, "manner": "lateral", "voicing": -1, "nasal": 0, "lateral": 1},
    "ɹ": {"place": 3, "manner": "approximant", "voicing": 1, "nasal": 0},
    "ɹ̥": {"place": 3, "manner": "approximant", "voicing": -1, "nasal": 0},
    # 齿龈后音 Postalveolar
    "ʃ": {"place": 4, "manner": "fricative", "voicing": -1, "nasal": 0},
    "ʒ": {"place": 4, "manner": "fricative", "voicing": 1, "nasal": 0},
    "tʃ": {"place": 4, "manner": "affricate", "voicing": -1, "nasal": 0},
    "tʃʰ": {"place": 4, "manner": "affricate", "voicing": -1, "nasal": 0, "aspirated": 1},
    "dʒ": {"place": 4, "manner": "affricate", "voicing": 1, "nasal": 0},
    "dʒʰ": {"place": 4, "manner": "affricate", "voicing": 1, "nasal": 0, "aspirated": 1},
    # 卷舌音 Retroflex
    "ʈ": {"place": 5, "manner": "plosive", "voicing": -1, "nasal": 0},
    "ʈʰ": {"place": 5, "manner": "plosive", "voicing": -1, "nasal": 0, "aspirated": 1},
    "ɖ": {"place": 5, "manner": "plosive", "voicing": 1, "nasal": 0},
    "ɖʰ": {"place": 5, "manner": "plosive", "voicing": 1, "nasal": 0, "aspirated": 1},
    "ɳ": {"place": 5, "manner": "nasal", "voicing": 1, "nasal": 1},
    "ʂ": {"place": 5, "manner": "fricative", "voicing": -1, "nasal": 0},
    "ʐ": {"place": 5, "manner": "fricative", "voicing": 1, "nasal": 0},
    "ɻ": {"place": 5, "manner": "approximant", "voicing": 1, "nasal": 0},
    "ɭ": {"place": 5, "manner": "lateral", "voicing": 1, "nasal": 0, "lateral": 1},
    # 硬腭音 Palatal
    "c": {"place": 6, "manner": "plosive", "voicing": -1, "nasal": 0},
    "cʰ": {"place": 6, "manner": "plosive", "voicing": -1, "nasal": 0, "aspirated": 1},
    "ɟ": {"place": 6, "manner": "plosive", "voicing": 1, "nasal": 0},
    "ɟʰ": {"place": 6, "manner": "plosive", "voicing": 1, "nasal": 0, "aspirated": 1},
    "ɲ": {"place": 6, "manner": "nasal", "voicing": 1, "nasal": 1},
    "ç": {"place": 6, "manner": "fricative", "voicing": -1, "nasal": 0},
    "ʝ": {"place": 6, "manner": "fricative", "voicing": 1, "nasal": 0},
    "j": {"place": 6, "manner": "approximant", "voicing": 1, "nasal": 0},
    "ʎ": {"place": 6, "manner": "lateral", "voicing": 1, "nasal": 0, "lateral": 1},
    # 软腭音 Velar
    "k": {"place": 7, "manner": "plosive", "voicing": -1, "nasal": 0},
    "kʰ": {"place": 7, "manner": "plosive", "voicing": -1, "nasal": 0, "aspirated": 1},
    "ɡ": {"place": 7, "manner": "plosive", "voicing": 1, "nasal": 0},
    "ɡʰ": {"place": 7, "manner": "plosive", "voicing": 1, "nasal": 0, "aspirated": 1},
    "ŋ": {"place": 7, "manner": "nasal", "voicing": 1, "nasal": 1},
    "ŋ̊": {"place": 7, "manner": "nasal", "voicing": -1, "nasal": 1},
    "x": {"place": 7, "manner": "fricative", "voicing": -1, "nasal": 0},
    "ɣ": {"place": 7, "manner": "fricative", "voicing": 1, "nasal": 0},
    "ɰ": {"place": 7, "manner": "approximant", "voicing": 1, "nasal": 0},
    "ʟ": {"place": 7, "manner": "lateral", "voicing": 1, "nasal": 0, "lateral": 1},
    "w": {"place": 7, "manner": "approximant", "voicing": 1, "nasal": 0, "labialized": 1},
    # 小舌音 Uvular
    "q": {"place": 8, "manner": "plosive", "voicing": -1, "nasal": 0},
    "qʰ": {"place": 8, "manner": "plosive", "voicing": -1, "nasal": 0, "aspirated": 1},
    "ɢ": {"place": 8, "manner": "plosive", "voicing": 1, "nasal": 0},
    "ɴ": {"place": 8, "manner": "nasal", "voicing": 1, "nasal": 1},
    "χ": {"place": 8, "manner": "fricative", "voicing": -1, "nasal": 0},
    "ʁ": {"place": 8, "manner": "fricative", "voicing": 1, "nasal": 0},
    # 咽音 Pharyngeal
    "ħ": {"place": 9, "manner": "fricative", "voicing": -1, "nasal": 0},
    "ʕ": {"place": 9, "manner": "fricative", "voicing": 1, "nasal": 0},
    # 声门音 Glottal
    "ʔ": {"place": 10, "manner": "plosive", "voicing": 0, "nasal": 0},
    "h": {"place": 10, "manner": "fricative", "voicing": -1, "nasal": 0},
    "ɦ": {"place": 10, "manner": "fricative", "voicing": 1, "nasal": 0},
    # 龈腭音 Alveolo-palatal
    "tɕ": {"place": 11, "manner": "affricate", "voicing": -1, "nasal": 0},
    "tɕʰ": {"place": 11, "manner": "affricate", "voicing": -1, "nasal": 0, "aspirated": 1},
    "dʑ": {"place": 11, "manner": "affricate", "voicing": 1, "nasal": 0},
    "dʑʰ": {"place": 11, "manner": "affricate", "voicing": 1, "nasal": 0, "aspirated": 1},
    "ɕ": {"place": 11, "manner": "fricative", "voicing": -1, "nasal": 0},
    "ʑ": {"place": 11, "manner": "fricative", "voicing": 1, "nasal": 0},
    "ɲ": {"place": 11, "manner": "nasal", "voicing": 1, "nasal": 1},
    # 齿龈塞擦音 Alveolar affricates
    "ts": {"place": 3, "manner": "affricate", "voicing": -1, "nasal": 0},
    "tsʰ": {"place": 3, "manner": "affricate", "voicing": -1, "nasal": 0, "aspirated": 1},
    "dz": {"place": 3, "manner": "affricate", "voicing": 1, "nasal": 0},
    "dzʰ": {"place": 3, "manner": "affricate", "voicing": 1, "nasal": 0, "aspirated": 1},
    # 卷舌塞擦音 Retroflex affricates
    "tʂ": {"place": 5, "manner": "affricate", "voicing": -1, "nasal": 0},
    "tʂʰ": {"place": 5, "manner": "affricate", "voicing": -1, "nasal": 0, "aspirated": 1},
    "dʐ": {"place": 5, "manner": "affricate", "voicing": 1, "nasal": 0},
    "dʐʰ": {"place": 5, "manner": "affricate", "voicing": 1, "nasal": 0, "aspirated": 1},
    # 常见变体 alias
    "g": {"place": 7, "manner": "plosive", "voicing": 1, "nasal": 0},
}

CONSONANT_ALIASES = {
    "tɕ": "tɕ",
    "tɕʰ": "tɕʰ",
    "dʑ": "dʑ",
    "dʑʰ": "dʑʰ",
    "ts": "ts",
    "tsʰ": "tsʰ",
    "dz": "dz",
    "dzʰ": "dzʰ",
    "tʂ": "tʂ",
    "tʂʰ": "tʂʰ",
    "dʐ": "dʐ",
    "dʐʰ": "dʐʰ",
    "tʃ": "tʃ",
    "tʃʰ": "tʃʰ",
    "dʒ": "dʒ",
    "dʒʰ": "dʒʰ",
}

CONSONANT_NAMES = {
    "t͡s": "ts",
    "t͡sʰ": "tsʰ",
    "d͡z": "dz",
    "d͡zʰ": "dzʰ",
    "t͡ɕ": "tɕ",
    "t͡ɕʰ": "tɕʰ",
    "d͡ʑ": "dʑ",
    "d͡ʑʰ": "dʑʰ",
    "t͡ʂ": "tʂ",
    "t͡ʂʰ": "tʂʰ",
    "d͡ʐ": "dʐ",
    "d͡ʐʰ": "dʐʰ",
    "t͡ʃ": "tʃ",
    "t͡ʃʰ": "tʃʰ",
    "d͡ʒ": "dʒ",
    "d͡ʒʰ": "dʒʰ",
}

# ─── IPA 元音特征表 ───────────────────────────────────────────

VOWEL_FEATURES = {
    "i": {"height": 4, "backness": 0, "rounded": 0, "tense": 1},
    "y": {"height": 4, "backness": 0, "rounded": 1, "tense": 1},
    "ɪ": {"height": 3.5, "backness": 0.3, "rounded": 0, "tense": 0},
    "ʏ": {"height": 3.5, "backness": 0.3, "rounded": 1, "tense": 0},
    "ɨ": {"height": 4, "backness": 1, "rounded": 0, "tense": 1},
    "ʉ": {"height": 4, "backness": 1, "rounded": 1, "tense": 1},
    "ɯ": {"height": 4, "backness": 2, "rounded": 0, "tense": 1},
    "u": {"height": 4, "backness": 2, "rounded": 1, "tense": 1},
    "ʊ": {"height": 3.5, "backness": 1.7, "rounded": 1, "tense": 0},
    "e": {"height": 3, "backness": 0, "rounded": 0, "tense": 1},
    "ø": {"height": 3, "backness": 0, "rounded": 1, "tense": 1},
    "ɘ": {"height": 3, "backness": 1, "rounded": 0, "tense": 1},
    "ɵ": {"height": 3, "backness": 1, "rounded": 1, "tense": 1},
    "ɤ": {"height": 3, "backness": 2, "rounded": 0, "tense": 0},
    "o": {"height": 3, "backness": 2, "rounded": 1, "tense": 1},
    "ɛ": {"height": 2, "backness": 0, "rounded": 0, "tense": 0},
    "œ": {"height": 2, "backness": 0, "rounded": 1, "tense": 0},
    "ɜ": {"height": 2, "backness": 1, "rounded": 0, "tense": 0},
    "ɞ": {"height": 2, "backness": 1, "rounded": 1, "tense": 0},
    "ʌ": {"height": 2, "backness": 2, "rounded": 0, "tense": 0},
    "ɔ": {"height": 2, "backness": 2, "rounded": 1, "tense": 0},
    "æ": {"height": 1.5, "backness": 0, "rounded": 0, "tense": 0},
    "ɐ": {"height": 1.5, "backness": 1, "rounded": 0, "tense": 0},
    "a": {"height": 1, "backness": 0, "rounded": 0, "tense": 0},
    "ɶ": {"height": 1, "backness": 0, "rounded": 1, "tense": 0},
    "ᴀ": {"height": 1, "backness": 0.3, "rounded": 0, "tense": 0},
    "ɑ": {"height": 1, "backness": 2, "rounded": 0, "tense": 0},
    "ɒ": {"height": 1, "backness": 2, "rounded": 1, "tense": 0},
    "ə": {"height": 2, "backness": 1, "rounded": 0, "tense": 0},
    # 鼻化元音
    "ĩ": {"height": 4, "backness": 0, "rounded": 0, "tense": 1, "nasalized": 1},
    "ɛ̃": {"height": 2, "backness": 0, "rounded": 0, "tense": 0, "nasalized": 1},
    "ɑ̃": {"height": 1, "backness": 2, "rounded": 0, "tense": 0, "nasalized": 1},
    "ɔ̃": {"height": 2, "backness": 2, "rounded": 1, "tense": 0, "nasalized": 1},
}

VOWEL_ALIASES = {
    "o̹": "o",
    "ɯ̰": "ɯ",
    "ḭ": "i",
    "ḛ": "e",
    "ɛ̰": "ɛ",
    "æ̰": "æ",
    "ɑ̰": "ɑ",
    "o̰": "o",
    "ṵ": "u",
    "ɤ̰": "ɤ",
    "ɔ̰": "ɔ",
    "ɯ̤": "ɯ",
    "a̰": "a",
    "ɒ̰": "ɒ",
}


# ─── 音节解析 ──────────────────────────────────────────────────


def parse_syllable(pron: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not pron or "/" in pron:
        if pron and "/" in pron:
            pron = pron.split("/")[0]
        else:
            return None, None, None

    tone_match = re.findall(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", pron)
    tone = None
    if tone_match:
        tone_superscript = tone_match[-1]
        sup_to_normal = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
        tone = tone_superscript.translate(sup_to_normal)
        pron = pron.replace(tone_superscript, "")

    remaining = pron.strip()
    if not remaining:
        return None, None, tone

    consonant = None
    vowel_part = remaining

    for length in (3, 2, 1):
        for prefix, canon in list(CONSONANT_NAMES.items()) + list(CONSONANT_ALIASES.items()):
            if remaining.startswith(prefix) and len(prefix) == length:
                consonant = canon
                vowel_part = remaining[len(prefix) :]
                break
        if consonant:
            break

    if consonant is None:
        if remaining and remaining[0] in CONSONANT_FEATURES:
            consonant = remaining[0]
            vowel_part = remaining[1:]
        elif remaining:
            vowel_part = remaining

    vowel = vowel_part if vowel_part else None

    if vowel:
        vowel_clean = vowel.rstrip("\u032f\u0330\u0324\u0339\u031e\u031f\u0325\u030a")
        if vowel_clean in VOWEL_FEATURES:
            vowel = vowel_clean
        elif vowel in VOWEL_FEATURES:
            pass
        else:
            if vowel in VOWEL_ALIASES:
                vowel = VOWEL_ALIASES[vowel]

    return consonant, vowel, tone


# ─── 距离计算 ──────────────────────────────────────────────────

MANNER_RANK = {
    "plosive": 0,
    "implosive": 0.5,
    "affricate": 1,
    "fricative": 2,
    "nasal": 3,
    "lateral": 4,
    "tap": 5,
    "trill": 5.5,
    "approximant": 6,
}


def consonant_distance(c1: Optional[str], c2: Optional[str]) -> float:
    if c1 == c2:
        return 0.0
    if c1 is None and c2 is None:
        return 0.0
    if c1 is None or c2 is None:
        # ʔ（喉塞音）≈ 零声母，距离极小
        if c1 == "ʔ" or c2 == "ʔ":
            return 0.1
        return 1.0

    f1 = CONSONANT_FEATURES.get(c1)
    f2 = CONSONANT_FEATURES.get(c2)
    if f1 is None or f2 is None:
        return 0.5 if c1 != c2 else 0.0

    place_dist = abs(f1["place"] - f2["place"]) / 10.0
    r1 = MANNER_RANK.get(f1["manner"], 0)
    r2 = MANNER_RANK.get(f2["manner"], 0)
    manner_dist = abs(r1 - r2) / 6.0
    voicing_dist = abs(f1.get("voicing", 0) - f2.get("voicing", 0)) / 2.0
    nasal_dist = abs(f1.get("nasal", 0) - f2.get("nasal", 0))
    aspirated_dist = abs(f1.get("aspirated", 0) - f2.get("aspirated", 0))
    lateral_dist = abs(f1.get("lateral", 0) - f2.get("lateral", 0))

    dist = (
        0.30 * place_dist
        + 0.30 * manner_dist
        + 0.20 * voicing_dist
        + 0.10 * nasal_dist
        + 0.05 * aspirated_dist
        + 0.05 * lateral_dist
    )
    return min(dist, 1.0)


def vowel_distance(v1: Optional[str], v2: Optional[str]) -> float:
    if v1 == v2:
        return 0.0
    if v1 is None and v2 is None:
        return 0.0
    if v1 is None or v2 is None:
        return 1.0

    f1 = VOWEL_FEATURES.get(v1)
    f2 = VOWEL_FEATURES.get(v2)
    if f1 is None or f2 is None:
        return 0.5 if v1 != v2 else 0.0

    height_dist = abs(f1["height"] - f2["height"]) / 4.0
    backness_dist = abs(f1["backness"] - f2["backness"]) / 2.0
    rounded_dist = abs(f1["rounded"] - f2["rounded"])
    tense_dist = abs(f1.get("tense", 0) - f2.get("tense", 0))

    dist = 0.35 * height_dist + 0.30 * backness_dist + 0.20 * rounded_dist + 0.15 * tense_dist
    return min(dist, 1.0)


def tone_distance(t1: Optional[str], t2: Optional[str]) -> float:
    if t1 == t2:
        return 0.0
    if t1 is None and t2 is None:
        return 0.0
    if t1 is None or t2 is None:
        return 1.0
    try:

        def avg_tone(t):
            digits = [int(c) for c in t]
            return sum(digits) / len(digits)

        avg1 = avg_tone(t1)
        avg2 = avg_tone(t2)
        return min(abs(avg1 - avg2) / 4.0, 1.0)
    except (ValueError, ZeroDivisionError):
        return 1.0 if t1 != t2 else 0.0


def syllable_distance(pron1: str, pron2: str) -> dict:
    c1, v1, t1 = parse_syllable(pron1)
    c2, v2, t2 = parse_syllable(pron2)

    c_dist = consonant_distance(c1, c2)
    v_dist = vowel_distance(v1, v2)
    t_dist = tone_distance(t1, t2)
    combined = 0.40 * c_dist + 0.40 * v_dist + 0.20 * t_dist

    return {
        "consonant_distance": round(c_dist, 4),
        "vowel_distance": round(v_dist, 4),
        "tone_distance": round(t_dist, 4),
        "combined_distance": round(combined, 4),
        "parsed1": {"consonant": c1, "vowel": v1, "tone": t1},
        "parsed2": {"consonant": c2, "vowel": v2, "tone": t2},
    }


def find_similar_by_pronunciation(
    target_pron: str,
    candidates: list[dict],
    top_k: int = 20,
    max_distance: float = 0.6,
) -> list[dict]:
    results = []
    for cand in candidates:
        cand_pron = cand.get("pronunciation") or cand.get("pron", "")
        dist_info = syllable_distance(target_pron, cand_pron)
        if dist_info["combined_distance"] <= max_distance:
            results.append({**cand, "distance": dist_info["combined_distance"], "distance_detail": dist_info})
    results.sort(key=lambda x: x["distance"])
    return results[:top_k]

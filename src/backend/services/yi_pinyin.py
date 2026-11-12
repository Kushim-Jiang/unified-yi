"""彝语拼音方案（2010 正字法）→ IPA 转换。

对应关系存在 map/yi_pinyin_ipa.yaml，这里只做查表和拼接。
转换只用于「比较发音相似度」，不改写 book/ 里保存的原始拼音。
"""

from functools import lru_cache
from pathlib import Path

import yaml

MAP_FILE = Path(__file__).parent.parent.parent.parent / "map" / "yi_pinyin_ipa.yaml"


@lru_cache(maxsize=1)
def load_map(path: str | None = None) -> dict:
    with Path(path or MAP_FILE).open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for key in ("initials", "finals", "tones"):
        data[key] = {str(k): str(v) for k, v in (data.get(key) or {}).items()}
    return data


def _split_tone(syllable: str, tones: dict) -> tuple[str, str]:
    if len(syllable) > 1 and syllable[-1] in tones:
        return syllable[:-1], syllable[-1]
    return syllable, ""


def to_ipa(pronunciation: str, path: str | None = None) -> str:
    """把一个彝语拼音音节（可含多个读音，用 / 分隔）转成 IPA 音节。

    转不出来（空值、非法字母）时返回 ""，调用方回退到原始拼音。
    """
    if not pronunciation:
        return ""
    syllable = pronunciation.split("/")[0].strip().lower()
    if not syllable:
        return ""

    table = load_map(path)
    initials = table["initials"]
    finals = table["finals"]
    tones = table["tones"]

    stem, tone_letter = _split_tone(syllable, tones)
    tone = tones[tone_letter]

    # 声母：取最长匹配（3 → 1），零声母时为空
    initial = ""
    rest = stem
    for length in (3, 2, 1):
        candidate = stem[:length]
        if len(candidate) == length and candidate in initials:
            initial = initials[candidate]
            rest = stem[length:]
            break

    if rest not in finals:
        return ""
    return initial + finals[rest] + tone

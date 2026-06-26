"""
统一彝文数据管理后端 API
=========================
提供：
- 书籍/来源数据浏览
- 字符查询与搜索
- 字形对齐（手动关联 + 自动建议）
- IPA 距离 & 语义相似度 & 部首笔画相似度
- 多模型 OCR（OpenAI 兼容 / Anthropic）
"""

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from ipa_distance import find_similar_by_pronunciation, syllable_distance
from meaning_similarity import find_similar_by_meaning, meaning_similarity
from models import AlignmentGroupCreate, CharacterUpdate, SuggestBatchInput
from ocr import router as ocr_router
from radical_similarity import find_similar_by_radical_stroke, load_radical_order, radical_stroke_similarity
from services import AlignmentManager, DataLoader

# ─── 路径配置 ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent.parent
WEB_DIR = BASE_DIR / "src" / "frontend"
FONT_DIR = BASE_DIR / "font"

# ─── 服务初始化 ────────────────────────────────────────────────
loader = DataLoader(BASE_DIR)
alignment_mgr = AlignmentManager(loader)

# ─── 应用初始化 ────────────────────────────────────────────────
app = FastAPI(title="Unified Yi Character Manager", version="1.2.0")
app.include_router(ocr_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════
# API 路由
# ══════════════════════════════════════════════════════════════


# ─── 来源 API ────────────────────────────────────────────────


@app.get("/api/sources")
def list_sources():
    """列出所有数据来源。"""
    data = loader.get_data()
    sources = []
    for key in sorted(data.keys()):
        meta = loader.SOURCE_META.get(key, {"name": key, "region": "未知", "year": None, "group": "other"})
        sources.append(
            {
                "id": key,
                "name": meta["name"],
                "region": meta["region"],
                "year": meta["year"],
                "group": meta["group"],
                "character_count": len(data[key]),
            }
        )
    return sources


# ─── 字符 API ────────────────────────────────────────────────


@app.get("/api/characters/{source}")
def list_characters(
    source: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    search: str = Query("", description="搜索关键词"),
):
    """列出指定来源的字符（分页）。"""
    data = loader.get_data()
    if source not in data:
        raise HTTPException(status_code=404, detail=f"Source '{source}' not found")

    characters = data[source]
    if search:
        search_lower = search.lower()
        characters = [
            c
            for c in characters
            if search_lower in c["pronunciation"].lower()
            or search in c["meaning"]
            or search_lower in c["src_ref"].lower()
        ]

    total = len(characters)
    start = (page - 1) * page_size
    end = start + page_size
    page_data = characters[start:end]

    return {
        "source": source,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        "data": page_data,
    }


@app.get("/api/character/{source}/{src_ref}")
def get_character(source: str, src_ref: str):
    """获取单个字符的详细信息（含 RS 信息）。"""
    data = loader.get_data()
    if source not in data:
        raise HTTPException(status_code=404, detail=f"Source '{source}' not found")
    for char in data[source]:
        if char["src_ref"] == src_ref:
            return char
    raise HTTPException(status_code=404, detail=f"Character '{src_ref}' not found in '{source}'")


@app.get("/api/character/by-glyph/{source}")
def get_character_by_glyph(source: str, glyph: str = Query(...)):
    """通过字形查找字符。"""
    data = loader.get_data()
    if source not in data:
        raise HTTPException(status_code=404, detail=f"Source '{source}' not found")
    for char in data[source]:
        if char["glyph"] == glyph:
            return char
    raise HTTPException(status_code=404, detail="Glyph not found")


@app.get("/api/search")
def search_all(
    q: str = Query("", description="搜索关键词"),
    source: str = Query("", description="限定来源"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """在所有来源中搜索字符。"""
    data = loader.get_data()
    sources_to_search = [source] if source and source in data else list(data.keys())

    results = []
    for src in sources_to_search:
        for char in data[src]:
            if (
                q.lower() in char["pronunciation"].lower()
                or q in char["meaning"]
                or q.lower() in char["src_ref"].lower()
                or q in char["glyph"]
            ):
                results.append({**char, "source": src})

    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "query": q,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        "data": results[start:end],
    }


# ─── 字符更新 API（直接修改 book TSV）───────────────────────


@app.put("/api/characters/{source}/{src_ref}")
def update_character(source: str, src_ref: str, update: CharacterUpdate):
    """更新指定字符的 pronunciation 和 meaning（直接修改 TSV 文件）。"""
    data = loader.get_data()
    if source not in data:
        raise HTTPException(status_code=404, detail=f"Source '{source}' not found")

    found = None
    for char in data[source]:
        if char["src_ref"] == src_ref:
            found = char
            break
    if found is None:
        raise HTTPException(status_code=404, detail=f"Character '{src_ref}' not found in '{source}'")

    # Update in memory
    found["pronunciation"] = update.pronunciation
    found["meaning"] = update.meaning

    # Rewrite the TSV file
    filepath = loader.BOOK_DIR / f"{source}.tsv"
    with filepath.open(encoding="utf-8") as f:
        lines = f.readlines()

    for i in range(1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1] == src_ref:
            if len(parts) >= 4:
                parts[2] = update.pronunciation
                parts[3] = update.meaning
            elif len(parts) == 3:
                parts.append(update.meaning)
            elif len(parts) == 2:
                parts.append(update.pronunciation)
                parts.append(update.meaning)
            lines[i] = "\t".join(parts) + "\n"
            break

    with filepath.open("w", encoding="utf-8") as f:
        f.writelines(lines)

    loader.clear_cache()
    return {"status": "ok", "character": found}


# ─── 对齐 API ────────────────────────────────────────────────


@app.get("/api/alignments")
def list_alignments():
    """列出所有对齐组（按部首-笔画排序）。"""
    return alignment_mgr.list_alignments()


@app.post("/api/alignments")
def create_alignment_group(al: AlignmentGroupCreate):
    """创建/扩展一个对齐组（多对多）。"""
    try:
        return alignment_mgr.create_or_merge(al)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── 实时编辑当前工作区（必须在 {group_id} 之前注册）───────


@app.get("/api/alignments/current-group")
def get_current_group():
    """获取当前正在编辑的对齐组。"""
    return alignment_mgr.get_current_group()


@app.post("/api/alignments/current-group")
def save_current_group(body: AlignmentGroupCreate):
    """实时保存当前正在编辑的对齐组。"""
    return alignment_mgr.save_current_group(body)


@app.delete("/api/alignments/current-group")
def clear_current_group():
    """清空当前工作区。"""
    return alignment_mgr.clear_current_group()


# ─── 静态对齐组 CRUD ──────────────────────────────────────────


@app.delete("/api/alignments/{group_id}")
def delete_alignment_group(group_id: int):
    """删除整个对齐组。"""
    try:
        return alignment_mgr.delete_group(group_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/alignments/{group_id}/entries/{entry_index}")
def remove_entry_from_group(group_id: int, entry_index: int):
    """从对齐组中移除一个条目。"""
    try:
        return alignment_mgr.remove_entry(group_id, entry_index)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── IPA 距离 / 语义相似度 / 部首相似度 API ──────────────────


@app.get("/api/ipa-distance")
def calc_ipa_distance(pron1: str = Query(...), pron2: str = Query(...)):
    """计算两个 IPA 音节的发音距离。"""
    return syllable_distance(pron1, pron2)


@app.get("/api/meaning-similarity")
def calc_meaning_similarity(mean1: str = Query(...), mean2: str = Query(...)):
    """计算两个释义的语义相似度。"""
    return meaning_similarity(mean1, mean2)


@app.get("/api/radical-similarity")
def calc_radical_similarity(
    rad1: str = Query(...),
    stroke1: int = Query(...),
    rad2: str = Query(...),
    stroke2: int = Query(...),
):
    """计算两个部首-笔画的字形结构相似度。"""
    return radical_stroke_similarity(rad1, stroke1, rad2, stroke2)


@app.get("/api/radical-order")
def get_radical_order():
    """获取部首排列顺序列表。"""
    radicals = load_radical_order()
    return {"total": len(radicals), "radicals": radicals}


# ─── 部首数据 API（读写 rs/ TSV）───────────────────────────


@app.get("/api/radical-data/{source}")
def list_radical_data(source: str):
    """获取指定来源的部首笔画数据。"""
    try:
        # Get book data to know all characters
        data = loader.get_data()
        if source not in data:
            raise HTTPException(status_code=404, detail=f"Source '{source}' not found")

        # Load RS data
        rs_data = loader.load_rs_data(source)
        radical_index = loader.get_radical_index()

        # Build character list with RS info
        result = []
        for char in data[source]:
            glyph = char["glyph"]
            rs = rs_data.get(glyph)
            if rs:
                rad_str = rs["radical"]
                stroke_str = rs["other_stroke"]
                radicals = [r.strip() for r in rad_str.split(",") if r.strip()]
                strokes = []
                for s in stroke_str.split(","):
                    s = s.strip()
                    strokes.append(int(s) if s.isdigit() else 0)
            else:
                radicals = []
                strokes = []

            result.append(
                {
                    "glyph": glyph,
                    "src_ref": char["src_ref"],
                    "radical": ",".join(radicals),
                    "other_stroke": ",".join(str(s) for s in strokes),
                    "radicals": radicals,
                    "strokes": strokes,
                    "has_rs": rs is not None,
                }
            )

        return {
            "source": source,
            "total": len(result),
            "radicals": list(radical_index.keys()),
            "data": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/radical-data/{source}/{glyph}")
def update_radical_data(source: str, glyph: str, radical: str = Query(...), other_stroke: str = Query("0")):
    """更新某个字符的部首和笔画数。
    radical 支持逗号分隔（多个部首），other_stroke 也支持逗号分隔。
    如果 rs/{source}.tsv 不存在则自动创建。"""
    filepath = loader.RS_DIR / f"{source}.tsv"
    # Auto-create RS file if missing
    if not filepath.exists():
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with filepath.open("w", encoding="utf-8") as f:
            f.write("glyph_unified\tradical\tother_stroke\n")
        lines = ["glyph_unified\tradical\tother_stroke\n"]
    else:
        with filepath.open(encoding="utf-8") as f:
            lines = f.readlines()

    header = lines[0].strip() if lines else ""
    if not header:
        lines = ["glyph_unified\tradical\tother_stroke\n"]

    # Find and update existing entry
    found = False
    for i in range(1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        parts = line.split("\t")
        if parts[0] == glyph:
            parts[1] = radical
            parts[2] = other_stroke
            lines[i] = "\t".join(parts) + "\n"
            found = True
            break

    if not found:
        lines.append(f"{glyph}\t{radical}\t{other_stroke}\n")

    with filepath.open("w", encoding="utf-8") as f:
        f.writelines(lines)

    loader.clear_cache()
    return {"status": "ok", "glyph": glyph, "radical": radical, "other_stroke": other_stroke}


@app.get("/api/suggest-alignments/{source}/{src_ref}")
def suggest_alignments(
    source: str,
    src_ref: str,
    target_source: str = Query("", description="目标来源"),
    method: str = Query("combined", description="pronunciation | meaning | radical | combined"),
    top_k: int = Query(20, ge=1, le=100),
):
    """
    为给定字符建议可能的对齐目标。
    支持四种方法：
      - pronunciation: 仅发音距离
      - meaning: 仅语义相似度
      - radical: 仅部首笔画相似度
      - combined: 综合三者
    """
    data = loader.get_data()
    if source not in data:
        raise HTTPException(status_code=404, detail=f"Source '{source}' not found")

    target_char = None
    for c in data[source]:
        if c["src_ref"] == src_ref:
            target_char = c
            break
    if target_char is None:
        raise HTTPException(status_code=404, detail=f"Character '{src_ref}' not found in '{source}'")

    candidates = []
    search_sources = [target_source] if target_source and target_source in data else [s for s in data if s != source]
    for s in search_sources:
        for c in data[s]:
            # align 匹配相似度时，只匹配有 meaning 的候选
            if (c.get("meaning") or "").strip():
                candidates.append({**c, "source": s})

    if not candidates:
        return {"target": {**target_char, "source": source}, "suggestions": []}

    if method == "pronunciation":
        suggestions = find_similar_by_pronunciation(target_char["pronunciation"], candidates, top_k=top_k)
    elif method == "meaning":
        suggestions = find_similar_by_meaning(target_char["meaning"], candidates, top_k=top_k)
    elif method == "radical":
        suggestions = find_similar_by_radical_stroke(target_char["glyph"], source, candidates, top_k=top_k)
    else:
        suggestions = _combined_three_way(target_char, candidates, source, top_k)

    return {
        "target": {**target_char, "source": source},
        "method": method,
        "suggestions": suggestions,
    }


def _combined_three_way(target_char: dict, candidates: list[dict], source: str, top_k: int) -> list[dict]:
    """三路综合相似度：优先释义拉丁拼音，回退 IPA。"""
    from meaning_similarity import extract_pinyin, pinyin_similarity

    results = []
    for cand in candidates:
        cand_mean = cand.get("meaning", "")
        t_lat = extract_pinyin(target_char.get("meaning", ""))
        c_lat = extract_pinyin(cand_mean)
        ipa_t = target_char.get("pronunciation", "")
        ipa_c = cand.get("pronunciation", "")

        if t_lat and c_lat:
            pron_sim = pinyin_similarity(t_lat, c_lat)
            w_pron, w_mean, w_rs = 0.50, 0.30, 0.20
            dist_info = {"method": "latin_pinyin", "a": t_lat, "b": c_lat}
            mean_info = meaning_similarity(target_char["meaning"], cand_mean)
            mean_sim = mean_info["combined_score"]
        elif ipa_t and ipa_c:
            dist_info = syllable_distance(ipa_t, ipa_c)
            pron_sim = 1.0 - dist_info["combined_distance"]
            w_pron, w_mean, w_rs = 0.50, 0.30, 0.20
            mean_info = meaning_similarity(target_char["meaning"], cand_mean)
            mean_sim = mean_info["combined_score"]
        else:
            dist_info = {"method": "none"}
            pron_sim = 0.0
            w_pron, w_mean, w_rs = 0.0, 0.60, 0.40
            shared = _shared_char_count(target_char.get("meaning", ""), cand_mean)
            mean_sim = min(shared / 10.0, 1.0)
            mean_info = {"combined_score": mean_sim, "shared_count": shared}

        target_rs = loader.get_char_rs(source, target_char["glyph"])
        cand_rs = loader.get_char_rs(cand.get("source", ""), cand.get("glyph", ""))
        if target_rs and cand_rs:
            rs_info = radical_stroke_similarity(
                target_rs.get("radical"),
                target_rs.get("other_stroke"),
                cand_rs.get("radical"),
                cand_rs.get("other_stroke"),
            )
            rs_sim = rs_info["combined_score"]
        else:
            rs_info = {"radical_similarity": 0.0, "stroke_similarity": 0.5, "combined_score": 0.15}
            rs_sim = 0.15

        combined = w_pron * pron_sim + w_mean * mean_sim + w_rs * rs_sim

        results.append(
            {
                **cand,
                "combined_score": round(combined, 4),
                "pron_similarity": round(pron_sim, 4),
                "mean_similarity": round(mean_sim, 4),
                "rs_similarity": round(rs_sim, 4),
                "shared_char_count": mean_info.get("shared_count", 0),
                "pron_distance_detail": dist_info,
                "mean_similarity_detail": mean_info,
                "rs_similarity_detail": rs_info,
            }
        )

    results.sort(key=lambda x: x["combined_score"], reverse=True)
    return results[:top_k]


def _shared_char_count(text1: str, text2: str) -> int:
    """统计两个释义之间共享的中文字符数（去重后），对连续匹配给予额外加分。"""

    def _strip_grammar(t):
        return re.sub(r"[（(][^）)]*[自动使动量词][^）)]*[）)]", "", t)

    a = _strip_grammar(text1)
    b = _strip_grammar(text2)
    a_chars = re.findall(r"[\u4e00-\u9fff]", a)
    b_chars = re.findall(r"[\u4e00-\u9fff]", b)
    chars1 = set(a_chars)
    chars2 = set(b_chars)
    shared_unique = len(chars1 & chars2)
    if shared_unique == 0:
        return 0

    sa = "".join(a_chars)
    sb = "".join(b_chars)
    bonus = 0
    for length in range(len(sa), 0, -1):
        for start in range(len(sa) - length + 1):
            sub = sa[start : start + length]
            if sub in sb:
                bonus = length - 1
                break
        if bonus:
            break
    i = 0
    while i < len(sa):
        j = i + 1
        while j <= len(sa) and sa[i:j] in sb:
            j += 1
        run_len = (j - 1) - i
        if run_len >= 2:
            bonus = max(bonus, run_len - 1)
        i += max(run_len, 1)
    return shared_unique + bonus


def _similarity_between_chars(char_a: dict, source_a: str, char_b: dict, source_b: str) -> dict:
    """计算两个字符之间 3 路综合相似度 (释义拉丁拼音 + 语义 + 部首)。

    优先使用释义中的拉丁拼音（如 shen/sheng）进行模糊匹配，
    回退到 IPA 注音。
    """
    from meaning_similarity import extract_pinyin, pinyin_similarity

    # 提取释义中的拉丁拼音
    lat_py_a = extract_pinyin(char_a.get("meaning", ""))
    lat_py_b = extract_pinyin(char_b.get("meaning", ""))
    # IPA 注音作为后备
    ipa_a = char_a.get("pronunciation", "")
    ipa_b = char_b.get("pronunciation", "")

    if lat_py_a and lat_py_b:
        # 优先：释义拉丁拼音模糊匹配
        pron_sim = pinyin_similarity(lat_py_a, lat_py_b)
        w_pron, w_mean, w_rs = 0.50, 0.30, 0.20
        pron = {"latin_pinyin_a": lat_py_a, "latin_pinyin_b": lat_py_b, "method": "latin_pinyin"}
        mean = meaning_similarity(char_a["meaning"], char_b["meaning"])
        mean_sim = mean["combined_score"]
        shared_count = _shared_char_count(char_a.get("meaning", ""), char_b.get("meaning", ""))
    elif ipa_a and ipa_b:
        # 后备：IPA 注音距离
        pron = syllable_distance(ipa_a, ipa_b)
        pron_sim = 1.0 - pron["combined_distance"]
        w_pron, w_mean, w_rs = 0.50, 0.30, 0.20
        mean = meaning_similarity(char_a["meaning"], char_b["meaning"])
        mean_sim = mean["combined_score"]
        shared_count = _shared_char_count(char_a.get("meaning", ""), char_b.get("meaning", ""))
    else:
        pron_sim = 0.0
        w_pron, w_mean, w_rs = 0.0, 0.60, 0.40
        pron = {"method": "none"}
        shared_count = _shared_char_count(char_a.get("meaning", ""), char_b.get("meaning", ""))
        mean_sim = min(shared_count / 10.0, 1.0)
        mean = {"combined_score": mean_sim, "shared_count": shared_count}

    rs_a = loader.get_char_rs(source_a, char_a["glyph"])
    rs_b = loader.get_char_rs(source_b, char_b["glyph"])
    if rs_a and rs_b:
        rs = radical_stroke_similarity(
            rs_a.get("radical"),
            rs_a.get("other_stroke"),
            rs_b.get("radical"),
            rs_b.get("other_stroke"),
        )
        rs_sim = rs["combined_score"]
    else:
        rs = {"radical_similarity": 0.0, "stroke_similarity": 0.5, "combined_score": 0.15}
        rs_sim = 0.15

    combined = w_pron * pron_sim + w_mean * mean_sim + w_rs * rs_sim
    return {
        "combined_score": round(combined, 4),
        "pron_similarity": round(pron_sim, 4),
        "mean_similarity": round(mean_sim, 4),
        "rs_similarity": round(rs_sim, 4),
        "shared_char_count": shared_count,
        "pron_detail": pron,
        "mean_detail": mean,
        "rs_detail": rs,
    }


def _best_similarity_to_group(candidate_char: dict, candidate_source: str, group_entry_chars: list[dict]) -> dict:
    """计算一个候选字符与一组条目中最佳匹配的综合相似度。"""
    best = {"combined_score": 0.0}
    for ge in group_entry_chars:
        sim = _similarity_between_chars(candidate_char, candidate_source, ge["char"], ge["source"])
        if sim["combined_score"] > best["combined_score"]:
            best = sim
    return best


# ─── 批量建议 API ────────────────────────────────────────────


@app.post("/api/suggest-alignments/batch")
def suggest_alignments_batch(body: SuggestBatchInput):
    """批量建议：给定一组已选条目，对每个尚未出现的来源分别给出最佳匹配建议。"""
    data = loader.get_data()
    if not body.entries:
        raise HTTPException(status_code=400, detail="Need at least one entry")

    group_chars = []
    for ref in body.entries:
        src = loader.source_from_ref(ref)
        if not src or src not in data:
            continue
        for c in data[src]:
            if c["src_ref"] == ref:
                group_chars.append({"source": src, "char": c})
                break
    if not group_chars:
        raise HTTPException(status_code=404, detail="No valid entries found")

    used_pairs = {(gc["source"], gc["char"]["src_ref"]) for gc in group_chars}
    existing_alignments = loader.get_alignments()
    aligned_pairs = set()
    for grp in existing_alignments:
        for ref in grp.get("entries", []):
            src = loader.source_from_ref(ref)
            aligned_pairs.add((src, ref))

    suggestions_by_source = {}
    for src_name in data:
        candidates = []
        for c in data[src_name]:
            if (src_name, c["src_ref"]) in used_pairs:
                continue
            if (src_name, c["src_ref"]) in aligned_pairs:
                continue
            # align 匹配相似度时，只匹配有 meaning 的候选
            if not (c.get("meaning") or "").strip():
                continue
            candidates.append({**c, "source": src_name})
        if not candidates:
            continue
        scored = []
        for cand in candidates:
            sim = _best_similarity_to_group(cand, src_name, group_chars)
            if sim["combined_score"] > 0:
                scored.append({**cand, **sim})
        scored.sort(key=lambda x: x["combined_score"], reverse=True)
        if scored:
            suggestions_by_source[src_name] = scored[:15]

    return {"target_group_size": len(group_chars), "suggestions_by_source": suggestions_by_source}


@app.post("/api/suggest-groups/batch")
def suggest_groups_batch(body: SuggestBatchInput):
    """给定一组已选条目，找出与之相似的所有现有对齐组（建议合并）。"""
    groups = loader.get_alignments()
    data = loader.get_data()

    query_chars = []
    for ref in body.entries:
        src = loader.source_from_ref(ref)
        if not src or src not in data:
            continue
        for c in data[src]:
            if c["src_ref"] == ref:
                query_chars.append({"source": src, "char": c})
                break
    if not query_chars:
        raise HTTPException(status_code=404, detail="No valid entries found")

    query_keys = {(qc["source"], qc["char"]["src_ref"]) for qc in query_chars}

    results = []
    for grp in groups:
        grp_entries = grp.get("entries", [])
        grp_keys = {(loader.source_from_ref(e), e) for e in grp_entries}
        if query_keys & grp_keys:
            continue
        grp_chars = []
        for ref in grp_entries:
            src = loader.source_from_ref(ref)
            if src in data:
                for c in data[src]:
                    if c["src_ref"] == ref:
                        grp_chars.append({"source": src, "char": c})
                        break
        if not grp_chars:
            continue

        q_to_g_best = g_to_q_best = 0.0
        for qc in query_chars:
            sim = _best_similarity_to_group(qc["char"], qc["source"], grp_chars)
            q_to_g_best = max(q_to_g_best, sim["combined_score"])
        for gc in grp_chars:
            sim = _best_similarity_to_group(gc["char"], gc["source"], query_chars)
            g_to_q_best = max(g_to_q_best, sim["combined_score"])

        best_sim = max(q_to_g_best, g_to_q_best)
        if best_sim >= 0.2:
            preview = []
            for ref in grp_entries[:4]:
                src = loader.source_from_ref(ref)
                char_obj = None
                if src in data:
                    for c in data[src]:
                        if c["src_ref"] == ref:
                            char_obj = c
                            break
                preview.append({"source": src, "src_ref": ref, "char": char_obj})
            results.append(
                {
                    "group_id": grp.get("id"),
                    "similarity": round(best_sim, 4),
                    "entries_count": len(grp_entries),
                    "preview": preview,
                }
            )

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return {"suggestions": results[:10]}


# ─── 全面比较 API ────────────────────────────────────────────


@app.get("/api/compare/{source_a}/{src_ref_a}/{source_b}/{src_ref_b}")
def compare_two(source_a: str, src_ref_a: str, source_b: str, src_ref_b: str):
    """全面比较两个字符：发音 + 语义 + 部首笔画。"""
    data = loader.get_data()
    if source_a not in data or source_b not in data:
        raise HTTPException(status_code=404, detail="Source not found")

    char_a = char_b = None
    for c in data[source_a]:
        if c["src_ref"] == src_ref_a:
            char_a = c
            break
    for c in data[source_b]:
        if c["src_ref"] == src_ref_b:
            char_b = c
            break
    if char_a is None or char_b is None:
        raise HTTPException(status_code=404, detail="Character not found")

    pron_dist = syllable_distance(char_a["pronunciation"], char_b["pronunciation"])
    mean_sim = meaning_similarity(char_a["meaning"], char_b["meaning"])
    rs_a = loader.get_char_rs(source_a, char_a["glyph"])
    rs_b = loader.get_char_rs(source_b, char_b["glyph"])
    if rs_a and rs_b:
        rs_info = radical_stroke_similarity(
            rs_a.get("radical"),
            rs_a.get("other_stroke"),
            rs_b.get("radical"),
            rs_b.get("other_stroke"),
        )
    else:
        rs_info = {"radical_similarity": 0.0, "stroke_similarity": 0.5, "combined_score": 0.15}

    pron_sim = 1.0 - pron_dist["combined_distance"]
    combined = round(0.25 * pron_sim + 0.50 * mean_sim["combined_score"] + 0.25 * rs_info["combined_score"], 4)

    return {
        "char_a": {**char_a, "source": source_a},
        "char_b": {**char_b, "source": source_b},
        "pronunciation_distance": pron_dist,
        "meaning_similarity": mean_sim,
        "radical_stroke_similarity": rs_info,
        "combined_score": combined,
    }


# ─── 映射 (YAML) API ──────────────────────────────────────────


@app.get("/api/mappings")
def list_mappings():
    """列出所有已有的 YAML 映射文件及其统计。"""
    mappings = []
    for yaml_file in sorted(loader.MAP_DIR.glob("*.yaml")):
        data_map = loader.load_yaml(yaml_file.stem)
        mappings.append({"file": yaml_file.name, "stem": yaml_file.stem, "pair_count": len(data_map)})
    return mappings


@app.get("/api/mappings/{name}")
def get_mapping(name: str):
    """获取指定映射文件的完整内容。"""
    data_map = loader.load_yaml(name)
    return {"name": name, "mappings": data_map, "count": len(data_map)}


@app.post("/api/mappings/{name}")
def add_mapping(name: str, glyph_a: str = Query(...), glyph_b: str = Query(...)):
    """向 YAML 映射文件中添加一对映射。"""
    import yaml

    filepath = loader.MAP_DIR / f"{name}.yaml"
    if not filepath.exists():
        filepath = loader.RS_DIR / f"{name}.yaml"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Mapping file '{name}' not found")

    existing = loader.load_yaml(name)
    existing[glyph_a] = glyph_b
    with filepath.open("w", encoding="utf-8") as f:
        yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)
    return {"status": "ok", "glyph_a": glyph_a, "glyph_b": glyph_b}


# ─── 字形集群分析 ─────────────────────────────────────────────


@app.get("/api/clusters/{glyph}")
def get_glyph_cluster(glyph: str):
    """获取某个字形在所有来源中的出现情况及所在的 alignment groups。"""
    data = loader.get_data()
    groups = loader.get_alignments()

    occurrences = []
    for src_name, chars in data.items():
        for char in chars:
            if char["glyph"] == glyph:
                occurrences.append({**char, "source": src_name})

    linked_groups = []
    for grp in groups:
        for occ in occurrences:
            for ref in grp.get("entries", []):
                src = loader.source_from_ref(ref)
                if src == occ["source"] and ref == occ["src_ref"]:
                    others = []
                    for ore in grp["entries"]:
                        if ore == ref:
                            continue
                        osrc = loader.source_from_ref(ore)
                        char_info = None
                        if osrc in data:
                            for c in data[osrc]:
                                if c["src_ref"] == ore:
                                    char_info = c
                                    break
                        others.append({"source": osrc, "src_ref": ore, "char": char_info})
                    if others:
                        linked_groups.append({"group_id": grp["id"], "via": occ["src_ref"], "peers": others})
                    break

    return {"glyph": glyph, "occurrences": occurrences, "linked_groups": linked_groups}


# ─── 统计 API ─────────────────────────────────────────────────


@app.get("/api/stats")
def get_stats():
    """获取总体统计信息。"""
    data = loader.get_data()
    alignments = loader.get_alignments()
    total_chars = sum(len(v) for v in data.values())
    return {
        "total_sources": len(data),
        "total_characters": total_chars,
        "total_alignments": len(alignments),
        "sources": {k: len(v) for k, v in data.items()},
    }


# ─── 静态文件挂载 ─────────────────────────────────────────────

if FONT_DIR.exists():
    app.mount("/font", StaticFiles(directory=str(FONT_DIR)), name="font")

if WEB_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(WEB_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(WEB_DIR / "js")), name="js")


# ─── 前端页面路由 ─────────────────────────────────────────────


@app.get("/")
def serve_index():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/align.html")
def serve_align():
    return FileResponse(str(WEB_DIR / "align.html"))


@app.get("/entry.html")
def serve_entry():
    return FileResponse(str(WEB_DIR / "entry.html"))


@app.get("/groups.html")
def serve_groups():
    return FileResponse(str(WEB_DIR / "groups.html"))


@app.get("/radicals.html")
def serve_radicals():
    return FileResponse(str(WEB_DIR / "radicals.html"))


# ─── 启动 ──────────────────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)

"""
统一彝文数据管理后端 API
=========================
提供：
- 书籍/来源数据浏览
- 字符查询与搜索
- 字形对齐（手动关联 + 自动建议）
- IPA 距离 & 语义相似度 & 部首笔画相似度
"""

import json
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ipa_distance import (
    syllable_distance,
    find_similar_by_pronunciation,
)
from meaning_similarity import (
    meaning_similarity,
    find_similar_by_meaning,
    combined_similarity,
)
from radical_similarity import (
    radical_stroke_similarity,
    find_similar_by_radical_stroke,
    get_char_rs,
)

# ─── 路径配置 ──────────────────────────────────────────────────
# BASE_DIR = repo root (go up 3 levels from src/backend/)
BASE_DIR = Path(__file__).parent.parent.parent
BOOK_DIR = BASE_DIR / "book"
MAP_DIR = BASE_DIR / "map"
FONT_DIR = BASE_DIR / "font"
RS_DIR = BASE_DIR / "rs"
WEB_DIR = BASE_DIR / "src" / "frontend"
ALIGNMENTS_FILE = BASE_DIR / "alignments.json"

# ─── 应用初始化 ────────────────────────────────────────────────

app = FastAPI(title="Unified Yi Character Manager", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── 数据加载 ──────────────────────────────────────────────────


def load_tsv(filename: str) -> list[dict]:
    """加载 book/ TSV 文件为字典列表，并尝试附加 RS 信息。"""
    filepath = BOOK_DIR / f"{filename}.tsv"
    if not filepath.exists():
        raise FileNotFoundError(f"Source file not found: {filename}.tsv")
    with filepath.open(encoding="utf-8") as f:
        lines = f.readlines()
    data = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 4:
            data.append(
                {
                    "glyph": parts[0],
                    "src_ref": parts[1],
                    "pronunciation": parts[2],
                    "meaning": parts[3],
                }
            )
    # 附加 RS 信息
    rs_data = _load_rs_file(filename)
    for char in data:
        rs = rs_data.get(char["glyph"])
        if rs:
            char["radical"] = rs["radical"]
            char["other_stroke"] = rs["other_stroke"]
    return data


def _load_rs_file(source: str) -> dict[str, dict]:
    """加载 rs/{source}.tsv。"""
    filepath = RS_DIR / f"{source}.tsv"
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
                "other_stroke": int(parts[2]) if parts[2].strip().isdigit() else 0,
            }
    return data


def load_yaml(filename: str) -> dict:
    """加载 YAML 文件。"""
    filepath = MAP_DIR / f"{filename}.yaml"
    if not filepath.exists():
        filepath = RS_DIR / f"{filename}.yaml"
    if not filepath.exists():
        return {}
    with filepath.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_alignments() -> list[dict]:
    """加载已保存的对齐数据。"""
    if ALIGNMENTS_FILE.exists():
        with ALIGNMENTS_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    return []


def save_alignments(data: list[dict]):
    """保存对齐数据。"""
    with ALIGNMENTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_all_data() -> dict[str, list[dict]]:
    """加载所有书籍数据到内存缓存。"""
    data = {}
    for tsv_file in sorted(BOOK_DIR.glob("*.tsv")):
        source_name = tsv_file.stem
        data[source_name] = load_tsv(source_name)
    return data


# 全局缓存
DATA_CACHE: dict[str, list[dict]] = {}
ALIGNMENTS_CACHE: list[dict] = []


def get_data() -> dict[str, list[dict]]:
    global DATA_CACHE
    if not DATA_CACHE:
        DATA_CACHE = load_all_data()
    return DATA_CACHE


def get_alignments() -> list[dict]:
    global ALIGNMENTS_CACHE
    if not ALIGNMENTS_CACHE:
        ALIGNMENTS_CACHE = load_alignments()
    return ALIGNMENTS_CACHE


# ─── 来源元信息 ────────────────────────────────────────────────

SOURCE_META = {
    "u0": {"name": "通用彝文字典 (2016)", "region": "通用", "year": 2016, "group": "unified"},
    "u1": {"name": "滇川黔桂彝文字典 (2001)", "region": "通用", "year": 2001, "group": "unified"},
    "q0": {"name": "简明彝汉字典 贵州本 (2018)", "region": "贵州", "year": 2018, "group": "guizhou"},
    "d0": {"name": "云南省规范彝文彝汉词典 (2014)", "region": "云南", "year": 2014, "group": "yunnan"},
    "d1": {"name": "云南规范彝文字汇本 (1991+)", "region": "云南", "year": 1991, "group": "yunnan"},
    "d2": {"name": "云南省十四种民族文字方案集合", "region": "云南", "year": None, "group": "yunnan"},
    "d3": {"name": "滇南彝文字典 (2005)", "region": "云南", "year": 2005, "group": "yunnan"},
    "d4": {"name": "彝汉简明词典 (1984)", "region": "云南", "year": 1984, "group": "yunnan"},
    "d5": {"name": "彝汉字典 楚雄本 (1995)", "region": "云南", "year": 1995, "group": "yunnan"},
    "d6": {"name": "古彝文常用字典 (2014)", "region": "云南", "year": 2014, "group": "yunnan"},
}


# ─── API 路由 ──────────────────────────────────────────────────


@app.get("/api/sources")
def list_sources():
    """列出所有数据来源。"""
    data = get_data()
    sources = []
    for key in sorted(data.keys()):
        meta = SOURCE_META.get(key, {"name": key, "region": "未知", "year": None, "group": "other"})
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


@app.get("/api/characters/{source}")
def list_characters(
    source: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    search: str = Query("", description="搜索关键词"),
):
    """列出指定来源的字符（分页）。"""
    data = get_data()
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
    data = get_data()
    if source not in data:
        raise HTTPException(status_code=404, detail=f"Source '{source}' not found")

    for char in data[source]:
        if char["src_ref"] == src_ref:
            return char
    raise HTTPException(status_code=404, detail=f"Character '{src_ref}' not found in '{source}'")


@app.get("/api/character/by-glyph/{source}")
def get_character_by_glyph(source: str, glyph: str = Query(...)):
    """通过字形查找字符。"""
    data = get_data()
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
    data = get_data()
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


# ─── 对齐 API ──────────────────────────────────────────────────


class AlignmentCreate(BaseModel):
    source_a: str
    src_ref_a: str
    source_b: str
    src_ref_b: str
    note: str = ""


@app.get("/api/alignments")
def list_alignments():
    """列出所有已保存的对齐记录。"""
    alignments = get_alignments()
    data = get_data()

    enriched = []
    for i, al in enumerate(alignments):
        char_a = None
        char_b = None
        if al["source_a"] in data:
            for c in data[al["source_a"]]:
                if c["src_ref"] == al["src_ref_a"]:
                    char_a = c
                    break
        if al["source_b"] in data:
            for c in data[al["source_b"]]:
                if c["src_ref"] == al["src_ref_b"]:
                    char_b = c
                    break
        enriched.append(
            {
                "id": i,
                "source_a": al["source_a"],
                "src_ref_a": al["src_ref_a"],
                "char_a": char_a,
                "source_b": al["source_b"],
                "src_ref_b": al["src_ref_b"],
                "char_b": char_b,
                "note": al.get("note", ""),
            }
        )
    return enriched


@app.post("/api/alignments")
def create_alignment(al: AlignmentCreate):
    """创建一条对齐记录。"""
    if al.source_a == al.source_b and al.src_ref_a == al.src_ref_b:
        raise HTTPException(status_code=400, detail="Cannot align a character with itself")

    alignments = get_alignments()

    for existing in alignments:
        if (
            existing["source_a"] == al.source_a
            and existing["src_ref_a"] == al.src_ref_a
            and existing["source_b"] == al.source_b
            and existing["src_ref_b"] == al.src_ref_b
        ):
            raise HTTPException(status_code=409, detail="Alignment already exists")
        if (
            existing["source_a"] == al.source_b
            and existing["src_ref_a"] == al.src_ref_b
            and existing["source_b"] == al.source_a
            and existing["src_ref_b"] == al.src_ref_a
        ):
            raise HTTPException(status_code=409, detail="Reverse alignment already exists")

    new_al = {
        "source_a": al.source_a,
        "src_ref_a": al.src_ref_a,
        "source_b": al.source_b,
        "src_ref_b": al.src_ref_b,
        "note": al.note,
    }
    alignments.append(new_al)
    save_alignments(alignments)
    ALIGNMENTS_CACHE.clear()
    return {"status": "ok", "alignment": new_al}


@app.delete("/api/alignments/{alignment_id}")
def delete_alignment(alignment_id: int):
    """删除一条对齐记录。"""
    alignments = get_alignments()
    if alignment_id < 0 or alignment_id >= len(alignments):
        raise HTTPException(status_code=404, detail="Alignment not found")
    removed = alignments.pop(alignment_id)
    save_alignments(alignments)
    ALIGNMENTS_CACHE.clear()
    return {"status": "ok", "removed": removed}


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
    from radical_similarity import load_radical_order

    radicals = load_radical_order()
    return {"total": len(radicals), "radicals": radicals}


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
      - combined: 综合三者 (发音 35% + 语义 30% + 部首 35%)
    """
    data = get_data()
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
        # combined: 三路综合
        suggestions = _combined_three_way(target_char, candidates, source, top_k)

    return {
        "target": {**target_char, "source": source},
        "method": method,
        "suggestions": suggestions,
    }


def _combined_three_way(target_char: dict, candidates: list[dict], source: str, top_k: int) -> list[dict]:
    """
    三路综合相似度：发音 35% + 语义 30% + 部首 35%
    """
    results = []
    for cand in candidates:
        cand_pron = cand.get("pronunciation", "")
        cand_mean = cand.get("meaning", "")

        # 发音相似度
        dist_info = syllable_distance(target_char["pronunciation"], cand_pron)
        pron_sim = 1.0 - dist_info["combined_distance"]

        # 语义相似度
        mean_info = meaning_similarity(target_char["meaning"], cand_mean)
        mean_sim = mean_info["combined_score"]

        # 部首笔画相似度
        target_rs = get_char_rs(source, target_char["glyph"])
        cand_rs = get_char_rs(cand.get("source", ""), cand.get("glyph", ""))
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

        combined = 0.35 * pron_sim + 0.30 * mean_sim + 0.35 * rs_sim

        results.append(
            {
                **cand,
                "combined_score": round(combined, 4),
                "pron_similarity": round(pron_sim, 4),
                "mean_similarity": round(mean_sim, 4),
                "rs_similarity": round(rs_sim, 4),
                "pron_distance_detail": dist_info,
                "mean_similarity_detail": mean_info,
                "rs_similarity_detail": rs_info,
            }
        )

    results.sort(key=lambda x: x["combined_score"], reverse=True)
    return results[:top_k]


@app.get("/api/compare/{source_a}/{src_ref_a}/{source_b}/{src_ref_b}")
def compare_two(source_a: str, src_ref_a: str, source_b: str, src_ref_b: str):
    """全面比较两个字符：发音 + 语义 + 部首笔画。"""
    data = get_data()
    if source_a not in data or source_b not in data:
        raise HTTPException(status_code=404, detail="Source not found")

    char_a = None
    char_b = None
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

    # 发音距离
    pron_dist = syllable_distance(char_a["pronunciation"], char_b["pronunciation"])
    # 语义相似度
    mean_sim = meaning_similarity(char_a["meaning"], char_b["meaning"])
    # 部首笔画相似度
    rs_a = get_char_rs(source_a, char_a["glyph"])
    rs_b = get_char_rs(source_b, char_b["glyph"])
    if rs_a and rs_b:
        rs_info = radical_stroke_similarity(
            rs_a.get("radical"),
            rs_a.get("other_stroke"),
            rs_b.get("radical"),
            rs_b.get("other_stroke"),
        )
    else:
        rs_info = {"radical_similarity": 0.0, "stroke_similarity": 0.5, "combined_score": 0.15}

    # 综合
    pron_sim = 1.0 - pron_dist["combined_distance"]
    combined = round(0.35 * pron_sim + 0.30 * mean_sim["combined_score"] + 0.35 * rs_info["combined_score"], 4)

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
    for yaml_file in sorted(MAP_DIR.glob("*.yaml")):
        data_map = load_yaml(yaml_file.stem)
        mappings.append(
            {
                "file": yaml_file.name,
                "stem": yaml_file.stem,
                "pair_count": len(data_map),
            }
        )
    return mappings


@app.get("/api/mappings/{name}")
def get_mapping(name: str):
    """获取指定映射文件的完整内容。"""
    data_map = load_yaml(name)
    return {"name": name, "mappings": data_map, "count": len(data_map)}


@app.post("/api/mappings/{name}")
def add_mapping(name: str, glyph_a: str = Query(...), glyph_b: str = Query(...)):
    """向 YAML 映射文件中添加一对映射。"""
    filepath = MAP_DIR / f"{name}.yaml"
    if not filepath.exists():
        filepath = RS_DIR / f"{name}.yaml"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Mapping file '{name}' not found")

    existing = load_yaml(name)
    existing[glyph_a] = glyph_b
    with filepath.open("w", encoding="utf-8") as f:
        yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)
    return {"status": "ok", "glyph_a": glyph_a, "glyph_b": glyph_b}


# ─── 字形集群分析 ─────────────────────────────────────────────


@app.get("/api/clusters/{glyph}")
def get_glyph_cluster(glyph: str):
    """获取某个字形在所有来源中的出现情况及已有关联。"""
    data = get_data()
    alignments = get_alignments()

    occurrences = []
    for src_name, chars in data.items():
        for char in chars:
            if char["glyph"] == glyph:
                occurrences.append({**char, "source": src_name})

    linked = []
    for al in alignments:
        for occ in occurrences:
            if al["source_a"] == occ["source"] and al["src_ref_a"] == occ["src_ref"]:
                if al["source_b"] in data:
                    for c in data[al["source_b"]]:
                        if c["src_ref"] == al["src_ref_b"]:
                            linked.append({**c, "source": al["source_b"], "via": al["source_a"]})
            elif al["source_b"] == occ["source"] and al["src_ref_b"] == occ["src_ref"]:
                if al["source_a"] in data:
                    for c in data[al["source_a"]]:
                        if c["src_ref"] == al["src_ref_a"]:
                            linked.append({**c, "source": al["source_a"], "via": al["source_b"]})

    return {"glyph": glyph, "occurrences": occurrences, "linked_characters": linked}


# ─── 统计 API ─────────────────────────────────────────────────


@app.get("/api/stats")
def get_stats():
    """获取总体统计信息。"""
    data = get_data()
    alignments = get_alignments()
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


# ─── 启动 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)

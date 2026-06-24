"""
数据加载服务
=============
封装 TSV / YAML / RS 文件的加载和缓存逻辑。
"""

import json
from pathlib import Path

import yaml


class DataLoader:
    """统一的数据加载器，管理所有数据文件的读取和缓存。"""

    # ── 路径配置 ──────────────────────────────────────────────
    BASE_DIR: Path
    BOOK_DIR: Path
    MAP_DIR: Path
    RS_DIR: Path
    ALIGNMENTS_FILE: Path
    CURRENT_GROUP_FILE: Path

    # ── 来源元信息 ────────────────────────────────────────────
    SOURCE_META: dict[str, dict] = {
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

    # ── 缓存 ──────────────────────────────────────────────────
    _data_cache: dict[str, list[dict]] = {}
    _rs_cache: dict[str, dict[str, dict]] = {}
    _alignments_cache: list[dict] = []

    def __init__(self, base_dir: Path | str | None = None):
        if base_dir is None:
            base_dir = Path(__file__).parent.parent.parent.parent
        self.BASE_DIR = Path(base_dir)
        self.BOOK_DIR = self.BASE_DIR / "book"
        self.MAP_DIR = self.BASE_DIR / "map"
        self.RS_DIR = self.BASE_DIR / "rs"
        self.ALIGNMENTS_FILE = self.BASE_DIR / "alignments.jsonl"
        self.CURRENT_GROUP_FILE = self.BASE_DIR / "current_group.jsonl"

    # ── 公开方法 ──────────────────────────────────────────────

    def get_data(self) -> dict[str, list[dict]]:
        """获取所有书籍数据（带缓存）。"""
        if not self._data_cache:
            self._data_cache = self._load_all_data()
        return self._data_cache

    def get_alignments(self) -> list[dict]:
        """获取所有对齐组（带缓存）。"""
        if not self._alignments_cache:
            self._alignments_cache = self._load_alignments()
        return self._alignments_cache

    def save_alignments(self, data: list[dict]):
        """将对齐组数据写入磁盘并清除缓存。"""
        with self.ALIGNMENTS_FILE.open("w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        self._alignments_cache = data

    def clear_cache(self):
        """清除所有数据缓存。"""
        self._data_cache.clear()
        self._rs_cache.clear()
        self._alignments_cache.clear()

    def load_tsv(self, filename: str) -> list[dict]:
        """加载 book/ TSV 文件为字典列表，并尝试附加 RS 信息。"""
        filepath = self.BOOK_DIR / f"{filename}.tsv"
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
            if len(parts) >= 2:
                data.append(
                    {
                        "glyph": parts[0],
                        "src_ref": parts[1],
                        "pronunciation": parts[2] if len(parts) > 2 else "",
                        "meaning": parts[3] if len(parts) > 3 else "",
                    }
                )
        rs_data = self._load_rs_file(filename)
        for char in data:
            rs = rs_data.get(char["glyph"])
            if rs:
                char["radical"] = rs["radical"]
                char["other_stroke"] = rs["other_stroke"]
        return data

    def load_yaml(self, filename: str) -> dict:
        """加载 YAML 文件（优先 map/，后备 rs/）。"""
        filepath = self.MAP_DIR / f"{filename}.yaml"
        if not filepath.exists():
            filepath = self.RS_DIR / f"{filename}.yaml"
        if not filepath.exists():
            return {}
        with filepath.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def load_rs_data(self, source: str) -> dict[str, dict]:
        """加载指定来源的部首-笔画数据。"""
        filepath = self.RS_DIR / f"{source}.tsv"
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

    def get_char_rs(self, source: str, glyph: str) -> dict | None:
        """获取某个字符（按 glyph）的部首-笔画信息，跨来源查找。"""
        if source not in self._rs_cache:
            self._rs_cache[source] = self.load_rs_data(source)
        cache = self._rs_cache[source]
        if glyph in cache:
            return cache[glyph]
        for src_key in self._rs_cache:
            if src_key == source:
                continue
            if glyph in self._rs_cache[src_key]:
                return self._rs_cache[src_key][glyph]
        return None

    def load_radical_order(self) -> list[str]:
        """从 rs_order.yaml 加载部首排列顺序。"""
        filepath = self.RS_DIR / "rs_order.yaml"
        if not filepath.exists():
            return []
        with filepath.open(encoding="utf-8") as f:
            order_dict = yaml.safe_load(f) or {}
        return list(order_dict.keys())

    def get_radical_index(self) -> dict[str, int]:
        """获取部首 → 索引序号的映射。"""
        radicals = self.load_radical_order()
        return {r: i for i, r in enumerate(radicals)}

    # ── 从 src_ref 提取 source ────────────────────────────────

    @staticmethod
    def source_from_ref(src_ref: str) -> str:
        """从 src_ref 提取 source 名称，如 'D0-00101' → 'd0'。"""
        return src_ref.split("-")[0].lower() if "-" in src_ref else ""

    # ── 私有方法 ──────────────────────────────────────────────

    def _load_rs_file(self, source: str) -> dict[str, dict]:
        """加载 rs/{source}.tsv。"""
        filepath = self.RS_DIR / f"{source}.tsv"
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

    def _load_all_data(self) -> dict[str, list[dict]]:
        """加载所有书籍数据到内存缓存。"""
        data = {}
        for tsv_file in sorted(self.BOOK_DIR.glob("*.tsv")):
            source_name = tsv_file.stem
            data[source_name] = self.load_tsv(source_name)
        return data

    def _load_alignments(self) -> list[dict]:
        """从 alignments.jsonl 加载对齐组，并自动迁移旧格式。"""
        if not self.ALIGNMENTS_FILE.exists():
            return []
        with self.ALIGNMENTS_FILE.open(encoding="utf-8") as f:
            raw = [json.loads(line) for line in f if line.strip()]
        if raw and isinstance(raw[0], dict) and "source_a" in raw[0]:
            migrated = self._migrate_old_alignments(raw)
            self.save_alignments(migrated)
            return migrated
        return raw

    @staticmethod
    def _migrate_old_alignments(old_data: list[dict]) -> list[dict]:
        """将旧版 1:1 对齐迁移为分组格式。"""
        groups = []
        next_id = 0
        for al in old_data:
            if "source_a" in al and "source_b" in al:
                groups.append(
                    {
                        "id": next_id,
                        "entries": [
                            {"source": al["source_a"], "src_ref": al["src_ref_a"]},
                            {"source": al["source_b"], "src_ref": al["src_ref_b"]},
                        ],
                        "note": al.get("note", ""),
                    }
                )
                next_id += 1
            elif "entries" in al:
                gid = al.get("id", next_id)
                groups.append(al)
                next_id = max(next_id, gid + 1)
        return groups

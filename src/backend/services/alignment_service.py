"""
对齐组管理服务
===============
管理对齐组的 CRUD、合并、排序等操作。
"""

from models import AlignmentGroupCreate
from services.data_service import DataLoader


class AlignmentManager:
    """对齐组管理器，封装所有对齐相关的业务逻辑。"""

    def __init__(self, loader: DataLoader):
        self.loader = loader

    # ── 列表 ──────────────────────────────────────────────────

    def list_alignments(self) -> list[dict]:
        """列出所有对齐组（带排序和 enrich）。"""
        groups = self.loader.get_alignments()
        data = self.loader.get_data()
        enriched = []
        for grp in groups:
            entries_enriched = []
            for ref in grp.get("entries", []):
                src = self.loader.source_from_ref(ref)
                char = None
                if src in data:
                    for c in data[src]:
                        if c["src_ref"] == ref:
                            char = c
                            break
                entries_enriched.append({"source": src, "src_ref": ref, "char": char})
            enriched.append(
                {
                    "id": grp.get("id", 0),
                    "entries": entries_enriched,
                    "note": grp.get("note", ""),
                }
            )
        enriched.sort(key=self._group_sort_key)
        return enriched

    # ── 创建 / 合并 ───────────────────────────────────────────

    def create_or_merge(self, al: AlignmentGroupCreate) -> dict:
        """
        创建/扩展一个对齐组：
        - 所有条目都未加入任何组 → 创建新组
        - 已有条目属于某组 → 合并入该组
        - 条目来自多个已有组 → 合并这些组
        """
        if len(al.entries) < 2:
            raise ValueError("At least 2 entries required")

        groups = self.loader.get_alignments()
        data = self.loader.get_data()

        # 验证
        seen = set()
        for ref in al.entries:
            src = self.loader.source_from_ref(ref)
            if not src or src not in data:
                raise ValueError(f"Source not found for '{ref}'")
            if not any(c["src_ref"] == ref for c in data[src]):
                raise ValueError(f"Char '{ref}' not found in '{src}'")
            if ref in seen:
                raise ValueError(f"Duplicate entry '{ref}'")
            seen.add(ref)

        new_entries = list(al.entries)

        # 查找已有组
        touched_ids = set()
        for ref in al.entries:
            src = self.loader.source_from_ref(ref)
            for grp in groups:
                if any(e == ref for e in grp.get("entries", [])):
                    touched_ids.add(grp["id"])

        if not touched_ids:
            new_id = max((g["id"] for g in groups), default=-1) + 1
            groups.append({"id": new_id, "entries": new_entries, "note": al.note})
            self.loader.save_alignments(groups)
            return {"status": "ok", "group_id": new_id, "action": "created"}

        elif len(touched_ids) == 1:
            gid = next(iter(touched_ids))
            for grp in groups:
                if grp["id"] == gid:
                    existing = set(grp["entries"])
                    for ref in new_entries:
                        if ref not in existing:
                            grp["entries"].append(ref)
                    if al.note:
                        grp["note"] = al.note
                    break
            self.loader.save_alignments(groups)
            return {"status": "ok", "group_id": gid, "action": "merged"}

        else:
            target_id = min(touched_ids)
            target_group = next(g for g in groups if g["id"] == target_id)
            merged = set(target_group["entries"])
            for gid in touched_ids:
                if gid == target_id:
                    continue
                src = next(g for g in groups if g["id"] == gid)
                for ref in src.get("entries", []):
                    if ref not in merged:
                        target_group["entries"].append(ref)
                        merged.add(ref)
                groups.remove(src)
            for ref in new_entries:
                if ref not in merged:
                    target_group["entries"].append(ref)
                    merged.add(ref)
            if al.note:
                target_group["note"] = al.note
            self.loader.save_alignments(groups)
            return {"status": "ok", "group_id": target_id, "action": "merged_groups"}

    # ── 删除 ──────────────────────────────────────────────────

    def delete_group(self, group_id: int) -> dict:
        """删除整个对齐组。"""
        groups = self.loader.get_alignments()
        for i, grp in enumerate(groups):
            if grp.get("id") == group_id:
                removed = groups.pop(i)
                self.loader.save_alignments(groups)
                return {"status": "ok", "removed": removed}
        raise ValueError(f"Group {group_id} not found")

    def remove_entry(self, group_id: int, entry_index: int) -> dict:
        """从对齐组中移除一个条目。"""
        groups = self.loader.get_alignments()
        for grp in groups:
            if grp.get("id") == group_id:
                entries = grp.get("entries", [])
                if entry_index < 0 or entry_index >= len(entries):
                    raise ValueError("Entry index out of range")
                removed = entries.pop(entry_index)
                if len(entries) < 2:
                    groups.remove(grp)
                self.loader.save_alignments(groups)
                return {"status": "ok", "removed": removed}
        raise ValueError(f"Group {group_id} not found")

    # ── 当前工作区 ────────────────────────────────────────────

    def get_current_group(self) -> dict:
        """获取当前正在编辑的对齐组。"""
        f = self.loader.CURRENT_GROUP_FILE
        if f.exists():
            with f.open(encoding="utf-8") as fh:
                line = fh.readline().strip()
                if line:
                    import json

                    return json.loads(line)
        return {"entries": [], "note": ""}

    def save_current_group(self, body: AlignmentGroupCreate):
        """实时保存当前正在编辑的对齐组。"""
        import json

        entries = list(body.entries)
        with self.loader.CURRENT_GROUP_FILE.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"entries": entries, "note": body.note}, ensure_ascii=False) + "\n")
        return {"status": "ok"}

    def clear_current_group(self):
        """清空当前工作区。"""
        f = self.loader.CURRENT_GROUP_FILE
        if f.exists():
            f.unlink()
        return {"status": "ok"}

    # ── 私有辅助 ──────────────────────────────────────────────

    def _group_sort_key(self, grp: dict) -> tuple:
        """排序键：(min_radical_order, min_stroke, id)。"""
        from radical_similarity import get_char_rs, radical_order_index

        min_rad = 99999
        min_stroke = 99999
        for e in grp.get("entries", []):
            char = e.get("char")
            if not char:
                continue
            rs = get_char_rs(e["source"], char.get("glyph", ""))
            if rs:
                ridx = radical_order_index(rs.get("radical"))
                if ridx >= 0:
                    min_rad = min(min_rad, ridx)
                    min_stroke = min(min_stroke, rs.get("other_stroke", 0) or 0)
                else:
                    min_rad = min(min_rad, 99998)
        return (min_rad, min_stroke, grp.get("id", 0))

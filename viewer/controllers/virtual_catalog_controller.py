import os
from typing import Dict, Iterable, List, Set

from viewer.services.catalog_db import (
    create_category,
    delete_category,
    get_asset_categories_map,
    get_categories_tree,
    rename_category,
    set_asset_category,
)


class VirtualCatalogController:
    def __init__(self):
        self.selected_category_id = 0
        self.filter_enabled = False
        self.only_uncategorized = False
        self.categories = []
        self.children_by_parent = {}
        self.asset_categories_map: Dict[str, Set[int]] = {}

    @staticmethod
    def _norm_path(path: str) -> str:
        return os.path.normcase(os.path.normpath(os.path.abspath(path)))

    def load_view_state(self, selected_category_id: int, filter_enabled: bool, only_uncategorized: bool):
        self.selected_category_id = int(selected_category_id or 0)
        self.filter_enabled = bool(filter_enabled)
        self.only_uncategorized = bool(only_uncategorized)

    def set_selected_category(self, category_id: int):
        self.selected_category_id = int(category_id or 0)

    def set_filter_enabled(self, enabled: bool):
        self.filter_enabled = bool(enabled)

    def set_only_uncategorized(self, enabled: bool):
        self.only_uncategorized = bool(enabled)

    def refresh_categories(self, db_path: str):
        rows = get_categories_tree(db_path=db_path)
        self.categories = list(rows or [])
        children = {}
        valid_ids = set()
        for row in self.categories:
            cid = int(row.get("id") or 0)
            if cid <= 0:
                continue
            valid_ids.add(cid)
            parent = row.get("parent_id")
            parent_id = int(parent) if parent is not None else 0
            children.setdefault(parent_id, []).append(cid)
        self.children_by_parent = children
        if self.selected_category_id not in valid_ids:
            self.selected_category_id = 0

    def refresh_asset_map(self, model_files: Iterable[str], db_path: str):
        self.asset_categories_map = get_asset_categories_map(model_files, db_path=db_path)

    def clear_asset_map(self):
        self.asset_categories_map = {}

    def descendants(self, category_id: int):
        cid = int(category_id or 0)
        if cid <= 0:
            return set()
        out = set()
        stack = [cid]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.add(cur)
            stack.extend(self.children_by_parent.get(cur, []))
        return out

    def apply_filters(self, file_paths: List[str]) -> List[str]:
        filtered = list(file_paths or [])

        if self.only_uncategorized:
            kept = []
            for file_path in filtered:
                cats = self.asset_categories_map.get(self._norm_path(file_path)) or set()
                if not cats:
                    kept.append(file_path)
            filtered = kept

        if self.filter_enabled and self.selected_category_id > 0:
            allowed = self.descendants(self.selected_category_id)
            kept = []
            for file_path in filtered:
                cats = self.asset_categories_map.get(self._norm_path(file_path)) or set()
                if any(int(cat) in allowed for cat in cats):
                    kept.append(file_path)
            filtered = kept
        return filtered

    def category_count_for_path(self, file_path: str) -> int:
        if not file_path:
            return 0
        return len(self.asset_categories_map.get(self._norm_path(file_path)) or set())

    def create_category(self, parent_id: int, name: str, db_path: str):
        return create_category(
            name=name,
            parent_id=(int(parent_id) if int(parent_id or 0) > 0 else None),
            db_path=db_path,
        )

    def rename_category(self, category_id: int, name: str, db_path: str):
        rename_category(int(category_id), new_name=name, db_path=db_path)

    def delete_category(self, category_id: int, db_path: str):
        delete_category(int(category_id), db_path=db_path)
        if int(category_id or 0) == self.selected_category_id:
            self.selected_category_id = 0

    def assign_path(self, file_path: str, category_id: int, db_path: str):
        cid = int(category_id or 0)
        if not file_path or cid <= 0:
            return False
        set_asset_category(file_path, cid, db_path=db_path)
        norm = self._norm_path(file_path)
        bucket = self.asset_categories_map.setdefault(norm, set())
        bucket.add(cid)
        return True

    def assign_paths(self, file_paths: Iterable[str], category_id: int, db_path: str) -> int:
        cid = int(category_id or 0)
        if cid <= 0:
            return 0
        assigned = 0
        for file_path in file_paths or []:
            if self.assign_path(file_path, cid, db_path=db_path):
                assigned += 1
        return assigned

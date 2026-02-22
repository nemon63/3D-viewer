import os
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from viewer.services.catalog_db import get_favorite_paths, set_asset_favorite


class CatalogController:
    def top_category(self, file_path: str, root_directory: str) -> str:
        if not root_directory:
            return "Без категории"
        try:
            rel = os.path.relpath(file_path, root_directory)
        except Exception:
            return "Без категории"
        rel = rel.replace("\\", "/")
        if "/" in rel:
            return rel.split("/", 1)[0]
        return "Корень"

    def categories_for_models(self, model_files: Sequence[str], root_directory: str) -> List[str]:
        categories = [self.top_category(path, root_directory) for path in model_files]
        return sorted(set(categories), key=lambda x: x.lower())

    def filter_models(
        self,
        model_files: Sequence[str],
        root_directory: str,
        search_text: str,
        selected_category: str,
        only_favorites: bool,
        favorite_paths: Set[str],
    ) -> List[str]:
        needle = (search_text or "").strip().lower()
        filtered: List[str] = []
        for file_path in model_files:
            rel = os.path.relpath(file_path, root_directory).lower() if root_directory else file_path.lower()
            norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
            category = self.top_category(file_path, root_directory)
            if needle and needle not in rel:
                continue
            if selected_category and selected_category != "all" and category != selected_category:
                continue
            if only_favorites and norm not in favorite_paths:
                continue
            filtered.append(file_path)
        return filtered

    def load_favorites(self, root_directory: str, db_path: str) -> Set[str]:
        return set(get_favorite_paths(root=root_directory, db_path=db_path))

    def toggle_favorite(self, file_path: str, favorite_paths: Set[str], db_path: str) -> bool:
        norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
        is_favorite = norm in favorite_paths
        set_asset_favorite(file_path, not is_favorite, db_path=db_path)
        if is_favorite:
            favorite_paths.discard(norm)
            return False
        favorite_paths.add(norm)
        return True

    def set_favorite(self, file_path: str, is_favorite: bool, favorite_paths: Set[str], db_path: str) -> bool:
        norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
        desired = bool(is_favorite)
        set_asset_favorite(file_path, desired, db_path=db_path)
        if desired:
            favorite_paths.add(norm)
        else:
            favorite_paths.discard(norm)
        return desired

    def build_dock_items(
        self,
        filtered_model_files: Sequence[str],
        root_directory: str,
        favorite_paths: Set[str],
        preview_map_raw: Dict[str, str],
        preview_root: str,
        asset_categories_map: Optional[Dict[str, Set[int]]] = None,
    ) -> Tuple[List[Tuple[str, str, bool, int]], Dict[str, str]]:
        items: List[Tuple[str, str, bool, int]] = []
        preview_map: Dict[str, str] = {}
        for file_path in filtered_model_files:
            norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
            rel_display = os.path.relpath(file_path, root_directory) if root_directory else file_path
            is_favorite = norm in favorite_paths
            category_count = len(asset_categories_map.get(norm, set())) if asset_categories_map else 0
            items.append((file_path, rel_display, is_favorite, int(category_count)))
            preview_path = preview_map_raw.get(norm)
            if preview_path and os.path.isfile(preview_path):
                pnorm = os.path.normcase(os.path.normpath(os.path.abspath(preview_path)))
                if pnorm.startswith(preview_root + os.sep):
                    preview_map[file_path] = preview_path
        return items, preview_map

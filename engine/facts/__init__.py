"""人物事实档案支持。"""

from .people_archive import (
    ensure_people_archives_migrated,
    get_person_archive_path,
    append_note,
    append_date_entry,
    rename_person_archive,
)

__all__ = [
    "ensure_people_archives_migrated",
    "get_person_archive_path",
    "append_note",
    "append_date_entry",
    "rename_person_archive",
]

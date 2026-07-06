"""联系人身份目录。"""
from .directory import (
    IdentityAccount,
    IdentityPerson,
    ResolveResult,
    add_alias,
    audit_identity,
    bootstrap_identity,
    get_person,
    link_account,
    merge_people,
    remove_alias,
    resolve_contact,
    search_people,
    set_display_name,
)

__all__ = [
    "IdentityAccount",
    "IdentityPerson",
    "ResolveResult",
    "add_alias",
    "audit_identity",
    "bootstrap_identity",
    "get_person",
    "link_account",
    "merge_people",
    "remove_alias",
    "resolve_contact",
    "search_people",
    "set_display_name",
]

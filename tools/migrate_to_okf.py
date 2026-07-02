"""Migrate SalesCRM wiki to OKF (Open Knowledge Format) standard.

Changes:
1. Normalize frontmatter on all concept files
2. Rewrite root index.md as bundle entry (with frontmatter, type: Knowledge Bundle)
3. Generate entities/index.md and scenarios/index.md (no frontmatter)
4. Convert all internal links to bundle-relative absolute paths (/entities/xxx.md)
5. Rename .wiki-schema.md to _wiki-schema.md (non-concept, underscore prefix)
"""
import os
import re
import sys
from collections import defaultdict

BUNDLE_ROOT = os.path.join(os.path.dirname(__file__), "..", "docs", "sales", "wiki")

TYPE_MAP = {
    "Concept": "Concept",
    "Scenario": "Scenario",
    "entity": "Concept",
    "scenario": "Scenario",
}


def parse_frontmatter(content):
    """Parse YAML frontmatter, return (fm_dict, body, raw_fm_string)."""
    m = re.match(r"^(---\s*\n)(.*?\n)(---\s*\n)", content, re.DOTALL)
    if not m:
        return None, content, ""
    raw_fm = m.group(2)
    body = content[m.end():]
    fm = {}
    # Handle list values like tags: [a, b, c]
    list_pattern = re.compile(r"^(\w[\w_]*):\s*\[(.*)\]\s*$")
    for line in raw_fm.strip().split("\n"):
        lm = list_pattern.match(line.strip())
        if lm:
            fm[lm.group(1)] = [x.strip() for x in lm.group(2).split(",") if x.strip()]
            continue
        km = re.match(r"^(\w[\w_]*):\s*(.*)", line)
        if km:
            fm[km.group(1)] = km.group(2).strip()
    return fm, body, raw_fm


def build_frontmatter(fm):
    """Build normalized frontmatter string."""
    lines = ["---"]

    # type (required)
    old_type = fm.get("type", "Concept")
    new_type = TYPE_MAP.get(old_type, old_type)
    lines.append(f"type: {new_type}")

    # title
    if "title" in fm:
        lines.append(f"title: {fm['title']}")

    # description
    if "description" in fm:
        desc = fm["description"]
        lines.append(f"description: {desc}")

    # resource (optional)
    if "resource" in fm and fm["resource"]:
        lines.append(f"resource: {fm['resource']}")

    # tags (list)
    if "tags" in fm:
        tags = fm["tags"]
        if isinstance(tags, list):
            tag_str = ", ".join(tags)
        else:
            tag_str = str(tags)
        lines.append(f"tags: [{tag_str}]")

    # timestamp
    if "timestamp" in fm:
        lines.append(f"timestamp: {fm['timestamp']}")

    # Preserve all other extension fields
    skip_keys = {"type", "title", "description", "resource", "tags", "timestamp", "date", "category", "entity_type", "scenarios", "confidence", "search_terms"}
    for k, v in fm.items():
        if k not in skip_keys:
            lines.append(f"{k}: {v}")

    lines.append("---")
    return "\n".join(lines) + "\n"


def extract_description(body, fm):
    """Extract description from first blockquote or frontmatter."""
    if "description" in fm and fm["description"]:
        return fm["description"]
    desc_match = re.search(r"^>\s*(.+)", body, re.MULTILINE)
    if desc_match:
        desc = desc_match.group(1).strip()
        if len(desc) > 200:
            desc = desc[:197] + "..."
        return desc
    return ""


def get_all_concepts():
    """Get all concept files (non-index, non-reserved). Returns {concept_id: filepath}."""
    concepts = {}
    for dirpath, dirs, files in os.walk(BUNDLE_ROOT):
        for f in files:
            if not f.endswith(".md"):
                continue
            if f in ("index.md", "log.md"):
                continue
            if f.startswith(".") or f.startswith("_"):
                continue
            filepath = os.path.join(dirpath, f)
            rel = os.path.relpath(filepath, BUNDLE_ROOT).replace(os.sep, "/")
            concept_id = rel[:-3]  # remove .md
            concepts[concept_id] = filepath
    return concepts


def convert_links_in_body(body, concepts, current_file):
    """Convert all internal markdown links to bundle-relative absolute paths."""
    current_dir = os.path.dirname(current_file)

    def resolve_link(match):
        display = match.group(1)
        target = match.group(2)

        # Skip external links
        if target.startswith("http://") or target.startswith("https://") or target.startswith("mailto:"):
            return match.group(0)

        # Skip anchor-only links
        if target.startswith("#"):
            return match.group(0)

        # Already bundle-relative absolute
        if target.startswith("/"):
            return match.group(0)

        # Resolve relative path
        target_path = os.path.normpath(os.path.join(current_dir, target)).replace(os.sep, "/")
        bundle_rel = os.path.relpath(target_path, BUNDLE_ROOT).replace(os.sep, "/")

        # Check if it's a concept
        concept_id = bundle_rel[:-3] if bundle_rel.endswith(".md") else bundle_rel
        if concept_id in concepts:
            return f"[{display}](/{bundle_rel})"

        return match.group(0)

    # Match markdown links [text](url)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", resolve_link, body)


def process_concept_file(filepath, concepts):
    """Process a single concept file. Returns (changed, details)."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    fm, body, _ = parse_frontmatter(content)
    if fm is None:
        return False, "no frontmatter"

    # Extract description from body if missing
    if "description" not in fm or not fm["description"]:
        fm["description"] = extract_description(body, fm)

    # Normalize frontmatter
    new_fm = build_frontmatter(fm)

    # Convert links in body
    new_body = convert_links_in_body(body, concepts, filepath)

    # Also convert links in frontmatter (if any)
    new_fm = convert_links_in_body(new_fm, concepts, filepath)

    new_content = new_fm + new_body

    if new_content == content:
        return False, "no changes"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True, "converted"


def generate_subdir_index(subdir_name, concepts):
    """Generate index.md for a subdirectory (no frontmatter per OKF spec)."""
    subdir_path = os.path.join(BUNDLE_ROOT, subdir_name)
    entries = []

    for concept_id, filepath in sorted(concepts.items()):
        if not concept_id.startswith(f"{subdir_name}/"):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        fm, body, _ = parse_frontmatter(content)
        if fm is None:
            continue

        name = os.path.basename(filepath)
        title = fm.get("title", name[:-3])
        desc = fm.get("description", "")
        if desc and len(desc) > 100:
            desc = desc[:97] + "..."

        entries.append((name, title, desc))

    if not entries:
        return None

    section_titles = {
        "entities": "Entities",
        "scenarios": "Scenarios",
    }
    header = section_titles.get(subdir_name, subdir_name.capitalize())

    lines = [f"# {header}\n"]
    for name, title, desc in entries:
        if desc:
            lines.append(f"* [{title}]({name}) - {desc}")
        else:
            lines.append(f"* [{title}]({name})")

    return "\n".join(lines) + "\n"


def generate_root_index(concepts):
    """Generate root index.md as bundle entry (with frontmatter)."""
    categories = defaultdict(list)

    for concept_id, filepath in sorted(concepts.items()):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        fm, body, _ = parse_frontmatter(content)
        if fm is None:
            continue

        title = fm.get("title", os.path.basename(concept_id))
        concept_type = fm.get("type", "Concept")
        desc = fm.get("description", "")
        if desc and len(desc) > 120:
            desc = desc[:117] + "..."

        categories[concept_type].append((concept_id + ".md", title, desc))

    # Build frontmatter
    fm_lines = [
        "---",
        "type: Knowledge Bundle",
        "title: SalesCRM Wiki",
        "description: SalesCRM knowledge base — systematic knowledge for sales communication, customer relationships, and decision analysis.",
        "tags: [sales, wiki, knowledge-base]",
        "timestamp: 2026-07-01T00:00:00Z",
        "okf_version: \"0.1\"",
        "---",
        "",
    ]

    # Build body
    body_lines = []

    section_labels = {
        "Concept": "Entities",
        "Scenario": "Scenarios",
    }

    for type_key in ["Concept", "Scenario"]:
        items = categories.get(type_key, [])
        if not items:
            continue
        label = section_labels.get(type_key, type_key)
        body_lines.append(f"# {label}")
        body_lines.append("")
        for rel, title, desc in items:
            if desc:
                body_lines.append(f"* [{title}]({rel}) - {desc}")
            else:
                body_lines.append(f"* [{title}]({rel})")
        body_lines.append("")

    return "\n".join(fm_lines + body_lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    dry_run = "--dry-run" in sys.argv

    # Step 1: Collect all concepts
    concepts = get_all_concepts()
    print(f"Total concept files: {len(concepts)}")

    # Step 2: Process each concept file
    converted = 0
    skipped = 0
    errors = []

    for concept_id, filepath in sorted(concepts.items()):
        try:
            changed, detail = process_concept_file(filepath, concepts)
            if changed:
                converted += 1
                rel = os.path.relpath(filepath, BUNDLE_ROOT).replace(os.sep, "/")
                print(f"  [CONVERT] {rel}")
            else:
                skipped += 1
        except Exception as e:
            errors.append((concept_id, str(e)))
            print(f"  [ERROR] {concept_id}: {e}")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Concept files: {converted} changed, {skipped} skipped, {len(errors)} errors")

    if dry_run:
        print("\n[DRY RUN] Skipping index generation")
        return

    # Step 3: Generate subdirectory index files
    for subdir in ["entities", "scenarios"]:
        index_content = generate_subdir_index(subdir, concepts)
        if index_content:
            index_path = os.path.join(BUNDLE_ROOT, subdir, "index.md")
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(index_content)
            print(f"  [INDEX] {subdir}/index.md")

    # Step 4: Generate root index.md
    root_index = generate_root_index(concepts)
    root_path = os.path.join(BUNDLE_ROOT, "index.md")
    with open(root_path, "w", encoding="utf-8") as f:
        f.write(root_index)
    print(f"  [INDEX] index.md")

    # Step 5: Handle .wiki-schema.md (rename to _wiki-schema.md)
    schema_path = os.path.join(BUNDLE_ROOT, ".wiki-schema.md")
    if os.path.exists(schema_path):
        new_schema_path = os.path.join(BUNDLE_ROOT, "_wiki-schema.md")
        os.rename(schema_path, new_schema_path)
        print(f"  [RENAME] .wiki-schema.md -> _wiki-schema.md")

    if errors:
        print("\nErrors:")
        for cid, err in errors:
            print(f"  {cid}: {err}")

    print("\nMigration complete!")


if __name__ == "__main__":
    main()

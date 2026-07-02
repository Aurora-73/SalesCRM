#!/usr/bin/env bash
set -euo pipefail

# Migration helper script for SalesCRM setup.
#
# Usage from Git Bash:
#   cd /e/Code/SalesCRM
#   bash tools/copy_to_salescrm.sh
#   bash tools/copy_to_salescrm.sh --force
#   bash tools/copy_to_salescrm.sh /e/Code/SalesCRM --force
#
# What is copied:
#   1. Directly reusable with light config edits:
#      - engine/importers/      WCD/WeFlow sync, checkpoint, DB init, OCR import
#      - engine/identity/       Person/Account/Alias identity layer
#      - engine/knowledge/      Wiki search/index/retriever layer
#      - engine/models/         Dataclass/YAML model layer
#      - engine/agent/          Tool implementation layer
#      - engine/tools.py        Agent tool facade
#      - engine/config.py       Path/config management
#   2. Core logic:
#      - engine/analyzers/      metrics/ranker/events
#      - engine/facts/          customer archive
#      - engine/formulas.py     BQ/BSP/BWS/PV/BS sales formulas
#   3. Agent skills and docs:
#      - .claude/skills/        sales-crm skill
#      - readme/                project/module docs
#      - tests/                 fixtures/tests
#      - tools/                 document/wiki helper scripts
#
# What is intentionally NOT copied:
#   - data/                     private runtime database, facts, outputs, config tokens
#   - docs/                     private/large wiki data; create docs/wiki manually
#   - _reference/               upstream references
#   - .git/.history/.pytest_cache/__pycache__

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_TARGET="$(cd "$ROOT/.." && pwd)/SalesCRM"
TARGET="$DEFAULT_TARGET"
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --force|-f)
      FORCE=1
      ;;
    --help|-h)
      sed -n '1,80p' "$0"
      exit 0
      ;;
    *)
      TARGET="$arg"
      ;;
  esac
done

if [[ -e "$TARGET" && "$FORCE" -ne 1 ]]; then
  echo "Target already exists: $TARGET"
  echo "Re-run with --force to merge/overwrite copied files."
  exit 1
fi

mkdir -p "$TARGET"

copy_path() {
  local src="$1"
  local dest="${2:-$1}"
  local abs_src="$ROOT/$src"
  local abs_dest="$TARGET/$dest"

  if [[ ! -e "$abs_src" ]]; then
    echo "skip missing: $src"
    return 0
  fi

  mkdir -p "$(dirname "$abs_dest")"
  rm -rf "$abs_dest"
  cp -a "$abs_src" "$abs_dest"
  echo "copied: $src -> $dest"
}

write_file() {
  local rel="$1"
  mkdir -p "$(dirname "$TARGET/$rel")"
  cat > "$TARGET/$rel"
  echo "created: $rel"
}

echo "Source: $ROOT"
echo "Target: $TARGET"
echo

# Core engine.
copy_path "engine/importers"
copy_path "engine/identity"
copy_path "engine/knowledge"
copy_path "engine/models"
copy_path "engine/agent"
copy_path "engine/analyzers"
copy_path "engine/facts"
copy_path "engine/config.py"
copy_path "engine/formulas.py"
copy_path "engine/tools.py"
copy_path "engine/stickers.py"
copy_path "engine/__init__.py"

# Agent instructions and docs.
copy_path ".claude/skills"
copy_path ".agents"
copy_path "readme"
copy_path "CLAUDE.md"
copy_path "requirements.txt"
copy_path "pytest.ini"
copy_path ".gitignore"

# Developer helpers and tests. The tools directory includes this script too;
# that is acceptable and keeps the migration helper available in the fork.
copy_path "tools"
copy_path "tests"

# Create SalesCRM-specific empty runtime directories. Do not copy private data.
mkdir -p \
  "$TARGET/data/raw" \
  "$TARGET/data/customers" \
  "$TARGET/data/outputs/analysis" \
  "$TARGET/data/outputs/reports" \
  "$TARGET/data/outputs/rankings" \
  "$TARGET/data/input" \
  "$TARGET/docs/wiki/entities" \
  "$TARGET/docs/wiki/scenarios" \
  "$TARGET/plan"

write_file "data/README.md" <<'EOF'
# SalesCRM Runtime Data

This directory is intentionally initialized empty.

Do not copy private data here. Create a local config and sync/import
SalesCRM data from the target environment.
EOF

write_file "docs/wiki/README.md" <<'EOF'
# Sales Knowledge Base (OKF Format)

SalesCRM wiki pages in OKF (Open Knowledge Format) structure:

- entities/: Core concepts, frameworks, and techniques (SPIN, MEDDIC, objection handling, etc.)
- scenarios/: Situation-specific decision guides (price objection, no reply, competitor pressure, etc.)
- index.md: Knowledge bundle root index
EOF

write_file "MIGRATION_TODO.md" <<'EOF'
# SalesCRM Migration TODO

## Rename Domain Concepts

- person/contact -> customer/account/contact as appropriate
- facts/people -> customers
- relationship stage -> sales stage
- Sales formulas: BQ/BSP/BWS/PV/BS
- interaction patterns: buyer/evaluator/free_consulting/silent

## Retune Core Logic

- engine/analyzers/metrics.py: retune weights for buyer intent
- engine/analyzers/events.py: add demand confirmed, quote sent, decision maker appeared
- engine/analyzers/ranker.py: hot customers, silent customers, urgent customers
- engine/formulas.py: implement sales_* wrappers or replace formulas
- engine/agent/brief.py: rewrite labels and recommendations for sales
- engine/agent/write.py and engine/facts: customer archive wording/paths
- engine/tools.py: expose sales_params/sales_bq/sales_bsp/sales_bws/sales_pv/sales_action

## Core Components

- WCD/WeFlow sync pipeline and WCD snapshot refresh behavior
- structured data tools: chat_data, brief_data, message_context_data
- identity alias resolution
- wiki search/retriever pattern
- Markdown + YAML analysis persistence pattern
EOF

write_file "README.md" <<'EOF'
# SalesCRM

AI-driven local-first sales customer analysis assistant. Based on WeChat chat records,
automatically analyze customer intent, identify sales opportunities, and provide follow-up suggestions.

Start from `readme/PROJECT.md` and `readme/`.
EOF

echo
echo "Done."
echo "Next:"
echo "  cd \"$TARGET\""
echo "  git init"
echo "  review MIGRATION_TODO.md"

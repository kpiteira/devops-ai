#!/bin/bash
# install.sh — Symlink devops-ai skills, agents, and rules to AI tool directories
#
# Usage: ./install.sh [--force] [--target claude|codex|copilot|all] [--rules <project-path>]
#
# Creates directory symlinks from ~/.<tool>/skills/<name>/ → devops-ai/skills/<name>/
# and file symlinks from ~/.<tool>/agents/<name>.md → devops-ai/agents/<name>.md
# so that AI tools discover and invoke devops-ai skills and agents natively.
#
# Running 'git pull' in devops-ai updates all symlinked skills globally.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"
AGENTS_DIR="$SCRIPT_DIR/agents"
RULES_DIR="$SCRIPT_DIR/rules"
FORCE=false
TARGET="all"
RULES_PROJECT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force) FORCE=true; shift ;;
        --target) TARGET="$2"; shift 2 ;;
        --rules) RULES_PROJECT="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: ./install.sh [--force] [--target claude|codex|copilot|all] [--rules <project-path>]"
            echo ""
            echo "Options:"
            echo "  --force              Overwrite existing non-symlink files"
            echo "  --target <tool>      Install for specific tool only (default: all)"
            echo "  --rules <path>       Install rules into a project's .claude/rules/"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Validate target
case "$TARGET" in
    claude|codex|copilot|all) ;;
    *) echo "Error: Invalid target '$TARGET'. Allowed values: claude, codex, copilot, all."; exit 1 ;;
esac

# ---------------------------------------------------------------------------
# Skill reconciliation — detect drift before overwriting
# ---------------------------------------------------------------------------

check_skill_drift() {
    local target_dir="$1"
    local has_drift=false

    # Check 1: Uncommitted changes in devops-ai skills/ (symlinks point here)
    local dirty_skills
    dirty_skills=$(git -C "$SCRIPT_DIR" diff --name-only -- skills/ 2>/dev/null || true)
    if [ -n "$dirty_skills" ]; then
        echo "  WARNING: Uncommitted skill changes in devops-ai:"
        echo "$dirty_skills" | while read -r f; do
            echo "    modified: $f"
        done
        has_drift=true
    fi

    # Check 2: Non-symlink skills at target that differ from devops-ai source
    if [ -d "$target_dir" ]; then
        for local_skill in "$target_dir"/*/; do
            [ -d "$local_skill" ] || continue
            [ -L "${local_skill%/}" ] && continue  # skip symlinks — they're fine
            local name
            name=$(basename "${local_skill%/}")
            local source_skill="$SKILLS_DIR/$name/SKILL.md"
            local local_file="${local_skill}SKILL.md"
            if [ -f "$source_skill" ] && [ -f "$local_file" ]; then
                if ! diff -q "$source_skill" "$local_file" >/dev/null 2>&1; then
                    echo "  WARNING: Local skill '$name' differs from devops-ai source"
                    echo "    local:  $local_file"
                    echo "    source: $source_skill"
                    has_drift=true
                fi
            elif [ ! -f "$source_skill" ] && [ -f "$local_file" ]; then
                echo "  INFO: Local-only skill '$name' (not in devops-ai)"
            fi
        done
    fi

    if [ "$has_drift" = true ]; then
        echo ""
        echo "  Skill drift detected. To resolve:"
        echo "    1. Review changes:  git -C $SCRIPT_DIR diff skills/"
        echo "    2. Commit to keep:  git -C $SCRIPT_DIR add skills/ && git commit"
        echo "    3. Discard changes: git -C $SCRIPT_DIR checkout skills/"
        echo "    4. Force install:   ./install.sh --force"
        echo ""
        if [ "$FORCE" != true ]; then
            echo "  Aborting. Use --force to install anyway (uncommitted changes will persist)."
            return 1
        else
            echo "  --force specified, continuing despite drift."
        fi
    fi
    return 0
}

cleanup_stale_symlinks() {
    local target_dir="$1"
    [ -d "$target_dir" ] || return 0
    for link in "$target_dir"/*/; do
        [ -L "${link%/}" ] || continue
        if [ ! -e "${link%/}" ]; then
            echo "  CLEAN: $(basename "${link%/}") (stale symlink)"
            rm -f "${link%/}"
        fi
    done
}

install_skills() {
    local target_dir="$1"
    local tool_name="$2"
    local count=0

    mkdir -p "$target_dir"
    cleanup_stale_symlinks "$target_dir"

    for skill_dir in "$SKILLS_DIR"/*/; do
        [ -d "$skill_dir" ] || continue
        local name
        name=$(basename "$skill_dir")
        local target="$target_dir/$name"

        if [ -e "$target" ] && [ ! -L "$target" ]; then
            if [ "$FORCE" = true ]; then
                rm -rf "$target"
            else
                echo "  SKIP: $name (non-symlink exists, use --force to overwrite)"
                continue
            fi
        fi

        ln -sfn "$skill_dir" "$target"
        echo "  OK: $name"
        count=$((count + 1))
    done

    echo "  → $count skills installed for $tool_name"
}

install_rules() {
    local project_dir="$1"
    local rules_target="$project_dir/.claude/rules"
    [ -d "$RULES_DIR" ] || return 0
    mkdir -p "$rules_target"
    local count=0
    for rule in "$RULES_DIR"/*.md; do
        [ -f "$rule" ] || continue
        local name
        name=$(basename "$rule")
        ln -sfn "$rule" "$rules_target/$name"
        count=$((count + 1))
    done
    echo "  → $count rules installed to $rules_target"
}

install_agents() {
    local target_dir="$1"
    local tool_name="$2"
    [ -d "$AGENTS_DIR" ] || return 0
    mkdir -p "$target_dir"

    # Clean stale agent symlinks
    for link in "$target_dir"/*.md; do
        [ -L "$link" ] || continue
        if [ ! -e "$link" ]; then
            echo "  CLEAN: $(basename "$link") (stale symlink)"
            rm -f "$link"
        fi
    done

    local count=0
    for agent in "$AGENTS_DIR"/*.md; do
        [ -f "$agent" ] || continue
        local name
        name=$(basename "$agent")
        local target="$target_dir/$name"

        if [ -e "$target" ] && [ ! -L "$target" ]; then
            if [ "$FORCE" = true ]; then
                rm -f "$target"
            else
                echo "  SKIP: $name (non-symlink exists, use --force to overwrite)"
                continue
            fi
        fi

        ln -sfn "$agent" "$target"
        echo "  OK: $name"
        count=$((count + 1))
    done

    echo "  → $count agents installed for $tool_name"
}

# Handle --rules mode
if [ -n "$RULES_PROJECT" ]; then
    if [ ! -d "$RULES_PROJECT" ]; then
        echo "Error: Project path '$RULES_PROJECT' does not exist."
        exit 1
    fi
    echo "Installing rules to $RULES_PROJECT:"
    install_rules "$RULES_PROJECT"
    exit 0
fi

echo "devops-ai skill installer"
echo ""

# kinfra CLI (editable install via uv)
echo "kinfra CLI:"
if command -v uv &>/dev/null; then
    install_output=$(uv tool install -e "$SCRIPT_DIR" 2>&1)
    install_status=$?
    echo "$install_output" | while read -r line; do
        echo "  $line"
    done
    if [ $install_status -ne 0 ]; then
        echo "  ERROR: uv tool install failed (exit $install_status)"
    elif command -v kinfra &>/dev/null; then
        echo "  → kinfra CLI installed"
    else
        echo "  → installed, but 'kinfra' not on PATH — check 'uv tool dir' output"
    fi
else
    echo "  SKIP: uv not found — install uv (https://docs.astral.sh/uv/) for kinfra CLI"
fi
echo ""

# Skill drift check — source-level (git status) plus Claude target directory
# (Claude is the primary target where local-only skills are created)
echo "Skill reconciliation:"
if ! check_skill_drift "$HOME/.claude/skills"; then
    exit 1
fi
echo ""

# Claude Code
if [ "$TARGET" = "all" ] || [ "$TARGET" = "claude" ]; then
    echo "Claude Code (skills):"
    install_skills "$HOME/.claude/skills" "Claude Code"
    echo "Claude Code (agents):"
    install_agents "$HOME/.claude/agents" "Claude Code"
    echo ""
fi

# Codex CLI
if [ "$TARGET" = "all" ] || [ "$TARGET" = "codex" ]; then
    echo "Codex CLI:"
    install_skills "$HOME/.codex/skills" "Codex CLI"
    echo ""
fi

# Copilot CLI
if [ "$TARGET" = "all" ] || [ "$TARGET" = "copilot" ]; then
    echo "GitHub Copilot CLI:"
    install_skills "$HOME/.copilot/skills" "Copilot CLI"
    echo ""
fi

# Self-install rules for devops-ai
echo "Rules (devops-ai):"
install_rules "$SCRIPT_DIR"
echo ""

# Configure git hooks path for devops-ai itself
if [ -d "$SCRIPT_DIR/.githooks" ]; then
    echo "Git hooks:"
    git -C "$SCRIPT_DIR" config core.hooksPath .githooks 2>/dev/null && \
        echo "  → core.hooksPath set to .githooks" || \
        echo "  SKIP: not a git repository"
    echo ""
fi

echo "Done. Run 'git pull' in devops-ai to update all skills."

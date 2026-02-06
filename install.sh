#!/bin/bash
# install.sh — Symlink devops-ai skills to AI tool directories
#
# Usage: ./install.sh [--force] [--target claude|codex|copilot|all]
#
# Creates directory symlinks from ~/.<tool>/skills/<name>/ → devops-ai/skills/<name>/
# so that AI tools discover and invoke devops-ai skills natively.
#
# Running 'git pull' in devops-ai updates all symlinked skills globally.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"
FORCE=false
TARGET="all"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force) FORCE=true; shift ;;
        --target) TARGET="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: ./install.sh [--force] [--target claude|codex|copilot|all]"
            echo ""
            echo "Options:"
            echo "  --force           Overwrite existing non-symlink files"
            echo "  --target <tool>   Install for specific tool only (default: all)"
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

install_skills() {
    local target_dir="$1"
    local tool_name="$2"
    local count=0

    mkdir -p "$target_dir"

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

echo "devops-ai skill installer"
echo ""

# Claude Code
if [ "$TARGET" = "all" ] || [ "$TARGET" = "claude" ]; then
    echo "Claude Code:"
    install_skills "$HOME/.claude/skills" "Claude Code"
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

echo "Done. Run 'git pull' in devops-ai to update all skills."

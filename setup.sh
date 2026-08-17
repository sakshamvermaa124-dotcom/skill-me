#!/bin/sh
# ─── SkillMe Developer Setup ───
# Run this once after cloning to enable pre-commit hooks.
#   git clone <repo> && cd skill-me && sh setup.sh

echo "⚙️  Configuring git to use tracked hooks..."
git config core.hooksPath .githooks
echo "✓ Pre-commit hooks activated."
echo ""
echo "Done! JS syntax errors will now be caught before every commit."

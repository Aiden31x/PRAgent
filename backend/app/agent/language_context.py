"""Language-aware context injection for the PR review agent.

Detects the programming languages present in a PR's changed files by file
extension, then loads the corresponding review checklist(s) from the
review-knowledge/ directory and returns them as a single string ready to be
appended to the first user message.

Fallback behaviour: if no recognized extensions are found, or if a checklist
file is missing from disk, an empty string is returned so the agent falls back
to the core rubric without crashing.
"""

from __future__ import annotations

import pathlib

# Absolute path to the review-knowledge/ directory (two levels above this file:
# app/agent/ -> app/ -> backend/ -> review-knowledge/).
_KNOWLEDGE_DIR = pathlib.Path(__file__).parent.parent.parent / "review-knowledge"

# Maps file extension (lowercase, including the leading dot) to a checklist name.
# The checklist name corresponds to a <name>.md file inside _KNOWLEDGE_DIR.
#
# Option-2 narrow mapping:
#   .tsx / .jsx  -> react-ts  (full React + Next.js + TypeScript guide)
#   .ts  / .js   -> typescript (lightweight TS-only guide, no React hooks)
#   .py  / .pyi  -> python
#   .java        -> java
#
# Everything else has no entry and gets the empty-string fallback.
_EXTENSION_MAP: dict[str, str] = {
    ".tsx":  "react-ts",
    ".jsx":  "react-ts",
    ".ts":   "typescript",
    ".js":   "typescript",
    ".mts":  "typescript",
    ".mjs":  "typescript",
    ".py":   "python",
    ".pyi":  "python",
    ".java": "java",
}


def detect_languages(changed_files: list[str]) -> list[str]:
    """Return the ordered, deduplicated list of checklist names that apply to
    the given list of changed file paths.

    Rules:
    - Order is determined by first appearance in the file list.
    - If both ``react-ts`` and ``typescript`` are detected (a PR mixing
      .tsx and .ts files), ``typescript`` is dropped because ``react-ts``
      already covers TypeScript fundamentals.
    """
    seen: dict[str, bool] = {}
    for filepath in changed_files:
        ext = pathlib.Path(filepath).suffix.lower()
        lang = _EXTENSION_MAP.get(ext)
        if lang and lang not in seen:
            seen[lang] = True

    langs = list(seen)

    # react-ts already includes TypeScript type-safety content — no need to
    # inject the lighter typescript guide on top of it.
    if "react-ts" in langs and "typescript" in langs:
        langs.remove("typescript")

    return langs


def load_language_context(changed_files: list[str]) -> str:
    """Return a formatted string of all relevant language checklists for the
    given changed files, or an empty string if none apply.

    The returned string is safe to append directly to the first user message.
    Missing checklist files are silently skipped so a misconfigured install
    does not crash a live review.
    """
    langs = detect_languages(changed_files)
    if not langs:
        return ""

    sections: list[str] = []
    for lang in langs:
        path = _KNOWLEDGE_DIR / f"{lang}.md"
        if path.exists():
            sections.append(path.read_text(encoding="utf-8").strip())

    if not sections:
        return ""

    header = "=== LANGUAGE-SPECIFIC REVIEW CHECKLIST ===\n\n"
    body = "\n\n---\n\n".join(sections)
    return header + body

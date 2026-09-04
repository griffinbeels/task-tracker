"""Read-only access to the cross-project knowledge base, for the Learnings overlay.

`~/.claude/knowledge` is Claude's own cross-project memory of how to build
things well — see that repo's own CLAUDE.md. This module never writes to it;
ingest/query/lint are a Claude session's own workflow, not this app's.
"""

from pathlib import Path


def knowledge_root() -> Path:
    """Reached through the module at call time, not bound at import.

    Same reasoning as registry.CONFIG_DIR (invariant 7): a test that bound
    this into a module-level constant would capture the real home directory
    the moment the module is imported, rather than whatever a fixture
    monkeypatches this function to return.
    """
    return Path.home() / ".claude" / "knowledge"


def read_page(relative_path: str) -> str:
    """The text of one markdown file under the knowledge root.

    `relative_path` crosses the bridge from JS: either the fixed "index.md"
    the Learnings button opens with, or a relative link the frontend has
    already resolved against the page it was found in. Joining it onto the
    root and resolving the result is what store.resolve_attachment does to an
    attachment reference, for the same reason — an absolute path, or one
    laced with `..`, would otherwise walk out of this tree entirely (the
    whole home directory is one `../../../` away from a wiki page), and a
    join with an absolute right-hand side silently drops the root altogether,
    which is exactly why the check below compares where the candidate ended
    up rather than trusting how it was built.
    """
    root = knowledge_root().resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"outside the knowledge root: {relative_path}")
    if candidate.suffix.lower() != ".md":
        raise ValueError(f"not a markdown file: {relative_path}")
    if not candidate.is_file():
        raise ValueError(f"no such page: {relative_path}")
    return candidate.read_text(encoding="utf-8")

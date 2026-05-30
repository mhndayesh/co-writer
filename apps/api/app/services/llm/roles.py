"""Task → category classification for LLM routing.

Every `page` passed to `llm_service.run()` maps to a category so the user can
route "creative" work (prose writing, scene drafting, continuity comparison)
and "technical" work (structured extraction/filing) to different models.

Categories:
  creative  — generates or judges prose; benefits from a stronger writing model
  technical — produces structured JSON; can run on a cheaper/local model
  embedding — vector embeddings (no `page`; resolved separately, needs an
              embed-capable provider)
"""
from __future__ import annotations

# Per-page category. Unknown pages default to "technical" (the safe/cheap side).
PAGE_CATEGORY: dict[str, str] = {
    "flow.polish": "creative",      # rewrite raw draft into polished prose
    "flow.companion": "creative",   # Writing Companion drafts a scene
    "story_check": "creative",      # continuity comparison / judgement
    "flow.extract": "technical",    # structured extraction → JSON
    "llm.test": "technical",        # connection diagnostic
}

CREATIVE = "creative"
TECHNICAL = "technical"
EMBEDDING = "embedding"

# Tasks the Custom-mode UI exposes for per-task routing, in display order.
CUSTOM_TASKS: list[tuple[str, str]] = [
    ("flow.polish", "Flow Polish"),
    ("flow.companion", "Writing Companion"),
    ("story_check", "Story Check"),
    ("flow.extract", "Flow Extract"),
]


def category_for_page(page: str) -> str:
    return PAGE_CATEGORY.get(page, TECHNICAL)

"""Task → category classification for LLM routing.

Every `page` passed to `llm_service.run()` maps to a category so the user can
route "creative" work (prose writing, scene drafting, continuity comparison)
and "technical" work (structured extraction/filing) to different models.

Categories:
  creative  - generates or judges prose; benefits from a stronger writing model
  technical - produces structured JSON; can run on a cheaper/local model
  embedding - vector embeddings (no `page`; resolved separately, needs an
              embed-capable provider)
"""
from __future__ import annotations

# Per-page category. Unknown pages default to "technical" (the safe/cheap side).
PAGE_CATEGORY: dict[str, str] = {
    "flow.polish": "creative",      # rewrite raw draft into polished prose
    "flow.companion": "creative",   # Writing Companion drafts a scene
    "story_check": "creative",      # continuity comparison / judgement
    "flow.extract": "technical",    # structured extraction → JSON
    "flow.enhance": "technical",    # language enhancement → JSON suggestions
    "llm.test": "technical",        # connection diagnostic
    # Character Voice Studio (Narrative Fidelity Engine)
    "voice.analyze": "technical",   # extract identity traits → JSON proposals
    "voice.interview": "creative",  # synthesize readable + structured profile
    "voice.place": "creative",      # synthesize place identity from answers
    "voice.observe": "creative",    # line-level critique (judgement, like story_check)
    "voice.rewrite": "creative",    # Dialogue Writer rewrite/draft (prose)
    "voice.evolve": "technical",    # post-scene delta proposals → JSON
    "voice.compare": "creative",    # side-by-side voice comparison (prose)
}

CREATIVE = "creative"
TECHNICAL = "technical"
EMBEDDING = "embedding"
LANES_ORDER = (CREATIVE, TECHNICAL, EMBEDDING)


def category_for_page(page: str) -> str:
    return PAGE_CATEGORY.get(page, TECHNICAL)

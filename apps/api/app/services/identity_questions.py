"""Static, researched interview + place question banks for the Voice Studio.

Synthesized from two research passes (see repo-root deep-research-report.md and the
compass artifact). Design rules baked in, in priority order:

  1. Cover all FIVE identity layers — core, behavioral, voice, relationship masks,
     current state — not just the three JSON layers. Masks/state route to their own
     tables at synthesis time (a one-off scene state must never become core canon).
  2. Every default question must change likely prose (dialogue, action, or scene
     logic). Low-signal trivia (zodiac, favorite color) is deliberately excluded.
  3. Ask for the GAP, not the trait: want vs need, public persona vs private self,
     stated value vs enacted behavior. Contradiction = realism.
  4. Behavioral / scenario wording over labels ("what do they do when criticized?"
     beats "are they insecure?"). Express stress/deception as deviations.
  5. Tiered depth: Quick = side cast, Medium = recurring cast (default), Deep =
     protagonists / antagonists / POV-heavy characters.

Tier counts (cumulative by `tier_min`, excluding branch questions):
  Quick  = 10   (3 core, 2 behavioral, 2 voice, 2 relationship, 1 current)
  Medium = 20   (5 core, 4 behavioral, 4 voice, 4 relationship, 3 current)
  Deep   = 35   (8 core, 7 behavioral, 7 voice, 8 relationship, 5 current)

Pure data (no DB, no LLM) so it's trivially unit-testable and works under the test
suite's fallback provider. Branching is data-driven: a question may carry a
`branches` map keyed by the chosen option; the client walks it to reveal targeted
follow-ups (one per ambiguity — never sprawling).

Question shape:
  {
    "id": str,                # stable key, used as the answer key
    "layer": "core"|"behavioral"|"voice"|"relationship"|"current",
    "text": str,
    "tier_min": "quick"|"medium"|"deep",   # smallest tier that includes it
    "hint": str,              # optional helper / follow-up guidance shown under the field
    "options": [str, ...],    # optional — renders a select; free text otherwise
    "is_branch": bool,        # branch-only questions are hidden until triggered
    "branches": {option: [question_id, ...]},  # optional targeted follow-ups
  }
"""
from __future__ import annotations

LAYERS = ("core", "behavioral", "voice", "relationship", "current")
TIERS = {"quick": 10, "medium": 20, "deep": 35}
_TIER_RANK = {"quick": 0, "medium": 1, "deep": 2}

INTERVIEW_BANK: list[dict] = [
    # ── Core Personality (8) — the unconscious engine: want/need/lie/wound/value ──
    {"id": "want", "layer": "core", "tier_min": "quick",
     "text": "What does this character want so badly they'll act on it now?",
     "hint": "Be concrete — and why now, not last year?"},
    {"id": "need", "layer": "core", "tier_min": "quick",
     "text": "What do they actually need but would resist admitting?",
     "hint": "The internal lack the arc is about — usually not the same as the want."},
    {"id": "lie", "layer": "core", "tier_min": "quick",
     "text": "What false belief about themselves or the world are they organizing their life around?",
     "hint": "e.g. “I'm only safe if I'm in control,” “I'm only valuable if I'm needed.”"},
    {"id": "wound", "layer": "core", "tier_min": "medium",
     "text": "What early event or message made that belief feel true — the line that, said aloud now, would still detonate?",
     "hint": "The ghost. If there's no single event, the repeated pattern."},
    {"id": "shame", "layer": "core", "tier_min": "medium",
     "text": "What are they most afraid someone will discover or confirm about them?",
     "hint": "What self-judgment does it imply?"},
    {"id": "value_hierarchy", "layer": "core", "tier_min": "deep",
     "text": "What would they sacrifice comfort, status, or love to protect?",
     "hint": "If several compete, force a ranking — that ordering is the character."},
    {"id": "moral_line", "layer": "core", "tier_min": "deep",
     "text": "What line will they not cross — and what could push them over it?",
     "hint": "If “nothing,” test desperation or a loved one in danger."},
    {"id": "self_gap", "layer": "core", "tier_min": "deep",
     "text": "How do they want to be seen, versus how they privately see themselves?",
     "hint": "The persona/shadow gap. Contradiction reads as realism."},

    # ── Behavioral Patterns (7) — observable output of the core under pressure ────
    {"id": "stress_response", "layer": "behavioral", "tier_min": "quick",
     "text": "When genuinely threatened, what's their first move?",
     "options": ["fight / confront", "flee / deflect", "freeze / shut down", "fawn / appease", "it depends"],
     "branches": {
         "fight / confront": ["stress_backup"],
         "flee / deflect": ["stress_backup"],
         "freeze / shut down": ["stress_backup"],
         "fawn / appease": ["stress_backup"],
         "it depends": ["stress_split"],
     }},
    {"id": "stress_backup", "layer": "behavioral", "tier_min": "quick", "is_branch": True,
     "text": "And when that first response fails, what's the fallback?",
     "hint": "The fallback often exposes more than the default."},
    {"id": "stress_split", "layer": "behavioral", "tier_min": "quick", "is_branch": True,
     "text": "Split it: how do they react to a social/emotional threat vs a physical one?"},
    {"id": "vulnerability", "layer": "behavioral", "tier_min": "quick",
     "text": "When someone they care about pushes them to be honest, what do they do?",
     "hint": "Their attachment defense — pursue, stonewall, deflect, comply?"},
    {"id": "criticism", "layer": "behavioral", "tier_min": "medium",
     "text": "How do they react to criticism from someone they respect?",
     "hint": "If public vs private differ, capture both."},
    {"id": "deception", "layer": "behavioral", "tier_min": "medium",
     "text": "When they lie, what changes from their normal manner?",
     "hint": "A deviation from THEIR baseline — not a universal “tell.”"},
    {"id": "decision_tempo", "layer": "behavioral", "tier_min": "deep",
     "text": "Under pressure, how do they decide?",
     "options": ["fast / decisive", "slow / deliberate", "defer to others", "freeze / avoid deciding"]},
    {"id": "anger_tell", "layer": "behavioral", "tier_min": "deep",
     "text": "When anger rises, what shows physically before any words?",
     "hint": "The pre-verbal cue. If they hide it, what's the controlled version?"},
    {"id": "recovery", "layer": "behavioral", "tier_min": "deep",
     "text": "In the first hour after a real failure, what do they do?",
     "hint": "Their resilience ritual — or who/what restarts them."},

    # ── Voice Fingerprint (7) — the idiolect a reader IDs with the tags removed ───
    {"id": "cadence", "layer": "voice", "tier_min": "quick",
     "text": "Do they speak in clipped fragments, steady sentences, or carefully built thoughts?",
     "options": ["clipped fragments", "short and plain", "steady / balanced", "long, subordinate cascades"],
     "hint": "If it shifts under stress, give the baseline here — stress goes in the emotion question."},
    {"id": "directness", "layer": "voice", "tier_min": "quick",
     "text": "When they want something, are they direct, evasive, joking, or commanding?",
     "options": ["blunt / direct", "diplomatic", "evasive", "joking / deflecting", "commanding"]},
    {"id": "lexicon", "layer": "voice", "tier_min": "medium",
     "text": "What words, topics, or registers do they reach for — and which do they avoid?",
     "hint": "Include a pet phrase and a word they'd never use, if any."},
    {"id": "emotion_shift", "layer": "voice", "tier_min": "medium",
     "text": "How does fear or anger change their speech — pace, volume, length, or silence?",
     "hint": "If “it doesn't,” ask whether they go quieter or more controlled."},
    {"id": "register", "layer": "voice", "tier_min": "deep",
     "text": "At baseline, how formal, slangy, or profane are they?",
     "options": ["formal", "plain / neutral", "colloquial / slangy", "profane / raw", "technical / precise"],
     "hint": "If it's audience-dependent, that's a mask — note it in the relationship questions."},
    {"id": "silence", "layer": "voice", "tier_min": "deep",
     "text": "Do they fill silence, tolerate it, or weaponize it?",
     "options": ["fill it", "tolerate it", "weaponize it"]},
    {"id": "humor", "layer": "voice", "tier_min": "deep",
     "text": "What's their humor for — to bond, deflect, dominate, self-protect, or do they avoid it?",
     "options": ["to bond", "to deflect", "to dominate", "to self-protect", "they avoid humor"]},

    # ── Relationship Masks (8) — voice modulated per audience; active-verb tactics ─
    {"id": "safe_person", "layer": "relationship", "tier_min": "quick",
     "text": "Who gets the least-filtered version of them — and what's different in that voice?",
     "hint": "The unmasked baseline. If “no one,” the least-filtered context."},
    {"id": "authority_mask", "layer": "relationship", "tier_min": "quick",
     "text": "How do they speak to an authority they dislike but still need something from?",
     "hint": "What do they suppress to get it?"},
    {"id": "aspirational_mask", "layer": "relationship", "tier_min": "medium",
     "text": "How do they speak to someone they want to impress or protect?",
     "hint": "What do they edit out of their normal voice?"},
    {"id": "code_switch", "layer": "relationship", "tier_min": "medium",
     "text": "With whom do they change how they talk the most — and what stays constant no matter what?",
     "hint": "The invariant is the real them."},
    {"id": "status_down", "layer": "relationship", "tier_min": "deep",
     "text": "How do they speak to someone clearly beneath them in status?",
     "hint": "This is an ethics tell. Give a concrete example if you can."},
    {"id": "adversary_mask", "layer": "relationship", "tier_min": "deep",
     "text": "Facing an adversary, how do they try to wound without exposing themselves?",
     "hint": "Their weapon of choice — cold politeness, mockery, silence, a fact held back?"},
    {"id": "regression", "layer": "relationship", "tier_min": "deep",
     "text": "Which person makes them revert to an older, younger version of themselves?",
     "hint": "The regression trigger — usually family or a first love/rival."},
    {"id": "intimacy_ceiling", "layer": "relationship", "tier_min": "deep",
     "text": "What do they hide even from the person closest to them?",
     "hint": "The trust boundary. If “nothing,” test it under pressure."},

    # ── Current State (5) — a temporary filter; routed to states, not core canon ──
    {"id": "concealed_affect", "layer": "current", "tier_min": "quick",
     "text": "Right now, what feeling are they working hardest not to show?",
     "hint": "The active suppressed emotion most affecting their dialogue."},
    {"id": "hidden_agenda", "layer": "current", "tier_min": "medium",
     "text": "In their current scene, what are they hiding or secretly after?"},
    {"id": "scene_objective", "layer": "current", "tier_min": "medium",
     "text": "What concrete outcome do they need before the current scene ends?",
     "hint": "What would count as success for them?"},
    {"id": "body_load", "layer": "current", "tier_min": "deep",
     "text": "What physical condition right now most affects how they speak or choose?",
     "hint": "Pain, exhaustion, hunger, intoxication, injury — and who notices."},
    {"id": "state_duration", "layer": "current", "tier_min": "deep",
     "text": "Is this state a one-scene blip, a chapter-long phase, or a lasting arc shift?",
     "options": ["one scene", "a chapter", "an arc shift"],
     "hint": "Controls whether it expires or gets promoted."},
]

PLACE_BANK: list[dict] = [
    {"id": "purpose", "text": "What is this place for — what happens here?"},
    {"id": "atmosphere", "text": "What's the emotional atmosphere when you walk in?"},
    {"id": "sound", "text": "What does it sound like?"},
    {"id": "smell", "text": "What does it smell like?"},
    {"id": "lighting", "text": "What's the lighting like?"},
    {"id": "anchors", "text": "One or two memorable visual anchors?"},
    {"id": "layout", "text": "How does the spatial layout shape what people can do here?"},
    {"id": "control", "text": "Who controls this space, and what are its unspoken rules?"},
    {"id": "variation", "text": "How does it change by time of day, weather, or story phase?"},
    {"id": "motif", "text": "Any recurring symbolic motif tied to this place?"},
]

# Map place question ids → PlaceIdentity fields for deterministic fallback fill.
PLACE_FIELD_MAP = {
    "purpose": "purpose",
    "atmosphere": "atmosphere",
    "layout": "spatial_layout",
    "control": "controls_space",
    "motif": "symbolic_motif",
}

# Fast id → question lookup (includes branch questions) for synthesis prompts.
QUESTIONS_BY_ID = {q["id"]: q for q in INTERVIEW_BANK}

# Layers that "analyze existing writing" extracts from prose. Relationship masks
# (audience-specific) and current state (scene-specific) are interview-driven —
# the research is explicit that sample analysis is for the stable layers, and
# inferring audience/scene from prose is unreliable.
EXTRACTABLE_LAYERS = ("core", "behavioral", "voice")


def extractable_questions() -> list[dict]:
    """The base questions the analyze pass answers from a prose sample — every
    core/behavioral/voice question (not depth-limited; analyze finds whatever the
    prose supports). Returns [{id, layer, text}]."""
    return [
        {"id": q["id"], "layer": q["layer"], "text": q["text"]}
        for q in INTERVIEW_BANK
        if not q.get("is_branch") and q["layer"] in EXTRACTABLE_LAYERS
    ]


def interview_for_tier(tier: str) -> list[dict]:
    """Return every base question available at `tier` or below, plus any branch
    questions whose trigger base question is included. Base-question count lands on
    the tier's advertised total (10 / 20 / 35); branch questions are extra and only
    surface when their trigger option is chosen."""
    rank = _TIER_RANK.get(tier, 0)
    included = [q for q in INTERVIEW_BANK if not q.get("is_branch") and _TIER_RANK[q["tier_min"]] <= rank]
    base_ids = {q["id"] for q in included}
    # Pull in branch questions referenced by any included base question.
    for q in included.copy():
        for targets in (q.get("branches") or {}).values():
            for tid in targets:
                bq = QUESTIONS_BY_ID.get(tid)
                if bq and bq["id"] not in base_ids:
                    included.append(bq)
                    base_ids.add(bq["id"])
    return included

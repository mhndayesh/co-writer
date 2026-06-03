"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class APIResponse(BaseModel):
    ok: bool
    data: Any = None
    error: dict | None = None


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr
    display_name: str
    created_at: datetime
    plan_tier: str = "free"
    plan_status: str = "none"
    is_admin: bool = False


# ── Billing / subscriptions ───────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    tier: Literal["dev_ai", "byok"]
    success_url: str | None = None
    cancel_url: str | None = None


class SetPlanRequest(BaseModel):
    tier: Literal["free", "dev_ai", "byok"]
    status: str | None = None


class CreateCodeRequest(BaseModel):
    tier: Literal["dev_ai", "byok"]
    duration_days: int | None = None   # null = lifetime
    max_uses: int | None = None        # null = unlimited
    note: str = Field(default="", max_length=200)
    code: str | None = None            # custom code; blank → auto-generate


class RedeemCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


# ── Stories ─────────────────────────────────────────────────────────────

def _validate_cover_url(v: str | None) -> str | None:
    """Allow http(s) URLs or same-origin uploaded paths (/v1/media/…); block
    javascript:/data:/file:/protocol-relative // — these render into <img src>."""
    if v is None:
        return v
    s = v.strip()
    if not s:
        return None
    is_same_origin = s.startswith("/") and not s.startswith("//")
    if not (is_same_origin or s.lower().startswith(("http://", "https://"))):
        raise ValueError("cover_image_url must be an http(s) URL or an uploaded path")
    if len(s) > 2048:
        raise ValueError("cover_image_url is too long")
    return s


class StoryCreate(BaseModel):
    title: str = "Untitled"
    genre: str = ""
    palette_idx: int = 0


class StoryUpdate(BaseModel):
    title: str | None = None
    genre: str | None = None
    palette_idx: int | None = None
    cover_image_url: str | None = None

    _v_cover = field_validator("cover_image_url")(_validate_cover_url)


class StoryStats(BaseModel):
    words: int = 0
    chapters: int = 0
    characters: int = 0


class StoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    genre: str
    palette_idx: int
    cover_image_url: str | None = None
    graph_status: str
    created_at: datetime
    updated_at: datetime
    stats: StoryStats = StoryStats()


# ── World ───────────────────────────────────────────────────────────────

class WorldIn(BaseModel):
    title: str | None = None
    genre: str | None = None
    logline: str | None = None
    time_period: str | None = None
    setting: str | None = None
    rules: list[str] | None = None
    themes: list[str] | None = None
    lore: str | None = None
    seeds: str | None = None


class WorldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    story_id: str
    title: str
    genre: str
    logline: str
    time_period: str
    setting: str
    rules: list[str]
    themes: list[str]
    lore: str
    seeds: str


# ── Characters ──────────────────────────────────────────────────────────

class CharacterIn(BaseModel):
    name: str
    role: str = ""
    icon: str = ""
    age: str = ""
    appearance: str = ""
    personality: str = ""
    backstory: str = ""
    motivation: str = ""
    flaw: str = ""
    arc: str = ""
    status: str = "alive"


class CharacterPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    icon: str | None = None
    age: str | None = None
    appearance: str | None = None
    personality: str | None = None
    backstory: str | None = None
    motivation: str | None = None
    flaw: str | None = None
    arc: str | None = None
    status: str | None = None


class CharacterOut(CharacterIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str


class RelationshipIn(BaseModel):
    target_id: str
    type: str
    description: str = ""


class RelationshipOut(RelationshipIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_id: str


# ── Character Voice Studio (Narrative Fidelity Engine) ────────────────────

class IdentityLayerPatch(BaseModel):
    """Replace one identity layer (core|behavioral|voice). The payload shape is
    intentionally free-form — the layers evolve faster than a strict schema."""
    payload: dict = {}
    build_method: str | None = None


class IdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str
    character_id: str
    core_personality: dict = {}
    behavioral_patterns: dict = {}
    voice_fingerprint: dict = {}
    short_profile: str = ""
    build_method: str = ""
    completeness: dict = {}
    updated_at: datetime | None = None


class MaskIn(BaseModel):
    audience_character_id: str | None = None
    audience_label: str = ""
    speech_style: str = ""
    tells: str = ""
    notes: str = ""


class MaskOut(MaskIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    character_id: str


class StateIn(BaseModel):
    label: str = ""
    detail: str = ""
    kind: str = "temporary"  # temporary|recurring|arc
    chapter_id: str | None = None
    active: bool = True


class StateOut(StateIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    character_id: str


class IdentityVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    character_id: str
    version_no: int
    kind: str
    snapshot: dict = {}
    note: str = ""
    chapter_id: str | None = None
    created_at: datetime


# Method 1 — analyze existing writing. Provide pasted `text` and/or pick
# `chapter_ids` to analyze; the server assembles the sample under a char budget.
class AnalyzeWritingRequest(BaseModel):
    text: str = Field(default="", max_length=200_000)
    chapter_ids: list[str] = []


class TraitProposal(BaseModel):
    layer: str = ""            # core|behavioral|voice
    field: str = ""           # the key within that layer
    value: Any = ""
    confidence: float = 0.0   # 0-1
    excerpts: list[str] = []
    status: str = "proposed"


class AnalyzeWritingResponse(BaseModel):
    traits: list[TraitProposal] = []
    representative_dialogue: list[str] = []
    uncertain_areas: list[str] = []
    fallback: bool = False


class TraitDecision(BaseModel):
    layer: str
    field: str
    value: Any = ""
    decision: str = "approve"  # approve|edit|reject (edit carries an updated value)


class ApproveTraitsRequest(BaseModel):
    decisions: list[TraitDecision] = []


# Method 2 — guided interview
class InterviewSubmitRequest(BaseModel):
    answers: dict = {}          # {question_id: answer}
    tier: str = "quick"


# Place Identity (Part 1C)
class PlaceIdentityPatch(BaseModel):
    purpose: str | None = None
    atmosphere: str | None = None
    sensory_palette: dict | None = None
    visual_anchors: list[Any] | None = None
    spatial_layout: str | None = None
    controls_space: str | None = None
    social_rules: str | None = None
    normal_behavior: str | None = None
    variations: dict | None = None
    symbolic_motif: str | None = None


class PlaceIdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    location_id: str
    purpose: str = ""
    atmosphere: str = ""
    sensory_palette: dict = {}
    visual_anchors: list[Any] = []
    spatial_layout: str = ""
    controls_space: str = ""
    social_rules: str = ""
    normal_behavior: str = ""
    variations: dict = {}
    symbolic_motif: str = ""


class PlaceBuildRequest(BaseModel):
    answers: dict = {}


# Observer + Dialogue Writer (Part 2)
class ObserverCritiqueRequest(BaseModel):
    draft: str = Field(min_length=1, max_length=200_000)
    chapter_id: str | None = None
    strictness: str = "balanced"  # light|balanced|strict


class ObserverNote(BaseModel):
    line: str = ""               # exact sentence copied from the draft
    category: str = ""
    severity: str = "low"        # high|medium|low
    confidence: float = 0.0
    message: str = ""
    suggestion: str = ""
    character_id: str | None = None
    character: str = ""
    fingerprint: str = ""        # server-computed; used by mark-intentional


class ObserverCritiqueResponse(BaseModel):
    notes: list[ObserverNote] = []
    fallback: bool = False


class RewriteRequest(BaseModel):
    draft: str = Field(default="", max_length=200_000)
    instruction: str = Field(default="", max_length=8_000)
    participants: list[str] = []   # character ids
    objective: str = Field(default="", max_length=8_000)
    chapter_id: str | None = None
    strictness: str = "balanced"


class MarkIntentionalRequest(BaseModel):
    line: str
    note_kind: str = ""
    reason: str = ""
    chapter_id: str | None = None
    character_id: str | None = None


class UpdateProfileFromNoteRequest(BaseModel):
    character_id: str
    layer: str                   # core|behavioral|voice
    field: str
    value: Any = ""


# Post-scene evolve
class EvolveRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    chapter_id: str | None = None


class EvolveSuggestion(BaseModel):
    type: str = ""               # new_phrase|revealed_fear|relationship_change|...
    character: str = ""
    character_id: str | None = None
    summary: str = ""
    suggested_save_as: str = "temporary"  # temporary|recurring|permanent|not_saved
    excerpt: str = ""


class EvolveResponse(BaseModel):
    suggestions: list[EvolveSuggestion] = []
    fallback: bool = False


class EvolveDecision(BaseModel):
    type: str = ""
    character_id: str | None = None
    summary: str = ""
    save_as: str = "not_saved"   # temporary|recurring|permanent|not_saved


class ApplyEvolveRequest(BaseModel):
    decisions: list[EvolveDecision] = []


# Voice comparison
class CompareRequest(BaseModel):
    character_ids: list[str] = Field(min_length=2)
    situation: str = Field(min_length=1, max_length=8_000)


class CompareEntry(BaseModel):
    character_id: str = ""
    character: str = ""
    response: str = ""


class CompareResponse(BaseModel):
    entries: list[CompareEntry] = []
    fallback: bool = False


# ── Chapters ────────────────────────────────────────────────────────────

class ChapterIn(BaseModel):
    title: str = ""
    content: str = ""
    summary: str = ""
    number: int | None = None
    pov_character_id: str | None = None
    location_id: str | None = None
    character_ids: list[str] = []
    seeds: list[Any] = []
    cover_image_url: str | None = None

    _v_cover = field_validator("cover_image_url")(_validate_cover_url)


class ChapterPatch(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    number: int | None = None
    pov_character_id: str | None = None
    location_id: str | None = None
    character_ids: list[str] | None = None
    seeds: list[Any] | None = None
    cover_image_url: str | None = None

    _v_cover = field_validator("cover_image_url")(_validate_cover_url)


class ChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str
    number: int
    title: str
    content: str
    summary: str
    cover_image_url: str | None = None
    pov_character_id: str | None
    location_id: str | None
    character_ids: list[str]
    seeds: list[Any]
    created_at: datetime
    updated_at: datetime


# ── Flow Writing ────────────────────────────────────────────────────────

class FlowPolishRequest(BaseModel):
    raw: str = Field(max_length=200_000)
    notes: str = Field(default="", max_length=8_000)
    # Optional scene setup (Voice Studio): who/where the scene is, so their full
    # identity is pinned in context. Empty → unchanged behavior.
    scene_character_ids: list[str] = []
    scene_location_id: str | None = None


class FlowPolishResponse(BaseModel):
    polished: str
    fallback: bool = False


class FlowExtractRequest(BaseModel):
    polished: str = Field(max_length=200_000)


class ExtractedCharacter(BaseModel):
    name: str
    role: str = ""
    note: str = ""
    status: str = ""       # alive|dead|unknown|missing|transformed — empty = no change
    arc_note: str = ""     # development observed in this scene — appended to character arc
    is_new: bool = True
    # The LLM echoes back the exact [id:…] of an existing CAST member it's
    # referring to. When present and valid it resolves the character
    # unambiguously — the only safe way to disambiguate two same-named cast
    # members. Server fills `existing_id` from it (or from a unique name match).
    character_id: str | None = None
    existing_id: str | None = None


class ExtractedEvent(BaseModel):
    kind: str = "event"
    description: str
    involved: list[str] = []


class ExtractedRelationship(BaseModel):
    source: str  # character name (must match characters[].name)
    target: str
    type: str    # ally|enemy|lover|rival|family|friend|mentor|...
    description: str = ""


class ExtractedFaction(BaseModel):
    name: str
    description: str = ""


class ExtractedLocation(BaseModel):
    name: str
    description: str = ""


class ExtractedThread(BaseModel):
    name: str
    description: str = ""
    status: str = "open"


class ExtractedRevelation(BaseModel):
    description: str
    kind: str = "revelation"
    characters_who_know: list[str] = []
    reader_knows: bool = False
    notes: str = ""
    confidence: float = 1.0


class ExtractedScene(BaseModel):
    ordinal: int = 0
    title: str = ""
    beat: str = ""
    summary: str = ""
    goal: str = ""
    conflict: str = ""
    outcome: str = ""
    pov: str = ""
    location: str = ""
    characters: list[str] = []
    plot_threads: list[str] = []
    time_anchor: str = ""
    time_sort_key: float | None = None
    duration_hint: str = ""
    sensory_palette: dict[str, int] = {}
    revelations: list[ExtractedRevelation] = []
    source_excerpt: str = ""
    content: str = ""


class FlowExtractResponse(BaseModel):
    title_suggestion: str = ""
    summary: str = ""
    pov_suggestion: str = ""
    location_suggestion: str = ""
    characters: list[ExtractedCharacter] = []
    events: list[ExtractedEvent] = []
    relationships: list[ExtractedRelationship] = []
    themes: list[str] = []
    locations: list[ExtractedLocation] = []
    factions: list[ExtractedFaction] = []
    threads: list[ExtractedThread] = []
    scenes: list[ExtractedScene] = []
    world_rules: list[str] = []
    world_lore: str = ""
    fallback: bool = False


class FlowApproveRequest(BaseModel):
    raw: str
    polished: str
    extracted: FlowExtractResponse
    include_character_names: list[str] = []
    chapter_title: str = ""
    chapter_summary: str = ""
    # If set, overwrite this existing chapter instead of appending a new one.
    # New characters/locations/etc from extract are still added (additive).
    target_chapter_id: str | None = None
    # If set (and target_chapter_id is None), create the new chapter at this
    # specific number — used to fill gaps in chapter numbering.
    target_chapter_number: int | None = None


class FlowApproveResponse(BaseModel):
    chapter_id: str
    new_character_ids: list[str] = []
    added_themes: list[str] = []
    scene_ids: list[str] = []
    revelation_ids: list[str] = []
    thread_scene_link_ids: list[str] = []
    version_no: int


# ── Language Enhancer ───────────────────────────────────────────────────

class FlowEnhanceRequest(BaseModel):
    raw: str = Field(max_length=200_000)


class FlowEnhanceResponse(BaseModel):
    language: str = ""
    enhanced: str = ""
    notes: str = ""
    fallback: bool = False


# ── Writing Companion (Chapters tab) ────────────────────────────────────

class CompanionRequest(BaseModel):
    chapter_id: str | None = None
    instruction: str = Field(min_length=1, max_length=8_000)


class CompanionResponse(BaseModel):
    draft: str
    fallback: bool = False


# ── Story Check ─────────────────────────────────────────────────────────

RevisionPass = Literal["structure", "character", "logic", "dialogue", "tightening"]


class StoryCheckRequest(BaseModel):
    chapter_id: str | None = None
    pass_type: RevisionPass = "logic"


class CheckFinding(BaseModel):
    severity: Literal["high", "medium", "low"]
    title: str
    detail: str
    suggestion: str = ""
    chapter_id: str | None = None
    scene_id: str | None = None


class StoryCheckResponse(BaseModel):
    chapter_id: str | None = None
    pass_type: RevisionPass = "logic"
    findings: list[CheckFinding] = []
    strengths: list[str] = []
    severity_buckets: dict = {}
    fallback: bool = False


# ── Graph ───────────────────────────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    label: str
    kind: Literal["character", "chapter", "theme", "location", "faction", "scene", "thread", "revelation"]
    color: str = ""
    size: int = 1
    data: dict = {}


class GraphLink(BaseModel):
    source: str
    target: str
    kind: str
    label: str = ""


class GraphView(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]
    source: Literal["neo4j", "postgres_fallback"]


# ── LLM Settings ────────────────────────────────────────────────────────

ProviderName = Literal["lmstudio", "openai", "anthropic", "openrouter", "gemini", "deepseek"]
LaneName = Literal["creative", "technical", "embedding"]


class LaneConfigIn(BaseModel):
    provider: ProviderName
    base_url: str = ""
    model: str = ""
    embed_model: str = ""
    api_key: str = ""  # plaintext on the wire; blank = keep existing

    @field_validator("base_url")
    @classmethod
    def _no_ssrf(cls, v: str) -> str:
        from app.core.ssrf import validate_provider_base_url
        return validate_provider_base_url(v)


class LaneConfigOut(BaseModel):
    provider: str = ""
    base_url: str = ""
    model: str = ""
    embed_model: str = ""
    has_api_key: bool = False


class LLMConfigIn(BaseModel):
    creative: LaneConfigIn | None = None
    technical: LaneConfigIn | None = None
    embedding: LaneConfigIn | None = None


class LLMConfigOut(BaseModel):
    creative: LaneConfigOut
    technical: LaneConfigOut
    embedding: LaneConfigOut


class LLMStatus(BaseModel):
    provider: str
    model: str
    reachable: bool
    detail: str = ""
    lane: str = "creative"


# ── Owner control panel: shape-shift + house default + tunable caps ──────────

class ActAsRequest(BaseModel):
    # None or "owner" = exit test mode (real unlimited owner).
    tier: Literal["free", "dev_ai", "byok", "owner"] | None = None


class HouseConfigIn(BaseModel):
    """The default AI every free + dev_ai user runs on. provider=None reverts to
    the env default. base_url SSRF-validated like a normal lane."""
    provider: ProviderName | None = None
    base_url: str = ""
    model: str = ""
    embed_model: str = ""
    api_key: str = ""  # plaintext on the wire; blank = keep the stored key

    @field_validator("base_url")
    @classmethod
    def _no_ssrf(cls, v: str) -> str:
        from app.core.ssrf import validate_provider_base_url
        return validate_provider_base_url(v)


class CapsIn(BaseModel):
    # None = use the env default. >= 0 (0 means "blocked").
    dev_ai_max_actions: int | None = Field(default=None, ge=0)
    dev_ai_max_tokens: int | None = Field(default=None, ge=0)
    free_trial_max_actions: int | None = Field(default=None, ge=0)
    free_trial_max_tokens: int | None = Field(default=None, ge=0)


class SiteConfigIn(BaseModel):
    house: HouseConfigIn = Field(default_factory=HouseConfigIn)
    caps: CapsIn = Field(default_factory=CapsIn)


class ProviderInfo(BaseModel):
    name: str
    base_url: str = ""
    default_model: str = ""
    default_embed_model: str = ""
    can_embed: bool = True


# ── Locations / Factions / Threads / Scenes ─────────────────────────────

class NamedDescribedIn(BaseModel):
    name: str
    description: str = ""


class NamedDescribedOut(NamedDescribedIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str


class LocationIn(NamedDescribedIn):
    visual: str = ""


class LocationOut(NamedDescribedOut):
    visual: str = ""


class FactionIn(NamedDescribedIn):
    visual_signature: str = ""


class FactionOut(NamedDescribedOut):
    visual_signature: str = ""


class PlotThreadIn(BaseModel):
    name: str
    description: str = ""
    status: str = "open"
    chapter_ids: list[str] = []


class PlotThreadOut(PlotThreadIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str


class SceneCardIn(BaseModel):
    chapter_id: str | None = None
    ordinal: int = 0
    beat: str = ""
    title: str = ""
    summary: str = ""
    goal: str = ""
    conflict: str = ""
    outcome: str = ""
    pov_character_id: str | None = None
    location_id: str | None = None
    character_ids: list[str] = []
    plot_thread_ids: list[str] = []
    time_anchor: str = ""
    time_sort_key: float | None = None
    duration_hint: str = ""
    sensory_palette: dict[str, int] = {}
    source_excerpt: str = ""
    content: str = ""


class SceneCardPatch(BaseModel):
    chapter_id: str | None = None
    ordinal: int | None = None
    beat: str | None = None
    title: str | None = None
    summary: str | None = None
    goal: str | None = None
    conflict: str | None = None
    outcome: str | None = None
    pov_character_id: str | None = None
    location_id: str | None = None
    character_ids: list[str] | None = None
    plot_thread_ids: list[str] | None = None
    time_anchor: str | None = None
    time_sort_key: float | None = None
    duration_hint: str | None = None
    sensory_palette: dict[str, int] | None = None
    source_excerpt: str | None = None
    content: str | None = None


class SceneCardOut(SceneCardIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str


class RevelationIn(BaseModel):
    scene_id: str | None = None
    chapter_id: str | None = None
    description: str
    kind: str = "revelation"
    characters_who_know: list[str] = []
    reader_knows: bool = False
    notes: str = ""
    confidence: float = 1.0


class RevelationPatch(BaseModel):
    scene_id: str | None = None
    chapter_id: str | None = None
    description: str | None = None
    kind: str | None = None
    characters_who_know: list[str] | None = None
    reader_knows: bool | None = None
    notes: str | None = None
    confidence: float | None = None


class RevelationOut(RevelationIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str
    created_at: datetime


class PlotThreadSceneLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str
    thread_id: str
    scene_id: str
    chapter_id: str | None
    status: str
    strength: float
    evidence: str


class TimelineSceneOut(SceneCardOut):
    chapter_number: int | None = None
    chapter_title: str = ""
    pov_name: str = ""
    location_name: str = ""
    character_names: list[str] = []
    plot_thread_names: list[str] = []


class WeaveCellOut(BaseModel):
    scene_id: str
    chapter_id: str | None = None
    chapter_number: int | None = None
    scene_ordinal: int = 0
    scene_title: str = ""
    status: str = "touch"
    strength: float = 1.0
    evidence: str = ""


class WeaveThreadOut(BaseModel):
    thread_id: str
    name: str
    status: str
    description: str = ""
    cells: list[WeaveCellOut] = []
    dormant_after: int | None = None


class WeaveOut(BaseModel):
    threads: list[WeaveThreadOut]
    scenes: list[TimelineSceneOut]


class CharacterVoiceProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str
    character_id: str
    sample_count: int
    dialogue_words: int
    avg_sentence_words: float
    question_rate: float
    exclamation_rate: float
    vocabulary_variety: float
    dialogue_share: float
    repeated_phrases: list[str]
    stats: dict
    updated_at: datetime

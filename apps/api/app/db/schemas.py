"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


# ── Stories ─────────────────────────────────────────────────────────────

class StoryCreate(BaseModel):
    title: str = "Untitled"
    genre: str = ""
    palette_idx: int = 0


class StoryUpdate(BaseModel):
    title: str | None = None
    genre: str | None = None
    palette_idx: int | None = None


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


class ChapterPatch(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    number: int | None = None
    pov_character_id: str | None = None
    location_id: str | None = None
    character_ids: list[str] | None = None
    seeds: list[Any] | None = None


class ChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str
    number: int
    title: str
    content: str
    summary: str
    pov_character_id: str | None
    location_id: str | None
    character_ids: list[str]
    seeds: list[Any]
    created_at: datetime
    updated_at: datetime


# ── Flow Writing ────────────────────────────────────────────────────────

class FlowPolishRequest(BaseModel):
    raw: str
    notes: str = ""


class FlowPolishResponse(BaseModel):
    polished: str
    fallback: bool = False


class FlowExtractRequest(BaseModel):
    polished: str


class ExtractedCharacter(BaseModel):
    name: str
    role: str = ""
    note: str = ""
    is_new: bool = True
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
    version_no: int


# ── Writing Companion (Chapters tab) ────────────────────────────────────

class CompanionRequest(BaseModel):
    chapter_id: str | None = None
    instruction: str


class CompanionResponse(BaseModel):
    draft: str
    fallback: bool = False


# ── Story Check ─────────────────────────────────────────────────────────

class StoryCheckRequest(BaseModel):
    chapter_id: str


class CheckFinding(BaseModel):
    severity: Literal["high", "medium", "low"]
    title: str
    detail: str
    suggestion: str = ""


class StoryCheckResponse(BaseModel):
    chapter_id: str
    findings: list[CheckFinding] = []
    strengths: list[str] = []
    severity_buckets: dict = {}
    fallback: bool = False


# ── Graph ───────────────────────────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    label: str
    kind: Literal["character", "chapter", "theme", "location", "faction"]
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

class LLMSettingsIn(BaseModel):
    provider: Literal["lmstudio", "openai", "anthropic", "openrouter", "gemini"]
    base_url: str = ""
    model: str = ""
    embed_model: str = ""
    api_key: str = ""  # plaintext on the wire, encrypted at rest


class LLMSettingsOut(BaseModel):
    provider: str
    base_url: str
    model: str
    embed_model: str
    has_api_key: bool


class LLMStatus(BaseModel):
    provider: str
    model: str
    reachable: bool
    detail: str = ""
    role: str = "default"


LLMMode = Literal["single", "split", "custom"]
ProviderName = Literal["lmstudio", "openai", "anthropic", "openrouter", "gemini"]


class LLMProfileIn(BaseModel):
    provider: ProviderName
    base_url: str = ""
    model: str = ""
    embed_model: str = ""
    api_key: str = ""  # plaintext on the wire; blank = keep existing


class LLMProfileOut(BaseModel):
    provider: str = ""
    base_url: str = ""
    model: str = ""
    embed_model: str = ""
    has_api_key: bool = False


class LLMConfigIn(BaseModel):
    mode: LLMMode = "single"
    default: LLMProfileIn | None = None
    creative: LLMProfileIn | None = None
    technical: LLMProfileIn | None = None
    embedding: LLMProfileIn | None = None
    # page -> profile, e.g. {"flow.polish": {...}}
    tasks: dict[str, LLMProfileIn] = {}


class LLMConfigOut(BaseModel):
    mode: LLMMode
    default: LLMProfileOut
    creative: LLMProfileOut | None = None
    technical: LLMProfileOut | None = None
    embedding: LLMProfileOut | None = None
    tasks: dict[str, LLMProfileOut] = {}


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
    content: str = ""


class SceneCardOut(SceneCardIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    story_id: str

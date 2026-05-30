"""Deterministic character voice fingerprinting.

This is intentionally conservative. It only attributes quoted dialogue when a
nearby speaker tag names a known character, then stores lightweight style
statistics for comparison in the UI and Story Check prompts.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chapter, Character, CharacterVoiceProfile

SPEECH_VERBS = r"said|asked|replied|whispered|shouted|cried|murmured|called|answered|snapped|told|hissed"
QUOTE_RE = re.compile(r"[\"“](.+?)[\"”]", re.DOTALL)
WORD_RE = re.compile(r"[A-Za-z']+")


def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def _attribute_quote(text: str, start: int, end: int, names: list[str]) -> str | None:
    before = text[max(0, start - 140):start]
    after = text[end:min(len(text), end + 140)]
    for name in names:
        safe = re.escape(name)
        patterns = [
            rf"{safe}\s+(?:{SPEECH_VERBS})\b",
            rf"(?:{SPEECH_VERBS})\s+{safe}\b",
        ]
        if any(re.search(p, before, flags=re.IGNORECASE) for p in patterns):
            return name
        if any(re.search(p, after, flags=re.IGNORECASE) for p in patterns):
            return name
    return None


def _repeated_phrases(words: list[str]) -> list[str]:
    if len(words) < 6:
        return []
    phrases = Counter(" ".join(words[i:i + 3]) for i in range(len(words) - 2))
    return [p for p, n in phrases.most_common(8) if n > 1]


async def rebuild_profiles(db: AsyncSession, story_id: str) -> list[CharacterVoiceProfile]:
    characters = (
        await db.execute(select(Character).where(Character.story_id == story_id).order_by(Character.created_at))
    ).scalars().all()
    chapters = (
        await db.execute(select(Chapter).where(Chapter.story_id == story_id).order_by(Chapter.number))
    ).scalars().all()
    names = [c.name for c in characters if c.name]

    samples: dict[str, list[str]] = defaultdict(list)
    all_dialogue_words = 0
    for chapter in chapters:
        content = chapter.content or ""
        for match in QUOTE_RE.finditer(content):
            quote = re.sub(r"\s+", " ", match.group(1).strip())
            if not quote:
                continue
            quote_words = _words(quote)
            all_dialogue_words += len(quote_words)
            speaker = _attribute_quote(content, match.start(), match.end(), names)
            if speaker:
                samples[speaker.lower()].append(quote)

    existing = (
        await db.execute(select(CharacterVoiceProfile).where(CharacterVoiceProfile.story_id == story_id))
    ).scalars().all()
    by_character = {p.character_id: p for p in existing}
    now = datetime.now(timezone.utc)
    profiles: list[CharacterVoiceProfile] = []

    for character in characters:
        char_samples = samples.get(character.name.lower(), [])
        combined = " ".join(char_samples)
        words = _words(combined)
        sentences = _sentences(combined)
        dialogue_words = len(words)
        sample_count = len(char_samples)
        avg_sentence_words = (dialogue_words / len(sentences)) if sentences else 0.0
        question_rate = sum(1 for s in char_samples if "?" in s) / sample_count if sample_count else 0.0
        exclamation_rate = sum(1 for s in char_samples if "!" in s) / sample_count if sample_count else 0.0
        vocabulary_variety = len(set(words)) / dialogue_words if dialogue_words else 0.0
        dialogue_share = dialogue_words / all_dialogue_words if all_dialogue_words else 0.0
        repeated = _repeated_phrases(words)

        profile = by_character.get(character.id)
        if profile is None:
            profile = CharacterVoiceProfile(story_id=story_id, character_id=character.id)
            db.add(profile)
        profile.sample_count = sample_count
        profile.dialogue_words = dialogue_words
        profile.avg_sentence_words = round(avg_sentence_words, 2)
        profile.question_rate = round(question_rate, 3)
        profile.exclamation_rate = round(exclamation_rate, 3)
        profile.vocabulary_variety = round(vocabulary_variety, 3)
        profile.dialogue_share = round(dialogue_share, 3)
        profile.repeated_phrases = repeated
        profile.stats = {
            "character_name": character.name,
            "sample_preview": char_samples[:3],
            "all_dialogue_words": all_dialogue_words,
        }
        profile.updated_at = now
        profiles.append(profile)

    await db.flush()
    return profiles


async def list_profiles(db: AsyncSession, story_id: str) -> list[CharacterVoiceProfile]:
    rows = (
        await db.execute(
            select(CharacterVoiceProfile)
            .where(CharacterVoiceProfile.story_id == story_id)
            .order_by(CharacterVoiceProfile.updated_at.desc())
        )
    ).scalars().all()
    if rows:
        return rows
    return await rebuild_profiles(db, story_id)

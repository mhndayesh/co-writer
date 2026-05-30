# Story Forge — Documentation

> **⚠️ Historical reference — the original product vision, not the current build.**
> This describes the first prototype: a single self-contained React component
> (`story_forge.jsx`, local-first, IndexedDB, Anthropic-only). The shipping app is a
> full-stack FastAPI + Next.js system (Postgres/SQLite, Neo4j, Qdrant, five LLM
> providers with split routing). Read this for the *why* — the writing philosophy and
> UX intent. For the current architecture and how to run it, see [README.md](README.md),
> [RUN.md](RUN.md), and [CLAUDE.md](CLAUDE.md). Where this doc and the code disagree, the
> code wins — e.g. character relationships are now **one row per character pair** in a
> `character_relationships` table, not a nested array on the character.

An AI-powered writing studio for people with vivid imagination but no formal writing craft. You write freely; the AI turns it into polished prose and quietly organizes the characters, events, places, and themes behind the scenes.

Everything is one self-contained React component (`story_forge.jsx`). It is **local-first** (your work stays on your device) and built so a **cloud backend can be added later by changing a single line**.

---

## Table of contents

1. [Quick start](#1-quick-start)
2. [The big idea](#2-the-big-idea)
3. [User guide](#3-user-guide)
4. [Backup & restore](#4-backup--restore)
5. [Architecture](#5-architecture)
6. [Data model](#6-data-model)
7. [Going cloud later](#7-going-cloud-later)
8. [Known limits & tips](#8-known-limits--tips)
9. [Code map](#9-code-map)

---

## 1. Quick start

**Inside Claude (as an artifact):** it just runs. Storage and the AI are wired automatically.

**As your own standalone app:** drop `story_forge.jsx` into any React project (Vite, Next.js, Create React App). It needs:

- `react` (hooks)
- `d3` (the Story Map graph)
- A way to reach the Anthropic API (see [AI calls](#52-ai-calls))

When run outside Claude, the app automatically falls back to **IndexedDB** for storage, so it works as a true local app with no extra setup.

```bash
npm install react d3
# place story_forge.jsx in your src, import and render <App />
```

---

## 2. The big idea

A normal writing tool makes *you* do the craft. Story Forge flips it:

> **You** pour out the raw idea → **the AI** makes it professional and extracts the structure → **you** approve or give notes → **the system** files everything into the right places.

The person using it never has to think about grammar, structure, character sheets, or continuity. That bookkeeping happens for them.

---

## 3. User guide

The app opens on the **Studio** — your home screen. Each story is a separate project. Open one and you get six tabs in the sidebar.

### The Studio (home)

- **New Story** — name it and pick a genre; it opens straight into Flow Writing.
- **Project cards** show word count, chapters, characters, and when you last touched each story. Each gets its own colour accent.
- **Open →** enters a project; the **✕** deletes one (with a confirmation).
- **Back up all / Restore** — see [section 4](#4-backup--restore).

### ❦ Flow Writing — the main event

The heart of the app, and where every project opens. Three steps:

1. **Write freely.** A big, calm page. No rules — fragments, typos, shorthand are all fine. Hit **Shape this into a scene →**.
2. **Review.** The AI returns:
   - Your idea rewritten as **polished prose**.
   - **What it found inside it** — new characters (each with a checkbox so you choose which to keep), existing characters who appear, locations, key events, and themes.
   - Either approve, or click **Add notes & revise** and tell it what to change in plain language ("make her angrier," "the brother is older"). It redoes everything with your notes — repeat until right.
3. **Done.** On approval the system automatically:
   - Saves the prose as a new **chapter** (with title, summary, POV, location, characters-present all set).
   - Adds selected **new characters** to your cast (no duplicates).
   - Weaves new **themes** into your world.
   - Maps everyone into the Story Map.

### ❧ Chapters

The structured editor for fine-tuning what Flow Writing produced — or writing manually. Per chapter: title, POV character, location, who's present, the prose itself (manuscript-style), and a summary. Includes a **Writing Companion** (describe a scene, AI drafts it) and an **Export Chapter** button. Autosaves as you type.

### ◈ Characters

Full profiles: role, status (alive / dead / unknown / missing / transformed), age, appearance, personality, backstory, motivation, fatal flaw, arc — plus a **relationships** builder linking characters (ally, enemy, lover, rival, family, etc.). Autosaves as you type.

### ✦ Your World

The story bible: title, genre, time period, logline, setting, lore, **world rules** (laws the AI always respects), **themes**, and a **seeds-to-pay-off** tracker for foreshadowing. Autosaves as you type.

### ◎ Story Map

A live force-directed graph of your whole story. Gold nodes = characters, rose = chapters, green = themes. Lines show relationships and who appears where. Drag nodes, scroll to zoom.

### ◇ Story Check

Pick a chapter; the AI reads it against your **entire** world bible, every character, and all previous chapters, then reports inconsistencies, logic gaps, and broken world rules — graded by severity — plus what's working well.

---

## 4. Backup & restore

Because data is local, the Studio has two controls:

- **⬇ Back up all** — downloads one `.json` file containing every project, character, chapter, and world bible.
- **⬆ Restore** — load that file on any device or browser to bring everything back.

This is also your bridge to cloud: the backup file is exactly the shape a sync service would store. **Tip:** back up regularly — clearing browser data erases local storage.

---

## 5. Architecture

### 5.1 Storage layer (the important part)

All persistence flows through one object, `DB`, with four methods:

```
DB.get(key)        -> value | null
DB.set(key, value) -> void
DB.del(key)        -> void
DB.keys(prefix)    -> [keys]
```

Nothing else in the app touches storage directly. `DB` is produced by `makeLocalDB()`, which:

- uses **`window.storage`** when available (inside Claude / the app), and
- falls back to **IndexedDB** when run standalone.

App-level helpers name the only keys that exist:

| Helper | Key |
|---|---|
| `loadStudio` / `saveStudio` | `sf_studio_v2` (the project index) |
| `loadProject` / `saveProject` / `deleteProject` | `sf_proj_<id>` (one per story) |

Each project stores `{ world, chars, chaps }`. Projects are fully isolated — switching never mixes their data.

### 5.2 AI calls

A single helper drives every AI feature:

```js
callAI(systemPrompt, userMessage)
// POST https://api.anthropic.com/v1/messages
// model: claude-sonnet-4-20250514
```

`buildCtx(world, chars, chaps)` assembles the full story context that gets injected into every call, so the AI always knows the world and cast.

Features using it: Flow Writing (a two-step **polish → extract** pipeline), the Writing Companion, and Story Check (returns structured JSON with a safe fallback if parsing fails).

### 5.3 Autosave

Your World, Characters, and Chapters each debounce-save ~900 ms after you stop typing, guarded so a save never loops. Manual **Save** buttons remain for reassurance. Flow Writing commits on approval.

### 5.4 Rendering

One `App` component holds all state. When no project is open it renders `<Studio>`; otherwise the sidebar plus the active tab. The Story Map uses D3's force simulation (`forceLink` distance 170, charge −600, collision 60) inside a zoom/pan group.

---

## 6. Data model

**World**
```js
{ title, genre, logline, timePeriod, setting,
  rules: [String], themes: [String], lore, seeds }
```

**Character**
```js
{ id, name, role, icon, age, appearance, personality,
  backstory, motivation, flaw, arc, status,
  relationships: [{ targetId, type, desc }] }
```

**Chapter**
```js
{ id, number, title, content, summary,
  pov,            // character id
  location,
  characters,     // [character id]
  seeds }
```

**Project (Studio index entry)**
```js
{ id, title, genre, paletteIdx, createdAt, updatedAt,
  stats: { words, chapters, chars } }
```

---

## 7. Going cloud later

The migration is intentionally tiny. The file already contains a commented `makeCloudDB(session)` stub. To switch:

1. Stand up a backend that stores key→value JSON per user (Supabase is the closest match — Postgres + auth + row-level security).
2. Implement the same four methods (`get / set / del / keys`) against it.
3. Add a sign-in flow that yields a `session`.
4. Change **one line**:

```js
const DB = makeLocalDB();          // before
const DB = makeCloudDB(session);   // after
```

Every feature — Studio, projects, Flow Writing, autosave, backup — becomes cloud-backed with no other edits, because they all already go through `DB`. The backup/restore JSON format doubles as your import path for migrating existing local data into the cloud.

**Suggested Supabase shape:**

```sql
create table kv (
  user_id uuid references auth.users not null,
  k text not null,
  v jsonb not null,
  primary key (user_id, k)
);
-- enable row-level security; policy: user_id = auth.uid()
```

---

## 8. Known limits & tips

- **Local = this device.** No cross-device sync until cloud is added. Use Backup/Restore to move between machines.
- **Long single generations can truncate** due to the response token cap. Flow Writing naturally encourages scene-sized chunks, which avoids this — write a scene at a time rather than a whole chapter in one go.
- **Clearing browser data erases local storage.** Back up first.
- **Browser storage APIs** (`localStorage`/`sessionStorage`) are intentionally not used; persistence is `window.storage` or IndexedDB only.

---

## 9. Code map

Everything lives in `story_forge.jsx`, in this order:

| Section | What it is |
|---|---|
| palette `C`, `COVER_PALETTES` | colours / theme |
| utils | `uid`, `wc` (word count), `timeAgo`, `defaultWorld` |
| **storage layer** | `idbAdapter`, `makeLocalDB`, `makeCloudDB` stub, `DB`, key helpers, `exportAllData` / `importAllData` |
| `buildCtx`, `callAI` | AI context + request |
| export helpers | `dl`, `exportChapter`, `exportFull`, `exportBible` |
| shared UI | `Inp`, `Ta`, `Sel`, `FG`, `Btn`, `Card`, `PageHdr` |
| `Studio` | project hub + backup/restore |
| `Sidebar` | nav, stats, export menu, back-to-studio |
| `WorldTab` | the story bible |
| `CharactersTab` | character CRUD + relationships |
| `FlowTab` | free-write → polish → review → integrate |
| `WritingTab` | structured chapter editor + Writing Companion |
| `GraphTab` | D3 Story Map |
| `CheckTab` | continuity analysis |
| `App` | state, save logic, Flow integration, routing |

---

*Story Forge — write freely; the craft happens behind the scenes.*

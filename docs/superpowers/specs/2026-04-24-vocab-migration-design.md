# Vocab Migration Design — 2026-04-24

Migrate from the hand-built `group1.json` (53 words, pre-labeled targets) to a dataset generated from `kandy_core_vocab.xlsx` (1309 words), and adapt the app to pick 25 targets per session with bonus words drawn from each target's `distractors` list.

## 1. New JSON schema

File: `kandy_core_vocab.json` at repo root. Generated from `kandy_core_vocab.xlsx`. Checked into git.

```json
{
  "version": 1,
  "words": [
    {
      "keyword": "japanese language",
      "word": "日本語",
      "kanji": ["日", "本", "語"],
      "hiragana": ["に", "ほ", "ん", "ご"],
      "distractors": ["every day", "japan", "tale", "tomorrow", "real"]
    }
  ]
}
```

### Field rules

- **`keyword`** — unique id across all 1309 entries. Comes from the xlsx `keyword` column.
- **`word`** — display form, may include trailing hiragana (e.g. `面白い`). Not unique across entries (18 homographic kanji forms map to 2 keywords each).
- **`kanji`** — array of individual kanji characters, one entry per character. Drops any trailing hiragana that appears in `word`. Duplicates inside one word are preserved (e.g. `日曜日` → `["日", "曜", "日"]`).
- **`hiragana`** — array of kana units (can include digraphs like `きょ`). Matches the xlsx `hiragana` column, comma-split.
- **`distractors`** — array of keyword ids (not kanji forms). Resolved from the xlsx `distractors` column (which stores kanji forms, comma-separated). Empty array when the xlsx had no distractors for that row (~33% of rows).

### Homographic resolution

18 kanji forms in the xlsx appear twice with different keywords (e.g., `方` → `direction (side)` and `person (polite form)`). When a distractor token references one of these kanji forms, we cannot know which keyword the author intended.

**Rule**: pick the **first-row occurrence** by xlsx order. Deterministic, arbitrary but consistent across builds.

### Build script

`scripts/build_vocab_json.py` — new file.

- Reads `kandy_core_vocab.xlsx` with `openpyxl`.
- Emits `kandy_core_vocab.json` at repo root.
- Deterministic output (follows xlsx row order).
- Validates: every distractor token resolves to a known kanji form. Fails loudly on unresolved tokens (xlsx typo indicator).
- Re-runnable; overwrites the JSON.

## 2. Session model

### At app load

- Fetch `kandy_core_vocab.json` once.
- Build an index keyed by `keyword` for O(1) lookup.

### At session start (also on restart)

1. **Pick 25 targets** — uniform random sample from all 1309 words, without replacement.
2. **Resolve bonus words** — union of every target's `distractors`, excluding any keyword that is itself a target.
3. **Pad bonus to minimum 25** — if the resolved bonus set has fewer than 25 unique words, add random entries from the dataset (excluding targets and already-selected bonuses) until the count reaches 25. No upper cap.
4. **Session kanji pool** — unique union of `kanji[]` across all session words (targets + bonuses).

### Per-session state (replaces old target-flag logic)

- `targets: Set<word>` — the 25 targets.
- `bonuses: Set<word>` — all bonus words (≥25).
- `allWords` — derived `[...targets, ...bonuses]`.
- `pendingTargets: word[]` — targets not yet cleared.
- `extraFound: Set<word>` — bonus words answered correctly.
- `mastery`, `revealedWords`, `masteryExemptIds` — same semantics as today, scoped to the 25 targets.
- `blockedTargets: Map<word, number>` — cooldown counters (see §3).

The old `target: true/false` JSON field is gone. Session membership (target vs. bonus) is determined by set lookup.

## 3. Grid build

Same focus-word + greedy-pack logic as today, but retargeted:

1. **Focus word** — random choice from `pendingTargets.filter(w => (blockedTargets.get(w) ?? 0) === 0)`. If that filter yields nothing (all pending blocked, or only 1 pending and it's blocked), fall back to unfiltered `pendingTargets`. Add focus word's `kanji[]` to the grid set.
2. **Greedy pack** — iterate shuffled (pending targets, then bonuses, then cleared targets) and add each word's `kanji[]` to the grid if it fits within the 25-cell budget. Respect each word's internal kanji duplicates (e.g. `日曜日` takes two `日` slots).
3. **Fill remaining slots** — random kanji from the session pool not already placed.
4. **Compute `formableWords`** — all session words whose kanji multiset is a sub-multiset of the grid's kanji multiset. (Multiset, not set: `日曜日` is formable only when the grid has two `日`.)
5. **Render.**

### Cooldown

All three events trigger a full rebuild: correct answer, wrong answer, hint reveal. (The current `shuffle(state.gridKanji)` path on wrong/hint is removed — that was a bug.)

- Wrong answer on a target → `blockedTargets.set(word, 3)` before the rebuild.
- Hint on a target → `blockedTargets.set(word, 3)` before the rebuild.
- Bonus words do not trigger blocks.
- After each rebuild, decrement every entry in `blockedTargets`. Remove entries that reach 0.
- A repeat mistake on the same word refreshes its cooldown to 3.

Edge cases:
- Only 1 pending target remaining and it's blocked → focus-word selection ignores the block.
- All pending targets blocked → focus-word selection ignores all blocks for this rebuild.
- Cooldown counters persist across rebuilds but not across session restarts.

## 4. Match logic

`matchWord(query)` receives the concatenated kanji string of the user's selection.

Preference order:
1. Pending target whose `kanji.join('')` matches `query`.
2. Any session word (bonus, cleared target) whose `kanji.join('')` matches `query`.
3. No match → toast.

If multiple candidates tie at the same preference tier, pick at random. (Handles the 18 homographic pairs where both entries could be in the session.)

## 5. Files changed

- ➕ `kandy_core_vocab.json` — generated, committed.
- ➕ `scripts/build_vocab_json.py` — new build script.
- 🔧 `index.html` — fetch path, session builder, grid logic, cooldown state.
- 🗑️ `group1.json` — deleted.

Not touched: `build_spec.md`, `for_the_future.txt`. `README.md` gets a run-instruction refresh if the fetch URL changes from `./group1.json` to `./kandy_core_vocab.json`.

## 6. Acceptance checks (manual)

**JSON generation**
- Output has exactly 1309 entries.
- Every `keyword` is unique.
- Every distractor keyword resolves to an entry in the same file.
- `面白い` → `kanji: ["面","白"]`, `hiragana: ["お","も","し","ろ","い"]`.
- `日曜日` → `kanji: ["日","曜","日"]`.

**Session init**
- On first load, the word list shows 25 target English meanings.
- `state.allWords.length >= 50`.
- No keyword is simultaneously a target and a bonus.

**Grid build**
- At least one pending target is formable from the current grid.
- No duplicate kanji in the grid except when justified by a session word that repeats a kanji internally.
- Successive reshuffles (via correct answers) change which words are formable.

**Cooldown**
- Wrong answer on target X → grid rebuilds → X's kanji not forced for the next 3 rebuilds. 4th rebuild, X may return as focus.
- Hint on target X → same behavior.
- Session with 1 pending target → cooldown ignored, the word remains focusable.

**Extras counter**
- `extra-found` / `extra-total` counts reflect the session's bonus-word set, not the old all-non-targets count.

## 7. Non-goals

- Small-tsu (`っ`) handling — already works; current code includes it in `HIRAGANA_POOL`.
- Progress persistence across reloads — out of scope.
- Group/category selection UI — out of scope. Session picks from all 1309.
- SRS / mastery across sessions — out of scope; mastery resets each session.
- xlsx `blocked_hiragana` column — currently empty in the source, ignored.

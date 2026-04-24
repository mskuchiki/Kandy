# Vocab Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the app from the 53-word `group1.json` to the 1309-word `kandy_core_vocab.xlsx` dataset; rework session bootstrap to pick 25 random targets + bonus words from their distractors; add a 3-reshuffle cooldown on wrong/hint target words.

**Architecture:** A one-off Python build script converts the xlsx to `kandy_core_vocab.json` (committed). `index.html` swaps the fetch target, adds a session builder that picks targets/bonuses, and rewrites grid logic to work over a session kanji pool instead of a static pool. Cooldown state is added to the browser state.

**Tech Stack:** Python 3 + openpyxl (build script, one-off). Vanilla JS (browser app). No test framework — manual verification matches existing project style.

**Spec:** [docs/superpowers/specs/2026-04-24-vocab-migration-design.md](../specs/2026-04-24-vocab-migration-design.md)

---

## File structure

- ➕ `scripts/build_vocab_json.py` — one-off build script. Reads xlsx, validates, writes JSON.
- ➕ `kandy_core_vocab.json` — generated output, committed.
- 🔧 `index.html` — fetch path, session builder, grid build, cooldown.
- 🔧 `README.md` — update fetch filename in run instructions.
- 🗑️ `group1.json` — deleted after migration.

---

## Task 1: Build script — scaffold + JSON emission

**Files:**
- Create: `scripts/build_vocab_json.py`

- [ ] **Step 1: Create the build script**

```python
"""Build kandy_core_vocab.json from kandy_core_vocab.xlsx."""
import json
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
XLSX_PATH = ROOT / "kandy_core_vocab.xlsx"
JSON_PATH = ROOT / "kandy_core_vocab.json"


def read_rows():
    wb = load_workbook(XLSX_PATH, data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue
        keyword, word, kanji, hiragana, _blocked, distractors = row[:6]
        rows.append({
            "keyword": keyword,
            "word": word,
            "kanji_raw": kanji,
            "hiragana_raw": hiragana,
            "distractors_raw": distractors,
        })
    return rows


def split_csv(value):
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


def build():
    rows = read_rows()

    # Homographic resolution: first-row occurrence wins.
    # Map kanji-form (word column) -> keyword of first occurrence.
    word_to_keyword = {}
    for row in rows:
        if row["word"] not in word_to_keyword:
            word_to_keyword[row["word"]] = row["keyword"]

    # Build entries and resolve distractors.
    seen_keywords = set()
    entries = []
    unresolved = []
    for row in rows:
        kw = row["keyword"]
        if kw in seen_keywords:
            print(f"ERROR: duplicate keyword '{kw}'", file=sys.stderr)
            sys.exit(1)
        seen_keywords.add(kw)

        kanji_tokens = split_csv(row["kanji_raw"])
        hiragana_tokens = split_csv(row["hiragana_raw"])
        distractor_tokens = split_csv(row["distractors_raw"])

        resolved = []
        for d_kanji in distractor_tokens:
            target_kw = word_to_keyword.get(d_kanji)
            if target_kw is None:
                unresolved.append((kw, d_kanji))
                continue
            resolved.append(target_kw)

        entries.append({
            "keyword": kw,
            "word": row["word"],
            "kanji": kanji_tokens,
            "hiragana": hiragana_tokens,
            "distractors": resolved,
        })

    if unresolved:
        print(f"ERROR: {len(unresolved)} unresolved distractors:", file=sys.stderr)
        for kw, d in unresolved[:20]:
            print(f"  in '{kw}': '{d}'", file=sys.stderr)
        sys.exit(1)

    return {"version": 1, "words": entries}


def main():
    payload = build()
    with JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(payload['words'])} entries to {JSON_PATH.name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

Run (from repo root):
```bash
py -m pip install openpyxl --quiet
py scripts/build_vocab_json.py
```
Expected output: `Wrote 1309 entries to kandy_core_vocab.json`

If it fails with an unresolved-distractors error, the xlsx has a typo. Report to the user before proceeding; do NOT edit the source xlsx without approval.

- [ ] **Step 3: Spot-check the JSON output**

Run:
```bash
PYTHONIOENCODING=utf-8 py -c "
import json
data = json.load(open('kandy_core_vocab.json', encoding='utf-8'))
print('version:', data['version'])
print('count:', len(data['words']))
# Check a few specific entries
by_kw = {w['keyword']: w for w in data['words']}
print(by_kw['japanese language'])
# Find 面白い and 日曜日
for w in data['words']:
    if w['word'] == '面白い':
        print('面白い:', w)
    if w['word'] == '日曜日':
        print('日曜日:', w)
# Ensure no distractor references a missing keyword
kws = set(by_kw.keys())
orphans = [(w['keyword'], d) for w in data['words'] for d in w['distractors'] if d not in kws]
print('orphan distractors:', len(orphans))
"
```

Expected:
- `version: 1`
- `count: 1309`
- `japanese language` entry has `kanji: ["日","本","語"]`, `hiragana: ["に","ほ","ん","ご"]`, distractors are keyword strings.
- `面白い` entry has `kanji: ["面","白"]`, `hiragana: ["お","も","し","ろ","い"]`.
- `日曜日` entry has `kanji: ["日","曜","日"]`.
- `orphan distractors: 0`

- [ ] **Step 4: Commit**

```bash
git add scripts/build_vocab_json.py kandy_core_vocab.json
git commit -m "$(cat <<'EOF'
feat: add vocab build script and generated JSON

Reads kandy_core_vocab.xlsx, emits kandy_core_vocab.json with 1309
entries. Distractors resolved to keyword ids; first-row occurrence
wins for the 18 homographic kanji forms.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Replace data loader and session bootstrap in index.html

This task swaps the fetch target and rewrites the session bootstrap to handle the new schema. After this task, the app will NOT run correctly yet — later tasks finish the refactor. We commit at the end.

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Remove obsolete `stripHiragana` helper and update `shuffle` import area**

Replace the block at [index.html:451-460](index.html#L451-L460):

```js
    // ── Helpers ───────────────────────────────────────────────────────────────
    const stripHiragana = s => s.replace(/[぀-ゟ]/g, '');
    const shuffle = arr => {
      const a = [...arr];
      for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
      }
      return a;
    };
```

With:

```js
    // ── Helpers ───────────────────────────────────────────────────────────────
    const shuffle = arr => {
      const a = [...arr];
      for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
      }
      return a;
    };

    const sample = (arr, n) => shuffle(arr).slice(0, Math.min(n, arr.length));

    // Multiset subset check: every element of `needles` (with multiplicity)
    // must be present in `haystack`. Both are arrays of strings.
    function isSubMultiset(needles, haystack) {
      const counts = new Map();
      for (const ch of haystack) counts.set(ch, (counts.get(ch) ?? 0) + 1);
      for (const ch of needles) {
        const c = counts.get(ch) ?? 0;
        if (c === 0) return false;
        counts.set(ch, c - 1);
      }
      return true;
    }
```

- [ ] **Step 2: Update state object**

Replace the state block at [index.html:503-530](index.html#L503-L530):

```js
    // ── State ─────────────────────────────────────────────────────────────────
    const state = {
      // session
      allWords: [],
      kanjiPool: [],
      pendingTargets: [],
      answeredCount: 0,
      wrongCount: 0,
      startTime: null,
      // grid
      gridKanji: [],
      formableWords: [],
      // interaction
      mode: 'idle',   // 'idle' | 'selecting' | 'question' | 'feedback' | 'complete'
      selected: [],
      holdTimer: null,
      // question
      currentWord: null,
      tiles: [],
      kanaSelected: [],
      lastCorrect: null,
      isHint: false,
      mastery: new Map(),        // word → -1 (red) | 0 (fresh) | 1 (orange) | 2 (white-near-clear)
      masteryExemptIds: new Set(),
      revealedWords: new Set(),  // target words whose English text has been uncovered
      extraFound: new Set(),     // non-target words answered correctly
    };
```

With:

```js
    // ── State ─────────────────────────────────────────────────────────────────
    const state = {
      // dataset (loaded once, kept immutable)
      dataset: [],          // full JSON words array (1309)
      datasetByKeyword: new Map(),
      // session
      targets: new Set(),   // target word objects (25)
      bonuses: new Set(),   // bonus word objects (>=25)
      allWords: [],         // [...targets, ...bonuses]
      sessionKanjiPool: [], // unique kanji across all session words
      pendingTargets: [],
      answeredCount: 0,
      wrongCount: 0,
      startTime: null,
      // grid
      gridKanji: [],
      formableWords: [],
      // interaction
      mode: 'idle',
      selected: [],
      holdTimer: null,
      // question
      currentWord: null,
      tiles: [],
      kanaSelected: [],
      lastCorrect: null,
      isHint: false,
      mastery: new Map(),
      masteryExemptKeywords: new Set(),
      revealedWords: new Set(),
      extraFound: new Set(),
      blockedTargets: new Map(),  // target word -> remaining reshuffles
    };
```

- [ ] **Step 3: Replace `initSession` and remove `computeMasteryExemptIds`/`_stripped` references**

Replace [index.html:587-604](index.html#L587-L604) (the `initSession` block) with:

```js
    // ── Session init ──────────────────────────────────────────────────────────
    function initSession() {
      const dataset = state.dataset;
      // 1. Pick 25 random targets (without replacement)
      const targetList = sample(dataset, 25);
      const targetSet = new Set(targetList);

      // 2. Union of distractors, excluding any target
      const bonusSet = new Set();
      for (const t of targetList) {
        for (const kw of t.distractors) {
          const w = state.datasetByKeyword.get(kw);
          if (w && !targetSet.has(w)) bonusSet.add(w);
        }
      }

      // 3. Pad to >= 25 bonuses with random non-target, non-bonus words
      if (bonusSet.size < 25) {
        const pool = dataset.filter(w => !targetSet.has(w) && !bonusSet.has(w));
        const needed = 25 - bonusSet.size;
        for (const w of sample(pool, needed)) bonusSet.add(w);
      }

      state.targets       = targetSet;
      state.bonuses       = bonusSet;
      state.allWords      = [...targetSet, ...bonusSet];

      // 4. Session kanji pool: unique kanji union across all session words
      const poolSet = new Set();
      for (const w of state.allWords) {
        for (const ch of w.kanji) poolSet.add(ch);
      }
      state.sessionKanjiPool = [...poolSet];

      state.pendingTargets = [...targetList];
      state.answeredCount  = 0;
      state.wrongCount     = 0;
      state.startTime      = Date.now();
      state.mode           = 'idle';
      state.selected       = [];
      state.currentWord    = null;
      state.isHint         = false;
      state.mastery        = new Map();
      state.masteryExemptKeywords = computeMasteryExemptKeywords(state.allWords, targetSet);
      state.revealedWords  = new Set();
      state.extraFound     = new Set();
      state.blockedTargets = new Map();
      if (state.holdTimer !== null) { clearTimeout(state.holdTimer); state.holdTimer = null; }
      buildGridAndRender();
    }
```

Replace `computeMasteryExemptIds` at [index.html:681-693](index.html#L681-L693) with:

```js
    // A multi-kanji target is mastery-exempt when any single kanji in it is
    // also the complete kanji form of a non-target session word. A single-tap
    // on that kanji would match the non-target, making a clean streak
    // impossible for the target via tap alone.
    function computeMasteryExemptKeywords(allWords, targetSet) {
      const nonTargetSingleKanji = new Set(
        allWords
          .filter(w => !targetSet.has(w) && w.kanji.length === 1)
          .map(w => w.kanji[0])
      );
      const exempt = new Set();
      for (const w of allWords) {
        if (!targetSet.has(w) || w.kanji.length <= 1) continue;
        if (w.kanji.some(ch => nonTargetSingleKanji.has(ch))) exempt.add(w.keyword);
      }
      return exempt;
    }
```

- [ ] **Step 4: Replace grid build (`buildGrid`, `tryBuildGrid`)**

Replace [index.html:612-673](index.html#L612-L673) (the two grid-build functions) with:

```js
    // ── Grid build ────────────────────────────────────────────────────────────
    const GRID_SIZE = 25;

    function buildGrid() {
      let best = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        const result = tryBuildGrid();
        if (!best || result.formableWords.length > best.formableWords.length) best = result;
        if (best.formableWords.length >= 5) break;
      }
      state.gridKanji     = best.gridKanji;
      state.formableWords = best.formableWords;

      // Decrement cooldowns at the end of every rebuild.
      for (const [w, n] of state.blockedTargets) {
        if (n <= 1) state.blockedTargets.delete(w);
        else state.blockedTargets.set(w, n - 1);
      }
    }

    function tryBuildGrid() {
      const gridKanji = [];  // array (allows duplicates)
      const addKanji  = ch => { gridKanji.push(ch); };

      // 1. Focus word: prefer unblocked pending target; fall back to any
      //    pending target if all blocked (or only blocked target remaining).
      let focusCandidates = state.pendingTargets.filter(
        w => (state.blockedTargets.get(w) ?? 0) === 0
      );
      if (focusCandidates.length === 0) focusCandidates = state.pendingTargets;

      let focus = null;
      if (focusCandidates.length > 0) {
        focus = focusCandidates[Math.floor(Math.random() * focusCandidates.length)];
        if (focus.kanji.length <= GRID_SIZE) {
          for (const ch of focus.kanji) addKanji(ch);
        }
      }

      // 2. Greedy pack: pending targets first, then bonuses, then cleared targets.
      const clearedTargets = [...state.targets].filter(w => !state.pendingTargets.includes(w));
      const packOrder = [
        ...shuffle(state.pendingTargets.filter(w => w !== focus)),
        ...shuffle([...state.bonuses]),
        ...shuffle(clearedTargets),
      ];

      for (const w of packOrder) {
        if (gridKanji.length >= GRID_SIZE) break;
        if (w.kanji.length === 0) continue;
        // Extra kanji this word would need beyond what's already on the grid,
        // respecting the word's own internal multiplicity.
        const needed = countsNeededBeyond(w.kanji, gridKanji);
        if (needed.length === 0) continue;        // already fully formable
        if (gridKanji.length + needed.length <= GRID_SIZE) {
          for (const ch of needed) addKanji(ch);
        }
      }

      // 3. Fill remaining slots with random kanji from the session pool
      //    that aren't already at the slot count they'd need. Simpler: just
      //    pull random pool kanji that don't already appear on the grid.
      if (gridKanji.length < GRID_SIZE) {
        const onGrid = new Set(gridKanji);
        const fill = shuffle(state.sessionKanjiPool.filter(ch => !onGrid.has(ch)));
        for (const ch of fill) {
          if (gridKanji.length >= GRID_SIZE) break;
          addKanji(ch);
        }
      }

      if (gridKanji.length < GRID_SIZE) console.warn('Grid: could not fill 25 kanji');

      const shuffled = shuffle(gridKanji).slice(0, GRID_SIZE);

      // 4. Compute formable words (multiset subset check against the grid)
      const formableWords = state.allWords.filter(
        w => w.kanji.length > 0 && isSubMultiset(w.kanji, shuffled)
      );

      return { gridKanji: shuffled, formableWords };
    }

    // Returns the extra characters `needles` would add to `haystack` to
    // be a sub-multiset. Empty array if already a sub-multiset.
    function countsNeededBeyond(needles, haystack) {
      const available = new Map();
      for (const ch of haystack) available.set(ch, (available.get(ch) ?? 0) + 1);
      const needed = [];
      for (const ch of needles) {
        const c = available.get(ch) ?? 0;
        if (c > 0) available.set(ch, c - 1);
        else needed.push(ch);
      }
      return needed;
    }
```

- [ ] **Step 5: Update `renderWordList` to iterate session targets**

Replace [index.html:696-717](index.html#L696-L717) with:

```js
    function renderWordList() {
      wordListEl.innerHTML = '';
      for (const w of state.targets) {
        const div = document.createElement('div');
        const pending  = state.pendingTargets.includes(w);
        const formable = pending && state.formableWords.some(fw => fw === w);
        const m        = pending ? (state.mastery.get(w) ?? 0) : null;
        const revealed = !pending || state.revealedWords.has(w);
        let cls = 'word-item ' + (pending ? 'pending' : 'cleared');
        if (formable) cls += ' formable';
        if (m === -1) cls += ' mastery-red';
        else if (m === 1) cls += ' mastery-orange';
        if (!revealed) cls += ' hidden';
        div.className = cls;
        const span = document.createElement('span');
        span.className   = 'word-text';
        span.textContent = w.keyword;
        div.appendChild(span);
        if (pending) div.addEventListener('click', () => showHint(w));
        wordListEl.appendChild(div);
      }
    }
```

- [ ] **Step 6: Update `renderExtraCounter`, `renderGrid` single-kanji status, `matchWord`**

Replace `renderExtraCounter` at [index.html:729-733](index.html#L729-L733) with:

```js
    function renderExtraCounter() {
      $('extra-found').textContent = state.extraFound.size;
      $('extra-total').textContent = state.bonuses.size;
    }
```

In `renderGrid` at [index.html:735-804](index.html#L735-L804), replace the single-kanji-status block [index.html:742-755](index.html#L742-L755) with:

```js
      // Build single-kanji word status: 'present' (blue) or 'found' (green)
      const singleKanjiStatus = new Map();
      for (const w of state.allWords) {
        if (w.kanji.length !== 1) continue;
        const ch = w.kanji[0];
        if (!state.gridKanji.includes(ch)) continue;
        const isFound = state.targets.has(w)
          ? !state.pendingTargets.includes(w)
          : state.extraFound.has(w);
        const cur = singleKanjiStatus.get(ch);
        if (!cur || (isFound && cur !== 'found')) {
          singleKanjiStatus.set(ch, isFound ? 'found' : 'present');
        }
      }
```

Replace `matchWord` at [index.html:831-840](index.html#L831-L840) with:

```js
    function matchWord(query) {
      const matches = state.allWords.filter(w => w.kanji.join('') === query);
      if (matches.length === 0) return null;
      if (matches.length === 1) return matches[0];

      // Multiple matches: prefer uncleared pending targets
      const pending = matches.filter(w => state.pendingTargets.includes(w));
      if (pending.length > 0) return pending[Math.floor(Math.random() * pending.length)];
      return matches[Math.floor(Math.random() * matches.length)];
    }
```

- [ ] **Step 7: Update `handleAnswer` and `showHint` (cooldown + feedback uses `keyword`)**

Replace `handleAnswer` at [index.html:892-914](index.html#L892-L914) with:

```js
    function handleAnswer(isCorrect) {
      state.answeredCount++;
      if (!isCorrect) state.wrongCount++;
      state.lastCorrect = isCorrect;

      const w = state.currentWord;
      const isTarget = state.targets.has(w);

      if (isTarget) {
        if (isCorrect) {
          state.revealedWords.add(w);
          const m = state.mastery.get(w) ?? 0;
          if (m === 0 || m >= 2) {
            state.pendingTargets = state.pendingTargets.filter(x => x !== w);
          } else {
            state.mastery.set(w, m === -1 ? 1 : m + 1);
          }
        } else {
          if (!state.masteryExemptKeywords.has(w.keyword)) state.mastery.set(w, -1);
          state.blockedTargets.set(w, 3);
        }
      } else if (isCorrect) {
        state.extraFound.add(w);
      }

      showFeedback(isCorrect);
    }
```

Replace `showFeedback`'s reading line at [index.html:923](index.html#L923):

```js
      feedbackReading.textContent = state.currentWord.reading.join('');
```

With:

```js
      feedbackReading.textContent = state.currentWord.hiragana.join('');
```

And `feedbackMeaning`:

```js
      feedbackMeaning.textContent = state.currentWord.meaning;
```

With:

```js
      feedbackMeaning.textContent = state.currentWord.keyword;
```

Replace `showHint` at [index.html:932-946](index.html#L932-L946) with:

```js
    function showHint(word) {
      if (state.mode !== 'idle') return;
      if (!state.masteryExemptKeywords.has(word.keyword)) state.mastery.set(word, -1);
      state.revealedWords.add(word);
      state.blockedTargets.set(word, 3);
      state.currentWord = word;
      state.mode        = 'feedback';
      state.isHint      = true;

      feedbackOverlay.classList.remove('correct', 'wrong', 'hint');
      feedbackOverlay.classList.add('correct', 'hint', 'visible');

      feedbackIcon.textContent    = word.word;
      feedbackReading.textContent = word.hiragana.join('');
      feedbackMeaning.textContent = word.keyword;
    }
```

(Note `word.word` is the display kanji form — replaces `word.kanji` which is now an array.)

Also update `showQuestion`'s modal-word line at [index.html:856](index.html#L856):

```js
      modalWord.textContent = word.kanji;
```

With:

```js
      modalWord.textContent = word.word;
```

And `handleKanaTap` at [index.html:880-882](index.html#L880-L882):

```js
      if (state.kanaSelected.length === state.currentWord.reading.length) {
        const submitted = state.kanaSelected.map(i => state.tiles[i]);
        const isCorrect = submitted.every((k, i) => k === state.currentWord.reading[i]);
```

With:

```js
      if (state.kanaSelected.length === state.currentWord.hiragana.length) {
        const submitted = state.kanaSelected.map(i => state.tiles[i]);
        const isCorrect = submitted.every((k, i) => k === state.currentWord.hiragana[i]);
```

And `generateTiles` at [index.html:491-501](index.html#L491-L501):

```js
    function generateTiles(word) {
      const answer = word.reading;
```

With:

```js
    function generateTiles(word) {
      const answer = word.hiragana;
```

- [ ] **Step 8: Rewrite `dismissFeedback` — full rebuild on every event**

Replace [index.html:948-965](index.html#L948-L965) with:

```js
    function dismissFeedback() {
      if (!feedbackOverlay.classList.contains('visible')) return;
      feedbackOverlay.classList.remove('visible', 'correct', 'wrong', 'hint');

      if (state.pendingTargets.length === 0) {
        showComplete();
        return;
      }

      state.mode   = 'idle';
      state.isHint = false;
      buildGridAndRender();
    }
```

- [ ] **Step 9: Update `showComplete` (target count = 25)**

Replace the stats block at [index.html:971-983](index.html#L971-L983) with:

```js
      const total   = state.targets.size;
      const elapsed = Math.floor((Date.now() - state.startTime) / 1000);
      const mins    = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const secs    = String(elapsed % 60).padStart(2, '0');
      const accuracy = state.answeredCount > 0
        ? Math.round(((state.answeredCount - state.wrongCount) / state.answeredCount) * 100)
        : 100;

      const cleared = total - state.pendingTargets.length;
      $('stat-cleared').textContent  = `Words cleared: ${cleared} / ${total}`;
      $('stat-attempts').textContent = `Total attempts: ${state.answeredCount}`;
      $('stat-accuracy').textContent = `Accuracy: ${accuracy}%`;
      $('stat-time').textContent     = `Time: ${mins}:${secs}`;
```

- [ ] **Step 10: Update restart handler**

Replace [index.html:581-584](index.html#L581-L584):

```js
    $('btn-restart').addEventListener('click', () => {
      completeScreen.classList.remove('visible');
      initSession(state.allWords, state.kanjiPool);
    });
```

With:

```js
    $('btn-restart').addEventListener('click', () => {
      completeScreen.classList.remove('visible');
      initSession();
    });
```

- [ ] **Step 11: Update reveal-button handler**

Replace [index.html:568-579](index.html#L568-L579):

```js
    $('btn-reveal').addEventListener('click', () => {
      const candidates = state.formableWords.filter(w =>
        w.target && state.pendingTargets.includes(w) && !state.revealedWords.has(w)
      );
      if (candidates.length === 0) {
        showToast('All visible words already revealed');
        return;
      }
      const word = candidates[Math.floor(Math.random() * candidates.length)];
      state.revealedWords.add(word);
      renderWordList();
    });
```

With:

```js
    $('btn-reveal').addEventListener('click', () => {
      const candidates = state.formableWords.filter(w =>
        state.targets.has(w) && state.pendingTargets.includes(w) && !state.revealedWords.has(w)
      );
      if (candidates.length === 0) {
        showToast('All visible words already revealed');
        return;
      }
      const word = candidates[Math.floor(Math.random() * candidates.length)];
      state.revealedWords.add(word);
      renderWordList();
    });
```

- [ ] **Step 12: Update boot code**

Replace [index.html:986-997](index.html#L986-L997):

```js
    // ── Boot ─────────────────────────────────────────────────────────────────
    // Integration-verified: all five flows (single-tap, multi-select, session
    // complete, no-match, cancel) and all eight specific checks pass.
    const data = await fetch('./group1.json').then(r => {
      if (!r.ok) throw new Error(`Failed to load data: ${r.status}`);
      return r.json();
    }).catch(err => {
      document.body.innerHTML = `<p style="padding:24px;font-family:sans-serif;color:#c62828;">Could not load group1.json. Serve this file over HTTP (e.g. python3 -m http.server).<br><small>${err.message}</small></p>`;
      throw err;
    });
    data.words.forEach(w => { w._stripped = stripHiragana(w.kanji); });
    initSession(data.words, data.kanji_pool);
```

With:

```js
    // ── Boot ─────────────────────────────────────────────────────────────────
    const data = await fetch('./kandy_core_vocab.json').then(r => {
      if (!r.ok) throw new Error(`Failed to load data: ${r.status}`);
      return r.json();
    }).catch(err => {
      document.body.innerHTML = `<p style="padding:24px;font-family:sans-serif;color:#c62828;">Could not load kandy_core_vocab.json. Serve this file over HTTP (e.g. python3 -m http.server).<br><small>${err.message}</small></p>`;
      throw err;
    });
    state.dataset = data.words;
    state.datasetByKeyword = new Map(data.words.map(w => [w.keyword, w]));
    initSession();
```

- [ ] **Step 13: Smoke-test in the browser**

Run from repo root:
```bash
py -m http.server 8000
```

Open `http://localhost:8000` in a browser. Verify:
- No console errors.
- Word list shows 25 English keywords (targets).
- Grid shows 25 kanji cells.
- At least one word in the list has the `formable` underline style.
- Tapping a single-cell target (e.g., if `本` shows in the grid and `book` is a target) opens the question modal.
- Correct answer triggers a full grid rebuild (different kanji set than before).
- Wrong answer also triggers a full grid rebuild (was previously only a reorder).

Stop the server (Ctrl+C) after verification.

- [ ] **Step 14: Commit**

```bash
git add index.html
git commit -m "$(cat <<'EOF'
feat: migrate app to kandy_core_vocab.json dataset

Session picks 25 random targets and resolves bonus words from each
target's distractors (padded to >=25). Grid build works over a
session kanji pool. Full rebuild on every answer event (correct,
wrong, hint). Adds 3-reshuffle cooldown for wrong/hint target words.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Integration verification against spec §6

**Files:**
- None modified.

- [ ] **Step 1: Run acceptance checks from the spec**

Start a server: `py -m http.server 8000`, open the app.

For each check, verify manually. Use the browser console to inspect state (`state.targets`, `state.bonuses`, `state.blockedTargets`, etc.).

**Session init checks:**
- Word list displays 25 target English meanings.
- In console: `state.allWords.length >= 50`.
- In console: no keyword appears in both `targets` and `bonuses` sets:
  ```js
  const t = new Set([...state.targets].map(w => w.keyword));
  const b = new Set([...state.bonuses].map(w => w.keyword));
  [...t].every(k => !b.has(k))  // should be true
  ```

**Grid build checks:**
- At least one pending target's keyword appears in `state.formableWords.map(w => w.keyword).filter(k => [...state.targets].some(t => t.keyword === k && state.pendingTargets.includes(t)))`.
- In the grid DOM: no duplicate kanji except when justified by a session word with internal duplication. Verify by hand once with 日曜日 if it shows up.
- Answer several targets correctly. Confirm the kanji set changes across reshuffles (at least 3 distinct kanji should rotate in/out across 3 consecutive rebuilds).

**Cooldown checks:**
- Get a target X wrong. Immediately after, observe grid rebuild.
- Inspect: `state.blockedTargets.get(<X-word-obj>)` shows a value between 1-3.
- Trigger 2 more rebuilds (answer 2 more words correctly). X should still be absent as focus; cooldown counter decrements.
- On the 4th rebuild after the mistake, X may return as focus (no guarantee, just eligible).
- Repeat with a hint: click a word in the list → hint appears → dismiss → grid rebuilds → `state.blockedTargets.get(<word>)` is set.

**Last-target edge case:**
- Clear 24 of 25 targets. Get the last one wrong. Confirm the grid rebuild still places the last target as focus (cooldown is ignored).

**Extras counter:**
- Correctly answer a bonus word. `extra-found` increments by 1. `extra-total` equals `state.bonuses.size`.

- [ ] **Step 2: Stop the server**

`Ctrl+C`.

- [ ] **Step 3: Update the "Integration-verified" comment in the boot block**

Edit the comment at the top of the boot block in [index.html](index.html) (just after `// ── Boot ──` line):

```js
    // ── Boot ─────────────────────────────────────────────────────────────────
    const data = await fetch('./kandy_core_vocab.json').then(r => {
```

to:

```js
    // ── Boot ─────────────────────────────────────────────────────────────────
    // Integration-verified: 1309-entry dataset; session picks 25 random targets
    // + bonus words from distractors (padded to >=25); full rebuild on every
    // answer/hint; 3-reshuffle cooldown for wrong/hint targets.
    const data = await fetch('./kandy_core_vocab.json').then(r => {
```

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "$(cat <<'EOF'
test: integration-verify vocab migration against spec

Manual verification against spec §6 acceptance criteria: session
init, grid build, cooldown, last-target edge case, extras counter.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Cleanup

**Files:**
- Delete: `group1.json`
- Modify: `README.md`

- [ ] **Step 1: Remove group1.json**

```bash
git rm group1.json
```

- [ ] **Step 2: Update README**

Read [README.md](README.md). If it references `group1.json` by name, replace with `kandy_core_vocab.json`. If it lists a run command (e.g. `python -m http.server`), keep it.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
chore: remove obsolete group1.json, refresh README

Migration to kandy_core_vocab.json is complete.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Known limitations / follow-ups

- **Word `日曜日` cannot be formed via selection today.** The grid build supports duplicating `日` in the grid, but the selection handler at [index.html:779](index.html#L779) dedupes by kanji string (`!state.selected.includes(kanji)`), so the user cannot pick the second `日` cell. This is a pre-existing limitation surfaced by the new dataset (only 1 word in 1309 has repeating kanji). Not fixed here — flag to the user for a separate task.

## Execution notes

- Tasks 1–4 are sequential; each depends on the previous one.
- Run the app in a browser after Task 2 — if the smoke test reveals bugs, fix in-place before committing.
- If an xlsx build-time validation fails (unresolved distractor), stop and report to the user before touching the xlsx.
- No test framework is added. Verification is manual per spec §6, matching the existing project style.

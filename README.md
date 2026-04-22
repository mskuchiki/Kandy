# Kanji Grid Study — Prototype

Tap kanji on a 5×5 grid to identify words. Complete all 25 target words to finish the session.

## Running

The app uses `fetch()` and **must be served over HTTP** — opening `index.html` directly as a `file://` URL will not work.

### Option A — Python (built-in, no install)

```bash
cd /path/to/Kandy
python3 -m http.server 8000
```

Open **http://localhost:8000** in your browser.

### Option B — Node.js

```bash
npx serve .
```

## How to play

- **Single tap** a kanji to submit it as a one-character word.
- **Hold** a kanji (~250ms) to enter multi-select mode. Tap additional kanji in order, then press **Confirm**.
- Pick the correct hiragana reading from the 4 options shown.
- Correct answers clear the word from the session. Wrong answers keep it in the queue.
- The session ends when all 25 target words are answered correctly.

## Files

| File | Description |
|------|-------------|
| `index.html` | Full app — HTML + CSS + JS, no build step |
| `group1.json` | Study data (Group 1, 25 target words) |

## Known limitations

- Must be served over HTTP (not `file://`)
- No cross-session persistence — refresh resets progress
- Only Group 1 is included

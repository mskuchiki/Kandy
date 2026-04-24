# Kanji Grid Study — Prototype

Tap kanji on a 5×5 grid to identify words. Each session picks 25 random target words from a 1309-word vocab list. Complete all 25 targets to finish the session.

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

## Install as a PWA

The app ships a web manifest and a service worker, so it's installable
and works offline after the first load.

- **Desktop Chrome / Edge:** click the install icon in the address bar.
- **Android Chrome:** menu → *Install app*.
- **iOS Safari:** Share → *Add to Home Screen*.

Regenerate the placeholder icons with `py scripts/build_icons.py`.

## Files

| File | Description |
|------|-------------|
| `index.html` | Full app — HTML + CSS + JS, no build step |
| `manifest.webmanifest` | PWA manifest (name, icons, theme colour) |
| `sw.js` | Service worker — caches the app shell for offline use |
| `icons/` | PWA icons (192, 512, maskable 512) |
| `kandy_core_vocab.json` | Vocab dataset (1309 words), generated from the xlsx |
| `kandy_core_vocab.xlsx` | Source spreadsheet for the dataset |
| `scripts/build_vocab_json.py` | Regenerates the JSON from the xlsx |
| `scripts/build_icons.py` | Regenerates the PWA icons |

## Known limitations

- Must be served over HTTP (not `file://`)
- No cross-session persistence — refresh resets progress

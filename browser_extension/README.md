# Aunoo Research Chrome Extension

Send any webpage or link to your Aunoo backend for AI analysis, review the
result in a heads-up panel, tweak the metadata, then save it—all without
leaving the page.

---

## Features

| Feature | Description |
|---------|-------------|
| Context-menu action | Right-click a page or link → **"Analyze with Aunoo"** |
| Instant HUD | A popup opens immediately with a loading spinner while the analysis runs |
| Editable fields | Title, sentiment, summary, explanations, category, future-signal, driver-type, time-to-impact, topic |
| Live dropdowns | Values are fetched from your Aunoo API (`/api/...`) for consistency |
| Settings page | Configure API base URL, default topic, summary length, summary voice |
| Sync storage | Settings roam across Chrome profiles signed into the same account |

---

## Installation (developer mode)

1. **Clone** this repo or copy the `browser_extension/` folder.
2. Open Chrome and navigate to `chrome://extensions`.
3. Enable **Developer mode** (top-right toggle).
4. Click **Load unpacked** and select the `browser_extension` folder.
5. An Aunoo icon will appear in the toolbar.

To update the extension after edits, click the **reload arrow** on the card or
press <kbd>Ctrl/Cmd-R</kbd> while the extension page is focused.

### Packaging a ZIP for Web Store

```bash
zip -r aunoo_extension.zip browser_extension/*
```
Upload the ZIP to the Chrome Web Store dashboard.

---

## Configuration

1. Right-click the Aunoo icon → **Options** (or **Manage extension → Extension options**).
2. **API Base URL** – root of your Aunoo backend (`https://app.aunoo.ai`, `http://localhost:10000`, …).
3. **Default Topic** – used when you haven't selected another topic in the HUD.
4. **Summary Length** – target word count (default **50**).
5. **Summary Voice** – stylistic tone (default **Business Analyst**).

The settings are stored in `chrome.storage.sync`, so they sync across devices
signed into the same Chrome profile.

---

## Usage

1. On any webpage or link, **right-click → Analyze with Aunoo**.
2. A HUD pops up:
   * Shows a spinner while the analysis is being generated.
   * Auto-refreshes into an editable form once results arrive.
3. Adjust any field (e.g., tweak the summary, pick a different sentiment).
4. Click **Save to Aunoo** to POST `/api/save-bulk-articles`.
5. A toast "Saved ✔" confirms success.

---

## File Structure

```
browser_extension/
├── background.js    # Service-worker: context-menu, API calls
├── manifest.json    # Chrome Manifest V3
├── options.html     # Settings UI
├── options.js       # Settings logic (sync storage)
├── popup.html       # HUD layout & styling
├── popup.js         # HUD logic (spinner, fetch, save)
├── icon128.png      # Toolbar & Web Store icon (add your own)
└── README.md        # This file
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| HUD closes instantly | Make sure the current window is focused; background.js handles this automatically in the latest version. |
| Spinner never ends | Check DevTools → **Console** for network errors; ensure your backend allows CORS for `chrome-extension://*`. |
| `[object Object]` in dropdowns | You're running an older build—upgrade to latest commit where label parsing is fixed. |

---

## License

MIT © Aunoo AI 
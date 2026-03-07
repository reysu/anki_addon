# Universal Furigana — Anki Add-on

Converts `word{annotation}` syntax into ruby text on **any card, any field** — no template editing required. Works on Anki Desktop, AnkiDroid, and AnkiMobile.

Includes **pitch accent visualization** with colored lines above mora showing exactly where the pitch drops.

## Install

**Option A** — From file:
1. Download `universal_furigana.ankiaddon` from this repo
2. In Anki: **Tools → Add-ons → Install from file...** → select the file
3. Restart Anki

**Option B** — Manual:
Copy `__init__.py`, `config.json`, and `manifest.json` into your Anki add-ons folder:
- macOS: `~/Library/Application Support/Anki2/addons21/universal_furigana/`
- Windows: `%APPDATA%\Anki2\addons21\universal_furigana\`
- Linux: `~/.local/share/Anki2/addons21/universal_furigana/`

## Furigana Syntax

Type annotations directly in your card fields:

| You type | Result |
|---|---|
| `食べる{たべる}` | たべる above 食べる |
| `食べる{to eat}` | "to eat" above 食べる |
| `食{た}べる` | furigana on 食 only |

**Rules:**
- Base word must be **directly followed** by `{annotation}` (no space between)
- A **space** before the base word acts as the word boundary

## Pitch Accent

Add a pitch type code after a semicolon:

| Code | Type | Color | Example |
|---|---|---|---|
| `;h` | Heiban (flat) | Blue | `学生{がくせい;h}` |
| `;a` | Atamadaka (head-high) | Red | `秋{あき;a}` |
| `;nX` | Nakadaka (drop after Xth mora) | Orange | `心{こころ;n2}` |
| `;o` | Odaka (tail-high) | Green | `花{はな;o}` |

### How the lines work
- A **horizontal line** above the mora marks high pitch
- A short **vertical tick** marks where the pitch drops
- **Heiban**: flat line, no drop (stays high through particles)
- **Atamadaka**: line on 1st mora, drops after
- **Nakadaka**: line from 2nd mora, drops at specified position
- **Odaka**: flat line, drops after the last mora (onto particle)

Colors are customizable in **Tools → Universal Furigana Settings...**

## Settings

Access via **Tools → Universal Furigana Settings...** in Anki. You can:
- Enable/disable the add-on
- Enable/disable pitch accent visualization
- Customize colors for each pitch accent type
- Restore defaults

## How it works

The add-on uses Anki's `card_will_show` hook to inject a small JavaScript snippet at render time. The JS walks DOM text nodes and converts `{annotation}` syntax into HTML `<ruby>` tags. This means:

- Works on all note types and fields automatically
- Doesn't modify your card templates
- Doesn't modify stored card data
- If you uninstall, cards just show the raw `{text}` — nothing is corrupted

## Author

Eric Su — [@reysu](https://github.com/reysu)

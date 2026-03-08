# Universal Furigana for Anki

A modern Anki add-on that converts `{annotation}` syntax into furigana, pitch accent visualization, and info tooltips — on any card, any field.

Works on **Anki Desktop**, **AnkiDroid**, and **AnkiMobile (iOS)**

---
## Use cases 
- You can use this addon to instantly visualize the pitch accent.
  <img width="587" height="99" alt="image" src="https://github.com/user-attachments/assets/b923206b-5321-4aae-b234-4ffa1dc148a2" />
- If you are making monolingual sentence cards, you can add a short definition in your native language so you can hover over.
  <img width="182" height="110" alt="image" src="https://github.com/user-attachments/assets/3514561c-6d43-498d-961d-8cbc6fae0807" />
- This also works for longer definitions, so you can have definitions in definitions or evens descriptions (pagination supported). 
<img width="359" height="144" alt="image" src="https://github.com/user-attachments/assets/fa16df42-7d27-4cd0-b46d-39803021a878" />

<img width="371" height="191" alt="image" src="https://github.com/user-attachments/assets/c0897cd9-882e-4ade-8bfe-eab9c2a20850" />

## Additional Features
- Add an english word as furigana 
<img width="864" height="71" alt="image" src="https://github.com/user-attachments/assets/92bdceb1-5346-4fda-8354-f1327fd9b087" />

- Hide Furigana and pitch accent until you hover
<img width="164" height="64" alt="image" src="https://github.com/user-attachments/assets/965647e9-2d4b-43de-8960-bed53652f9a9" />

- Add readings for other languages, such as bopomofo 
<img width="433" height="64" alt="image" src="https://github.com/user-attachments/assets/51284008-a0e0-4097-9080-4d6c7d01cd54" />

- Customize pitch accent readings and furigana size 
<img width="543" height="329" alt="image" src="https://github.com/user-attachments/assets/021ae043-6615-4001-bce8-b0baccb4c033" />


# How to use it 
## quick guide
Add a space before the word and add the information within the curly brackets. Each section is separated by semi-colons. 
`{<text to display on top>; <pitch accent type>; <information to show on over>}`

For example 
`学生{がくせい;h;to eat}` 
<img width="100" height="74" alt="image" src="https://github.com/user-attachments/assets/adb4ae48-9a6d-42ed-b439-c0ec236d9cf1" />

You can leave any of the sections blank 
`学生{;h;to eat}` 
<img width="101" height="64" alt="image" src="https://github.com/user-attachments/assets/05963e6d-4f59-4a35-a234-efe2c9a85f22" />

Or 
`学生{;;to eat}`
<img width="102" height="57" alt="image" src="https://github.com/user-attachments/assets/e4e8fed7-e062-4556-9cff-af79b5a9ad52" />

## pitch accent types

Add a pitch code after a semicolon to visualize Japanese pitch accent with colored lines:

| Code | Type | Color | Example |
|------|------|-------|---------|
| `h` | Heiban (flat) | Blue | `学生{がくせい;h}` |
| `a` | Atamadaka (head-high) | Red | `秋{あき;a}` |
| `nX` | Nakadaka (drop after X) | Orange | `心{こころ;n2}` |
| `o` | Odaka (tail-high) | Green | `花{はな;o}` |

![Pitch Accent](screenshots/02_pitch_accent.png)

A **top line** marks high-pitch mora. A **vertical tick** marks where the pitch drops. The pattern is always visible — no hover needed.

## pitch-only Mode
Use just the pitch code without a reading — the lines are drawn directly on the base word:
```
ぷっつり{h}    ぷっつり{a}    ぷっつり{n3}    ぷっつり{o}
```

![Pitch Only](screenshots/05_pitch_only.png)

## info Tooltips

Add a description as the last semicolon segment. It appears as a hover tooltip (desktop) or tap tooltip (mobile):

```
気前{きまえ;h;generosity}       ← reading + pitch + tooltip
食べる{たべる;;to eat}          ← reading + tooltip (no pitch)
ぷっつり{n3;snapping}           ← pitch-only + tooltip
```

![Tooltip](screenshots/04_tooltip.png)

A small ℹ indicator appears next to words that have a tooltip. Hover on desktop, tap on mobile. Tap elsewhere to dismiss.

## Examples

| You Type | Result |
|----------|--------|
| `食べる{たべる}` | Furigana reading above word |
| `食べる{to eat}` | English text above word |
| `学生{がくせい;h}` | Reading + heiban pitch (blue) |
| `秋{あき;a}` | Reading + atamadaka pitch (red) |
| `心{こころ;n2}` | Reading + nakadaka pitch (orange) |
| `花{はな;o}` | Reading + odaka pitch (green) |
| `ぷっつり{n3}` | Pitch-only (lines on base word) |
| `気前{きまえ;h;generosity}` | Reading + pitch + ℹ tooltip |
| `食べる{たべる;;to eat}` | Reading + ℹ tooltip (no pitch) |
| `ぷっつり{n3;snapping}` | Pitch-only + ℹ tooltip |

---

## Installation

### From .ankiaddon file

1. Download `universal_furigana.ankiaddon` from this repo
2. In Anki, go to **Tools → Add-ons → Install from file...**
3. Select the downloaded file and restart Anki

---

## Settings

Open **Tools → Universal Furigana Settings** to:

- Enable/disable the add-on
- Enable/disable pitch accent
- Customize pitch accent colors with a color picker
- Set up mobile compatibility (see below)

---

## Mobile Compatibility

The add-on works automatically on Anki Desktop. To make it work on **AnkiDroid** and **AnkiMobile (iOS)**:

1. Open **Tools → Universal Furigana Settings**
2. Scroll down to **Mobile Compatibility**
3. Check the card templates you want to enable (or click **Select All**)
4. Click **Save**
5. Sync your collection

The add-on injects the script directly into your card templates so it travels with your cards when you sync. If you change colors or settings, saving will update the injected code automatically.

---

## Uninstalling

If you uninstall the add-on:
- Your cards are **not** affected — the `{annotation}` text stays in your fields
- You'll just see the raw syntax like `食べる{たべる}` instead of rendered furigana
- To also remove injected mobile code: open settings, click **Deselect All**, then **Save** before uninstalling

---

## Author

**Eric Su** ([@reysu](https://github.com/reysu))

## License

MIT

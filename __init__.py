"""
Universal Furigana Add-on for Anki (v5)
========================================
Converts {annotation} syntax into ruby text on ANY card, ANY field.
Supports pitch accent visualization with colored lines above mora.
Info tooltips via hover (desktop) or tap (mobile).

Works on desktop (Anki 2.1.x) via card_will_show hook.
Works on mobile (AnkiDroid / AnkiMobile) via template injection.

Syntax:
  word{reading}          -> furigana reading above word
  word{reading;h}        -> heiban pitch accent (blue, flat line)
  word{reading;a}        -> atamadaka pitch accent (red, drop after 1st)
  word{reading;nX}       -> nakadaka pitch accent (orange, drop after Xth mora)
  word{reading;o}        -> odaka pitch accent (green, drop after last)
  word{pitch}            -> pitch-only (lines on base word, no ruby)
  word{reading;pitch;desc} -> reading + pitch + info tooltip
  word{pitch;desc}       -> pitch-only + info tooltip

Author: Eric Su (reysu)
"""

import json
import os
import re
from aqt import mw, gui_hooks
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QColorDialog, QGroupBox, QGridLayout,
    QFrame, Qt, QFont, QWidget, QScrollArea, QMessageBox,
    QDoubleSpinBox
)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "enabled": True,
    "pitch_accent_enabled": True,
    "color_heiban": "#3366CC",
    "color_atamadaka": "#CC3333",
    "color_nakadaka": "#DD8800",
    "color_odaka": "#339933",
    "line_thickness": 2,
    "furigana_font_size": 0.6,  # em units, relative to base text
    "injected_templates": [],  # list of "NoteType::CardName::side" entries
}


def _get_config():
    cfg = mw.addonManager.getConfig(__name__) or {}
    merged = dict(_DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def _save_config(cfg):
    mw.addonManager.writeConfig(__name__, cfg)


# ---------------------------------------------------------------------------
# Injection markers — used to find/replace our code block in templates
# ---------------------------------------------------------------------------

_MARKER_START = "<!-- UF-START -->"
_MARKER_END = "<!-- UF-END -->"


# ---------------------------------------------------------------------------
# JavaScript + CSS injected into every card
# ---------------------------------------------------------------------------

_SCRIPT_TEMPLATE = r"""
<script>
(function() {
    var PITCH_ENABLED = %%PITCH_ENABLED%%;
    var COLORS = %%COLORS%%;
    var LINE_PX = %%LINE_PX%%;
    var RT_FONT_SIZE = '%%RT_FONT_SIZE%%';

    // ---- Mora splitter ----
    function splitMora(kana) {
        var digraphs = '\u3083\u3085\u3087\u30e3\u30e5\u30e7\u30a1\u30a3\u30a5\u30a7\u30a9';
        var mora = [];
        for (var i = 0; i < kana.length; i++) {
            var ch = kana[i];
            if (i + 1 < kana.length && digraphs.indexOf(kana[i + 1]) !== -1) {
                mora.push(ch + kana[i + 1]);
                i++;
            } else {
                mora.push(ch);
            }
        }
        return mora;
    }

    // ---- Pitch pattern generator ----
    function getPitchPattern(moraCount, type, dropAt) {
        var pattern = [];
        if (type === 'h') {
            pattern.push(0);
            for (var i = 1; i < moraCount; i++) pattern.push(1);
        } else if (type === 'a') {
            pattern.push(1);
            for (var i = 1; i < moraCount; i++) pattern.push(0);
        } else if (type === 'o') {
            pattern.push(0);
            for (var i = 1; i < moraCount; i++) pattern.push(1);
        } else if (type === 'n') {
            pattern.push(0);
            for (var i = 1; i < moraCount; i++) {
                pattern.push(i < dropAt ? 1 : 0);
            }
        }
        return pattern;
    }

    // ---- Build pitch HTML ----
    function buildPitchHTML(reading, type, dropAt, color) {
        var mora = splitMora(reading);
        var moraCount = mora.length;
        var pattern = getPitchPattern(moraCount, type, dropAt);
        var html = '<span class="uf-pitch-word" style="display:inline-flex;align-items:flex-end;">';

        for (var i = 0; i < mora.length; i++) {
            var isHigh = pattern[i] === 1;
            var nextLow = (i + 1 < mora.length) ? pattern[i + 1] === 0 : false;

            var bTop = isHigh ? (LINE_PX + 'px solid ' + color) : 'none';

            var hasDrop = false;
            if (type === 'a' && i === 0) hasDrop = true;
            else if (type === 'n' && isHigh && nextLow) hasDrop = true;
            else if (type === 'o' && i === mora.length - 1) hasDrop = true;

            var style = 'display:inline-block;position:relative;'
                + 'padding-top:' + (LINE_PX + 2) + 'px;'
                + 'border-top:' + bTop + ';'
                + 'color:' + color + ';'
                + 'line-height:1;';

            html += '<span style="' + style + '">' + mora[i];

            if (hasDrop) {
                html += '<span style="position:absolute;right:0;top:-' + LINE_PX + 'px;'
                    + 'width:' + LINE_PX + 'px;height:40%;'
                    + 'background:' + color + ';"></span>';
            }

            html += '</span>';
        }
        html += '</span>';
        return html;
    }

    // ---- Pitch code detector ----
    function parsePitchCode(str) {
        if (!PITCH_ENABLED || !str) return null;
        var code = str.trim().toLowerCase();
        if (code === 'h' || code === 'a' || code === 'o') {
            return { type: code, drop: 0, color: COLORS[code] };
        }
        if (code.charAt(0) === 'n' && code.length > 1) {
            var drop = parseInt(code.substring(1), 10);
            if (!isNaN(drop) && drop > 0) {
                return { type: 'n', drop: drop, color: COLORS['n'] };
            }
        }
        return null;
    }

    // ---- Parse annotation ----
    function parseAnnotation(annotation, baseWord) {
        var parts = annotation.split(';');
        var reading = null;
        var pitch = null;
        var gloss = null;

        var firstAsPitch = parsePitchCode(parts[0]);

        if (firstAsPitch) {
            pitch = firstAsPitch;
            if (parts.length > 1 && parts[1].trim().length > 0) {
                gloss = parts[1].trim();
            }
        } else {
            reading = parts[0];
            if (parts.length > 1) {
                pitch = parsePitchCode(parts[1]);
            }
            if (parts.length > 2 && parts[2].trim().length > 0) {
                gloss = parts[2].trim();
            }
        }

        return { reading: reading, pitch: pitch, gloss: gloss };
    }

    // ---- Main conversion ----
    function convertFurigana(rootNode) {
        var walker = document.createTreeWalker(
            rootNode,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: function(node) {
                    var p = node.parentNode;
                    if (!p) return NodeFilter.FILTER_REJECT;
                    var tag = p.tagName;
                    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'RT')
                        return NodeFilter.FILTER_REJECT;
                    if (p.classList && p.classList.contains('uf-pitch-word'))
                        return NodeFilter.FILTER_REJECT;
                    if (node.nodeValue && node.nodeValue.indexOf('{') !== -1)
                        return NodeFilter.FILTER_ACCEPT;
                    return NodeFilter.FILTER_REJECT;
                }
            },
            false
        );

        var textNodes = [];
        while (walker.nextNode()) textNodes.push(walker.currentNode);

        for (var i = textNodes.length - 1; i >= 0; i--) {
            var textNode = textNodes[i];
            var text = textNode.nodeValue;

            var RE = /([^\s{]+?)\{([^}]+)\}/g;
            if (!RE.test(text)) continue;
            RE.lastIndex = 0;

            var parts = [];
            var lastIdx = 0;
            var m;

            while ((m = RE.exec(text)) !== null) {
                if (m.index > lastIdx) {
                    parts.push({ t: 'txt', v: text.substring(lastIdx, m.index) });
                }
                parts.push({ t: 'fg', base: m[1], ann: m[2] });
                lastIdx = m.index + m[0].length;
            }

            if (parts.length === 0) continue;
            if (lastIdx < text.length) {
                parts.push({ t: 'txt', v: text.substring(lastIdx) });
            }

            var frag = document.createDocumentFragment();
            for (var p = 0; p < parts.length; p++) {
                var part = parts[p];
                if (part.t === 'txt') {
                    frag.appendChild(document.createTextNode(part.v));
                } else {
                    var parsed = parseAnnotation(part.ann, part.base);

                    if (!parsed.reading && parsed.pitch) {
                        var container = document.createElement('span');
                        container.innerHTML = buildPitchHTML(part.base, parsed.pitch.type,
                                                            parsed.pitch.drop, parsed.pitch.color);
                        if (parsed.gloss) {
                            wrapWithTooltip(container, parsed.gloss);
                        }
                        frag.appendChild(container);

                    } else {
                        var rtContent = '';

                        if (parsed.pitch && parsed.reading) {
                            rtContent += buildPitchHTML(parsed.reading, parsed.pitch.type,
                                                       parsed.pitch.drop, parsed.pitch.color);
                        } else if (parsed.reading) {
                            rtContent += '<span>' + parsed.reading + '</span>';
                        }

                        var ruby = document.createElement('ruby');
                        ruby.innerHTML = part.base + '<rt>' + rtContent + '</rt>';

                        if (parsed.gloss) {
                            wrapWithTooltip(ruby, parsed.gloss);
                        }

                        frag.appendChild(ruby);
                    }
                }
            }
            textNode.parentNode.replaceChild(frag, textNode);
        }
    }

    // ---- Tooltip helper (Migaku-style: popup is a child of the word) ----
    function wrapWithTooltip(el, text) {
        el.classList.add('uf-has-info');
        var dot = document.createElement('span');
        dot.className = 'uf-info-dot';
        dot.textContent = '\u24D8';
        el.appendChild(dot);
        var popup = document.createElement('div');
        popup.className = 'uf-tooltip';
        popup.textContent = text;
        el.appendChild(popup);
    }

    function showPopup(el) {
        var popup = el.querySelector('.uf-tooltip');
        if (!popup) return;
        popup.style.display = 'block';
        popup.style.position = 'absolute';
        popup.style.left = '2px';
        popup.style.top = el.offsetHeight + 'px';
        var pRect = popup.getBoundingClientRect();
        var card = el.closest('.card') || document.body;
        var cardRect = card.getBoundingClientRect();
        var rightEdge = pRect.left + pRect.width;
        var limit = cardRect.left + cardRect.width;
        if (rightEdge > limit) {
            popup.style.left = '-' + (rightEdge - limit + 2) + 'px';
        }
        if (pRect.top + pRect.height > window.innerHeight) {
            popup.style.top = '-' + (popup.offsetHeight + 3) + 'px';
        }
    }

    function hidePopup(el) {
        var popup = el.querySelector('.uf-tooltip');
        if (popup) {
            popup.style.display = 'none';
            popup.style.left = '';
            popup.style.top = '';
        }
    }

    function hideAllPopups() {
        var popups = document.getElementsByClassName('uf-tooltip');
        for (var i = 0; i < popups.length; i++) {
            popups[i].style.display = 'none';
            popups[i].style.left = '';
            popups[i].style.top = '';
        }
    }

    document.body.addEventListener('mouseenter', function(e) {
        var el = e.target.closest('.uf-has-info');
        if (el) showPopup(el);
    }, true);
    document.body.addEventListener('mouseleave', function(e) {
        var el = e.target.closest('.uf-has-info');
        if (el) hidePopup(el);
    }, true);
    document.body.addEventListener('click', function(e) {
        var el = e.target.closest('.uf-has-info');
        if (el) {
            var popup = el.querySelector('.uf-tooltip');
            if (popup && popup.style.display === 'block') {
                hidePopup(el);
            } else {
                hideAllPopups();
                showPopup(el);
            }
        } else {
            hideAllPopups();
        }
    });

    function processCard() {
        var sels = ['.card', '#content', '#qa', '#qa_box', '.field'];
        var done = false;
        for (var s = 0; s < sels.length; s++) {
            var els = document.querySelectorAll(sels[s]);
            for (var i = 0; i < els.length; i++) {
                if (els[i].textContent.indexOf('{') !== -1) {
                    convertFurigana(els[i]);
                    done = true;
                }
            }
        }
        if (!done && document.body && document.body.textContent.indexOf('{') !== -1) {
            convertFurigana(document.body);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', processCard);
    } else {
        processCard();
    }

    if (typeof MutationObserver !== 'undefined') {
        var _seen = new WeakSet();
        new MutationObserver(function(muts) {
            for (var m = 0; m < muts.length; m++) {
                var nodes = muts[m].addedNodes;
                for (var n = 0; n < nodes.length; n++) {
                    var nd = nodes[n];
                    if (nd.nodeType === 1 && !_seen.has(nd) &&
                        nd.textContent && nd.textContent.indexOf('{') !== -1) {
                        _seen.add(nd);
                        convertFurigana(nd);
                    }
                }
            }
        }).observe(document.body, { childList: true, subtree: true });
    }
})();
</script>

<style>
ruby { ruby-align: center; ruby-position: over; }
ruby rt { font-size: %%RT_FONT_SIZE%%em; color: inherit; opacity: 0.85; font-weight: normal; line-height: 1.2; }
.uf-pitch-word span { font-size: 1em; }

/* Info tooltip system */
.uf-has-info { position: relative; cursor: help; }
.uf-has-info:hover { background: rgba(255,255,255,0.06); border-radius: 3px; }
.uf-info-dot {
    font-size: 0.45em;
    vertical-align: super;
    opacity: 0.35;
    margin-left: 1px;
    cursor: help;
    position: relative;
    top: -0.5em;
}
.uf-tooltip {
    display: none;
    position: absolute;
    z-index: 99999;
    background: #2a2a3e;
    color: #ddd;
    border: 1px solid #555;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 14px;
    line-height: 1.4;
    max-width: 300px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    pointer-events: none;
    white-space: normal;
    word-wrap: break-word;
}
</style>
"""


def _build_script(cfg):
    """Build the JS/CSS payload using current config values."""
    colors = json.dumps({
        "h": cfg["color_heiban"],
        "a": cfg["color_atamadaka"],
        "n": cfg["color_nakadaka"],
        "o": cfg["color_odaka"],
    })
    thickness = str(int(cfg.get("line_thickness", 2)))
    pitch_enabled = "true" if cfg.get("pitch_accent_enabled", True) else "false"

    script = _SCRIPT_TEMPLATE
    script = script.replace("%%PITCH_ENABLED%%", pitch_enabled)
    script = script.replace("%%COLORS%%", colors)
    script = script.replace("%%LINE_PX%%", thickness)
    rt_size = str(cfg.get("furigana_font_size", 0.6))
    script = script.replace("%%RT_FONT_SIZE%%", rt_size)
    return script


def _build_injectable(cfg):
    """Build the marked block for template injection."""
    return _MARKER_START + "\n" + _build_script(cfg).strip() + "\n" + _MARKER_END


# ---------------------------------------------------------------------------
# Template injection helpers
# ---------------------------------------------------------------------------

def _strip_injection(html):
    """Remove any existing UF injection from HTML."""
    pattern = re.compile(
        re.escape(_MARKER_START) + r".*?" + re.escape(_MARKER_END),
        re.DOTALL
    )
    return pattern.sub("", html).rstrip()


def _has_injection(html):
    """Check if HTML already has a UF injection."""
    return _MARKER_START in html


def _make_key(note_name, tmpl_name, side):
    """Create a unique key for a template side."""
    return "%s::%s::%s" % (note_name, tmpl_name, side)


def _inject_templates(cfg):
    """Inject or remove script from card templates based on config."""
    wanted = set(cfg.get("injected_templates", []))
    block = _build_injectable(cfg)
    col = mw.col
    if not col:
        return

    models = col.models.all()
    for model in models:
        note_name = model["name"]
        for tmpl in model["tmpls"]:
            tmpl_name = tmpl["name"]
            changed = False

            for side, field in [("front", "qfmt"), ("back", "afmt")]:
                key = _make_key(note_name, tmpl_name, side)
                html = tmpl[field]
                stripped = _strip_injection(html)

                if key in wanted:
                    # Inject (or re-inject with updated config)
                    tmpl[field] = stripped + "\n\n" + block
                    changed = True
                elif _has_injection(html):
                    # Remove injection
                    tmpl[field] = stripped
                    changed = True

            if changed:
                col.models.save(model)


def _remove_all_injections():
    """Remove UF injection from ALL templates."""
    col = mw.col
    if not col:
        return
    models = col.models.all()
    for model in models:
        changed = False
        for tmpl in model["tmpls"]:
            for field in ["qfmt", "afmt"]:
                if _has_injection(tmpl[field]):
                    tmpl[field] = _strip_injection(tmpl[field])
                    changed = True
        if changed:
            col.models.save(model)


# ---------------------------------------------------------------------------
# Card hook (fallback for non-injected templates)
# ---------------------------------------------------------------------------

def on_card_will_show(text: str, card, kind: str) -> str:
    cfg = _get_config()
    if not cfg.get("enabled", True):
        return text
    # Skip injection if template already has our markers
    if _MARKER_START in text:
        return text
    if '{' in text and '}' in text:
        return text + _build_script(cfg)
    return text


gui_hooks.card_will_show.append(on_card_will_show)


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class _ColorButton(QPushButton):
    """A button that shows its color and opens a color picker on click."""

    def __init__(self, color_hex, parent=None):
        super().__init__(parent)
        self._color = color_hex
        self.setFixedSize(60, 28)
        self._update_style()
        self.clicked.connect(self._pick_color)

    def _update_style(self):
        self.setStyleSheet(
            "background-color: %s; border: 1px solid #888; "
            "border-radius: 4px; min-width: 50px;" % self._color
        )

    def _pick_color(self):
        from aqt.qt import QColor
        color = QColorDialog.getColor(
            QColor(self._color), self.parentWidget(), "Pick Color"
        )
        if color.isValid():
            self._color = color.name()
            self._update_style()

    def color(self):
        return self._color


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Universal Furigana \u2014 Settings")
        self.setMinimumWidth(560)
        self.cfg = _get_config()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # -- How it works --
        info_group = QGroupBox("How It Works")
        info_layout = QVBoxLayout(info_group)
        info_text = QLabel(
            "<b>Furigana</b><br>"
            "Type <code>word{reading}</code> in any card field. "
            "A space before the word acts as the delimiter.<br><br>"
            "<b>Examples:</b><br>"
            "<code>\u98df\u3079\u308b{\u305f\u3079\u308b}</code> \u2192 reading above the word<br>"
            "<code>\u98df\u3079\u308b{to eat}</code> \u2192 English gloss above the word<br><br>"
            "<b>Pitch Accent (with reading)</b><br>"
            "Add a pitch code after a semicolon:<br>"
            "<code>\u5b66\u751f{\u304c\u304f\u305b\u3044;h}</code> \u2192 heiban (flat) \u2014 blue<br>"
            "<code>\u79cb{\u3042\u304d;a}</code> \u2192 atamadaka (head-high) \u2014 red<br>"
            "<code>\u5fc3{\u3053\u3053\u308d;n2}</code> \u2192 nakadaka (drop after 2nd mora) \u2014 orange<br>"
            "<code>\u82b1{\u306f\u306a;o}</code> \u2192 odaka (tail-high, drop on particle) \u2014 green<br><br>"
            "<b>Pitch Accent (without reading)</b><br>"
            "Use just the pitch code \u2014 lines are drawn on the base word itself:<br>"
            "<code>\u3077\u3063\u3064\u308a{n3}</code> \u2192 orange line with drop after 3rd mora<br>"
            "<code>\u304c\u304f\u305b\u3044{h}</code> \u2192 blue flat line on the word<br><br>"
            "<b>Info Tooltip (hover/tap)</b><br>"
            "Add a description as the last segment \u2014 it shows as a \u24D8 tooltip:<br>"
            "<code>\u6c17\u524d{\u304d\u307e\u3048;h;generosity}</code> \u2192 reading + pitch + tooltip<br>"
            "<code>\u98df\u3079\u308b{\u305f\u3079\u308b;;to eat}</code> \u2192 reading + tooltip (no pitch)<br>"
            "<code>\u3077\u3063\u3064\u308a{n3;snapping}</code> \u2192 pitch-only + tooltip<br>"
            "Hover on desktop or tap on mobile to see the description.<br>"
            "Tap elsewhere to dismiss on mobile.<br><br>"
            "Pitch accent shows colored lines above the furigana:<br>"
            "\u25aa A <b>top line</b> marks high-pitch mora<br>"
            "\u25aa A <b>vertical step</b> marks where the pitch drops<br>"
            "\u25aa No hover needed \u2014 the pattern is always visible"
        )
        info_text.setWordWrap(True)
        info_text.setTextFormat(Qt.TextFormat.RichText)
        info_layout.addWidget(info_text)
        layout.addWidget(info_group)

        # -- Enable / Disable --
        self.enabled_cb = QCheckBox("Enable furigana conversion")
        self.enabled_cb.setChecked(self.cfg.get("enabled", True))
        layout.addWidget(self.enabled_cb)

        self.pitch_cb = QCheckBox("Enable pitch accent visualization")
        self.pitch_cb.setChecked(self.cfg.get("pitch_accent_enabled", True))
        layout.addWidget(self.pitch_cb)

        # -- Color settings --
        color_group = QGroupBox("Pitch Accent Colors")
        color_grid = QGridLayout(color_group)

        labels = [
            ("Heiban (h) \u2014 flat:", "color_heiban"),
            ("Atamadaka (a) \u2014 head-high:", "color_atamadaka"),
            ("Nakadaka (nX) \u2014 mid-drop:", "color_nakadaka"),
            ("Odaka (o) \u2014 tail-high:", "color_odaka"),
        ]

        self._color_buttons = {}
        for row, (label_text, key) in enumerate(labels):
            lbl = QLabel(label_text)
            btn = _ColorButton(self.cfg.get(key, _DEFAULT_CONFIG[key]))
            self._color_buttons[key] = btn
            color_grid.addWidget(lbl, row, 0)
            color_grid.addWidget(btn, row, 1)

        layout.addWidget(color_group)

        # -- Furigana font size --
        font_group = QGroupBox("Furigana Font Size")
        font_layout = QHBoxLayout(font_group)
        font_layout.addWidget(QLabel("Size (em):"))
        self.font_spin = QDoubleSpinBox()
        self.font_spin.setRange(0.3, 1.5)
        self.font_spin.setSingleStep(0.05)
        self.font_spin.setDecimals(2)
        self.font_spin.setValue(self.cfg.get("furigana_font_size", 0.6))
        self.font_spin.setToolTip(
            "Controls how large the furigana text is relative to the base text. "
            "Smaller values = smaller furigana. Default: 0.60"
        )
        font_layout.addWidget(self.font_spin)
        font_layout.addStretch()
        layout.addWidget(font_group)

        # -- Mobile compatibility: template injection --
        mobile_group = QGroupBox("Mobile Compatibility (AnkiDroid / AnkiMobile)")
        mobile_layout = QVBoxLayout(mobile_group)

        mobile_info = QLabel(
            "Check the templates below to inject the furigana script directly "
            "into your card templates. This makes it work on <b>AnkiDroid</b> and "
            "<b>AnkiMobile (iOS)</b> after syncing.\n\n"
            "On desktop, the add-on works automatically on all cards even without "
            "checking anything here."
        )
        mobile_info.setWordWrap(True)
        mobile_layout.addWidget(mobile_info)

        # Scrollable area for template checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        injected_set = set(self.cfg.get("injected_templates", []))
        self._template_cbs = {}  # key -> QCheckBox

        col = mw.col
        if col:
            models = col.models.all()
            for model in sorted(models, key=lambda m: m["name"]):
                note_name = model["name"]
                for tmpl in model["tmpls"]:
                    tmpl_name = tmpl["name"]
                    for side, label in [("front", "Front"), ("back", "Back")]:
                        key = _make_key(note_name, tmpl_name, side)
                        display = "%s \u2192 %s \u2192 %s" % (
                            note_name, tmpl_name, label
                        )
                        cb = QCheckBox(display)
                        cb.setChecked(key in injected_set)
                        scroll_layout.addWidget(cb)
                        self._template_cbs[key] = cb

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        mobile_layout.addWidget(scroll)

        # Select all / deselect all
        sel_layout = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._select_all_templates)
        desel_all_btn = QPushButton("Deselect All")
        desel_all_btn.clicked.connect(self._deselect_all_templates)
        sel_layout.addWidget(sel_all_btn)
        sel_layout.addWidget(desel_all_btn)
        sel_layout.addStretch()
        mobile_layout.addLayout(sel_layout)

        layout.addWidget(mobile_group)

        # -- Buttons --
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        restore_btn = QPushButton("Restore Defaults")
        restore_btn.clicked.connect(self._on_restore)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)

        btn_layout.addWidget(restore_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _select_all_templates(self):
        for cb in self._template_cbs.values():
            cb.setChecked(True)

    def _deselect_all_templates(self):
        for cb in self._template_cbs.values():
            cb.setChecked(False)

    def _on_save(self):
        self.cfg["enabled"] = self.enabled_cb.isChecked()
        self.cfg["pitch_accent_enabled"] = self.pitch_cb.isChecked()
        self.cfg["furigana_font_size"] = round(self.font_spin.value(), 2)
        for key, btn in self._color_buttons.items():
            self.cfg[key] = btn.color()

        # Collect checked templates
        selected = []
        for key, cb in self._template_cbs.items():
            if cb.isChecked():
                selected.append(key)
        self.cfg["injected_templates"] = selected

        _save_config(self.cfg)

        # Inject/remove from templates
        _inject_templates(self.cfg)

        self.accept()

    def _on_restore(self):
        self.cfg = dict(_DEFAULT_CONFIG)
        self.enabled_cb.setChecked(True)
        self.pitch_cb.setChecked(True)
        self.font_spin.setValue(_DEFAULT_CONFIG["furigana_font_size"])
        for key, btn in self._color_buttons.items():
            btn._color = _DEFAULT_CONFIG[key]
            btn._update_style()
        for cb in self._template_cbs.values():
            cb.setChecked(False)


def _open_settings():
    dialog = SettingsDialog(mw)
    dialog.exec()


# -- Menu item --
_action = mw.form.menuTools.addAction("Universal Furigana Settings\u2026")
_action.triggered.connect(_open_settings)

"""
Universal Furigana Add-on for Anki (v2)
========================================
Converts {annotation} syntax into ruby text on ANY card, ANY field.
Supports pitch accent visualization with colored lines above mora.

Works on desktop (Anki 2.1.x) and mobile (AnkiDroid / AnkiMobile).

Syntax:
  word{reading}          -> furigana reading above word
  word{reading;h}        -> heiban pitch accent (blue, flat line)
  word{reading;a}        -> atamadaka pitch accent (red, drop after 1st)
  word{reading;nX}       -> nakadaka pitch accent (orange, drop after Xth mora)
  word{reading;o}        -> odaka pitch accent (green, drop after last mora)

Author: Eric Su (reysu)
"""

import json
import os
from aqt import mw, gui_hooks
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QColorDialog, QGroupBox, QGridLayout,
    QFrame, Qt, QFont, QWidget
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
}


def _get_config():
    cfg = mw.addonManager.getConfig(__name__) or {}
    merged = dict(_DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def _save_config(cfg):
    mw.addonManager.writeConfig(__name__, cfg)


# ---------------------------------------------------------------------------
# JavaScript + CSS injected into every card
# ---------------------------------------------------------------------------

# The JS is kept as a plain string template with PLACEHOLDER markers
# that get replaced with config values. This avoids f-string escaping hell
# with JS regex braces.

_SCRIPT_TEMPLATE = r"""
<script>
(function() {
    var PITCH_ENABLED = %%PITCH_ENABLED%%;
    var COLORS = %%COLORS%%;
    var LINE_PX = %%LINE_PX%%;

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
    // Returns array of 0 (low) / 1 (high) per mora
    function getPitchPattern(moraCount, type, dropAt) {
        var pattern = [];
        if (type === 'h') {
            // Heiban: L H H H H ...
            pattern.push(0);
            for (var i = 1; i < moraCount; i++) pattern.push(1);
        } else if (type === 'a') {
            // Atamadaka: H L L L ...
            pattern.push(1);
            for (var i = 1; i < moraCount; i++) pattern.push(0);
        } else if (type === 'o') {
            // Odaka: L H H H ... H (drop after last)
            pattern.push(0);
            for (var i = 1; i < moraCount; i++) pattern.push(1);
        } else if (type === 'n') {
            // Nakadaka: L H H ... H L L (drop after mora #dropAt)
            pattern.push(0);
            for (var i = 1; i < moraCount; i++) {
                pattern.push(i < dropAt ? 1 : 0);
            }
        }
        return pattern;
    }

    // ---- Build pitch HTML ----
    // Draws a clean horizontal line above high-pitch mora.
    // Only a single vertical drop line where pitch falls — no boxes.
    //   heiban:    flat line across all mora (no verticals)
    //   atamadaka: line on 1st mora, drop-line on its right
    //   nakadaka:  line from 2nd mora to drop point, drop-line there
    //   odaka:     flat line across all mora, drop-line after last
    function buildPitchHTML(reading, type, dropAt, color) {
        var mora = splitMora(reading);
        var moraCount = mora.length;
        var pattern = getPitchPattern(moraCount, type, dropAt);
        var html = '<span class="uf-pitch-word" style="display:inline-flex;align-items:flex-end;">';

        for (var i = 0; i < mora.length; i++) {
            var isHigh = pattern[i] === 1;
            var nextLow = (i + 1 < mora.length) ? pattern[i + 1] === 0 : false;

            var bTop = isHigh ? (LINE_PX + 'px solid ' + color) : 'none';

            // Check if this mora is the drop point
            var hasDrop = false;
            if (type === 'a' && i === 0) hasDrop = true;
            else if (type === 'n' && isHigh && nextLow) hasDrop = true;
            else if (type === 'o' && i === mora.length - 1) hasDrop = true;

            // Use position:relative on the mora span so we can place
            // a half-height drop line via an inner absolute span
            var style = 'display:inline-block;position:relative;'
                + 'padding-top:' + (LINE_PX + 2) + 'px;'
                + 'border-top:' + bTop + ';'
                + 'color:' + color + ';'
                + 'line-height:1;';

            html += '<span style="' + style + '">' + mora[i];

            if (hasDrop) {
                // Small absolute-positioned span on the right edge,
                // 50% tall. Starts from -LINE_PX so it overlaps with
                // the border-top and connects seamlessly at the corner.
                html += '<span style="position:absolute;right:0;top:-' + LINE_PX + 'px;'
                    + 'width:' + LINE_PX + 'px;height:40%;'
                    + 'background:' + color + ';"></span>';
            }

            html += '</span>';
        }
        html += '</span>';
        return html;
    }

    // ---- Parse annotation ----
    function parseAnnotation(annotation) {
        var parts = annotation.split(';');
        var reading = parts[0];
        var pitch = null;

        if (PITCH_ENABLED && parts.length > 1) {
            var code = parts[1].trim().toLowerCase();
            if (code === 'h' || code === 'a' || code === 'o') {
                pitch = { type: code, drop: 0, color: COLORS[code] };
            } else if (code.charAt(0) === 'n' && code.length > 1) {
                var drop = parseInt(code.substring(1), 10);
                if (!isNaN(drop)) {
                    pitch = { type: 'n', drop: drop, color: COLORS['n'] };
                }
            }
        }
        return { reading: reading, pitch: pitch };
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
            RE.lastIndex = 0;  // reset after .test()

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
                    var parsed = parseAnnotation(part.ann);
                    if (parsed.pitch) {
                        var wrapper = document.createElement('ruby');
                        wrapper.innerHTML = part.base + '<rt>' +
                            buildPitchHTML(parsed.reading, parsed.pitch.type,
                                          parsed.pitch.drop, parsed.pitch.color) +
                            '</rt>';
                        frag.appendChild(wrapper);
                    } else {
                        var ruby = document.createElement('ruby');
                        ruby.textContent = part.base;
                        var rt = document.createElement('rt');
                        rt.textContent = parsed.reading;
                        ruby.appendChild(rt);
                        frag.appendChild(ruby);
                    }
                }
            }
            textNode.parentNode.replaceChild(frag, textNode);
        }
    }

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
ruby { ruby-align: center; }
ruby rt { font-size: 0.6em; color: inherit; opacity: 0.85; font-weight: normal; }
.uf-pitch-word span { font-size: 1em; }
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
    return script


# ---------------------------------------------------------------------------
# Card hook
# ---------------------------------------------------------------------------

def on_card_will_show(text: str, card, kind: str) -> str:
    cfg = _get_config()
    if not cfg.get("enabled", True):
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
        self.setMinimumWidth(520)
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
            "<b>Pitch Accent</b><br>"
            "Add a pitch code after a semicolon:<br>"
            "<code>\u5b66\u751f{\u304c\u304f\u305b\u3044;h}</code> \u2192 heiban (flat) \u2014 blue<br>"
            "<code>\u79cb{\u3042\u304d;a}</code> \u2192 atamadaka (head-high) \u2014 red<br>"
            "<code>\u5fc3{\u3053\u3053\u308d;n2}</code> \u2192 nakadaka (drop after 2nd mora) \u2014 orange<br>"
            "<code>\u82b1{\u306f\u306a;o}</code> \u2192 odaka (tail-high, drop on particle) \u2014 green<br><br>"
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

    def _on_save(self):
        self.cfg["enabled"] = self.enabled_cb.isChecked()
        self.cfg["pitch_accent_enabled"] = self.pitch_cb.isChecked()
        for key, btn in self._color_buttons.items():
            self.cfg[key] = btn.color()
        _save_config(self.cfg)
        self.accept()

    def _on_restore(self):
        self.cfg = dict(_DEFAULT_CONFIG)
        self.enabled_cb.setChecked(True)
        self.pitch_cb.setChecked(True)
        for key, btn in self._color_buttons.items():
            btn._color = _DEFAULT_CONFIG[key]
            btn._update_style()


def _open_settings():
    dialog = SettingsDialog(mw)
    dialog.exec()


# -- Menu item --
_action = mw.form.menuTools.addAction("Universal Furigana Settings\u2026")
_action.triggered.connect(_open_settings)

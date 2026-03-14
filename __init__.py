"""
Universal Furigana Add-on for Anki (v10m)
========================================
Converts {annotation} syntax into ruby text on ANY card, ANY field.
Supports pitch accent visualization with colored lines above mora.
Info tooltips via hover (desktop) or tap (mobile).
Dictionary lookup: import Yomitan/Yomichan dictionaries for auto-fill.

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
  word{reading;?;desc}     -> reading + info tooltip (unknown pitch)
  word{pitch;desc}         -> pitch-only + info tooltip
  word{!reading}           -> hidden furigana (blurred, hover/tap to reveal)
  word{!reading;pitch}     -> hidden furigana + pitch (blurred)
  word{!reading;pitch;desc} -> hidden furigana + pitch + tooltip

Author: Eric Su (reysu)
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from aqt import mw, gui_hooks
from aqt.editor import Editor
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QColorDialog, QGroupBox, QGridLayout,
    QFrame, Qt, QFont, QWidget, QScrollArea, QMessageBox,
    QDoubleSpinBox, QFileDialog, QListWidget, QListWidgetItem,
    QProgressDialog, QApplication, QLineEdit, QTextEdit,
    QTabWidget, QComboBox
)

# Debug marker (stdout, not stderr — stderr triggers Anki error dialogs)
sys.stdout.write("[Universal Furigana] Add-on loaded successfully\n")


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
    "skip_particles": True,  # skip particles (助詞) in sentence mode
    "color_words_enabled": False,   # master on/off for coloring the base word
    "color_words_furigana": True,   # color furigana text (already the default behavior)
    "color_words_kanji": False,     # color the kanji/base text too
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
    var COLOR_WORDS = %%COLOR_WORDS%%;

    // Prevent duplicate global listener registration when the script is
    // re-injected on every card show (AnkiDroid reuses the webview).
    var _ufFirstLoad = !window._ufGlobalListenersReady;

    // ---- Dark mode detection ----
    function isDarkMode() {
        var b = document.body;
        if (!b) return false;
        if (b.classList.contains('nightMode') || b.classList.contains('night_mode')) return true;
        // Check ancestors (AnkiDroid sometimes puts class higher up)
        var el = b.parentElement;
        while (el) {
            if (el.classList && (el.classList.contains('nightMode') || el.classList.contains('night_mode'))) return true;
            el = el.parentElement;
        }
        // Fallback: check computed background color brightness
        var bg = window.getComputedStyle(b).backgroundColor;
        if (bg) {
            var m = bg.match(/\d+/g);
            if (m && m.length >= 3) {
                var lum = 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
                if (lum < 80) return true;
            }
        }
        return false;
    }

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
        var html = '<span class="uf-pitch-word" style="display:contents;">';

        for (var i = 0; i < mora.length; i++) {
            var isHigh = pattern[i] === 1;
            var nextLow = (i + 1 < mora.length) ? pattern[i + 1] === 0 : false;

            var bTop = isHigh ? (LINE_PX + 'px solid ' + color) : (LINE_PX + 'px solid transparent');

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
        var hidden = false;
        if (annotation.charAt(0) === '!') {
            hidden = true;
            annotation = annotation.substring(1);
        }
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

        return { reading: reading, pitch: pitch, gloss: gloss, hidden: hidden };
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
                        var useColor = parsed.pitch.color;
                        if (COLOR_WORDS.enabled) {
                            if (!COLOR_WORDS.kanji) useColor = 'inherit';
                        }
                        container.innerHTML = buildPitchHTML(part.base, parsed.pitch.type,
                                                            parsed.pitch.drop, useColor);
                        if (parsed.hidden) container.classList.add('uf-hidden');
                        if (parsed.gloss) {
                            wrapWithTooltip(container, parsed.gloss);
                        }
                        frag.appendChild(container);

                    } else {
                        var rtContent = '';

                        if (parsed.pitch && parsed.reading) {
                            var fgColor = parsed.pitch.color;
                            if (COLOR_WORDS.enabled && !COLOR_WORDS.furigana) fgColor = 'inherit';
                            rtContent += buildPitchHTML(parsed.reading, parsed.pitch.type,
                                                       parsed.pitch.drop, fgColor);
                        } else if (parsed.reading) {
                            rtContent += '<span>' + parsed.reading + '</span>';
                        }

                        var ruby = document.createElement('ruby');
                        if (parsed.hidden) ruby.classList.add('uf-hidden');
                        var baseHTML = part.base;
                        if (COLOR_WORDS.enabled && COLOR_WORDS.kanji && parsed.pitch) {
                            baseHTML = '<span style="color:' + parsed.pitch.color + '">' + part.base + '</span>';
                        } else if (isDarkMode()) {
                            ruby.style.color = '#fff';
                        }
                        ruby.innerHTML = baseHTML + '<rt>' + rtContent + '</rt>';

                        if (parsed.gloss) {
                            // Attach tooltip directly to the ruby element (no wrapper needed)
                            var rtEl = ruby.querySelector('rt');
                            wrapWithTooltip(ruby, parsed.gloss, rtEl);
                        }
                        frag.appendChild(ruby);
                    }
                }
            }
            // Guard: textNode may have been detached by a concurrent
            // MutationObserver or a prior iteration; skip if orphaned.
            if (textNode.parentNode) {
                textNode.parentNode.replaceChild(frag, textNode);
            }
        }
    }

    // ---- Tooltip with pagination (portal-based to avoid layout shift) ----
    var CHARS_PER_PAGE = 120;
    var _ufTooltipId = 0;

    // Get or create the portal container for tooltips (lives outside text flow)
    function getTooltipPortal() {
        var portal = document.getElementById('uf-tooltip-portal');
        if (!portal) {
            portal = document.createElement('div');
            portal.id = 'uf-tooltip-portal';
            document.body.appendChild(portal);
        }
        return portal;
    }

    function wrapWithTooltip(el, text, rtEl) {
        el.classList.add('uf-has-info');
        var tooltipId = 'uf-tt-' + (_ufTooltipId++);
        el.setAttribute('data-uf-tt', tooltipId);

        var dot = document.createElement('span');
        dot.className = 'uf-info-dot';
        dot.textContent = '\u24D8';
        // Place dot inside <rt> (next to furigana) when available,
        // otherwise fall back to appending on the wrapper element
        if (rtEl) {
            dot.classList.add('uf-info-dot-rt');
            rtEl.appendChild(dot);
        } else {
            el.appendChild(dot);
        }

        // Build popup in portal (outside text flow entirely)
        var popup = document.createElement('div');
        popup.className = 'uf-tooltip';
        popup.id = tooltipId;

        var pages = paginate(text);
        popup.setAttribute('data-pages', JSON.stringify(pages));
        popup.setAttribute('data-page', '0');

        var body = document.createElement('div');
        body.className = 'uf-tt-body';
        popup.appendChild(body);

        if (pages.length > 1) {
            var nav = document.createElement('div');
            nav.className = 'uf-tt-nav';
            var prev = document.createElement('span');
            prev.className = 'uf-tt-prev';
            prev.textContent = '\u2039';
            var info = document.createElement('span');
            info.className = 'uf-tt-info';
            var next = document.createElement('span');
            next.className = 'uf-tt-next';
            next.textContent = '\u203A';
            prev.addEventListener('touchend', function(ev) { ev.stopPropagation(); ev.preventDefault(); ufNavPage(popup, -1); });
            prev.addEventListener('click', function(ev) { ev.stopPropagation(); ufNavPage(popup, -1); });
            next.addEventListener('touchend', function(ev) { ev.stopPropagation(); ev.preventDefault(); ufNavPage(popup, 1); });
            next.addEventListener('click', function(ev) { ev.stopPropagation(); ufNavPage(popup, 1); });
            nav.appendChild(prev);
            nav.appendChild(info);
            nav.appendChild(next);
            popup.appendChild(nav);
        }

        // Append to portal, NOT inside the word element
        getTooltipPortal().appendChild(popup);

        // Direct touch handlers for mobile.
        // We track touch position so only genuine taps toggle the tooltip
        // (not swipes/scrolls), and we call stopPropagation to prevent
        // AnkiDroid from interpreting the tap as a card-advance gesture.
        var _touchStartX = 0, _touchStartY = 0;
        el.addEventListener('touchstart', function(ev) {
            var t = ev.changedTouches[0];
            _touchStartX = t.clientX;
            _touchStartY = t.clientY;
        }, { passive: true });
        el.addEventListener('touchend', function(ev) {
            // Let nav arrow taps through without toggling
            if (ev.target.closest('.uf-tt-prev, .uf-tt-next')) return;
            // Ignore swipes (moved > 15px)
            var t = ev.changedTouches[0];
            var dx = Math.abs(t.clientX - _touchStartX);
            var dy = Math.abs(t.clientY - _touchStartY);
            if (dx > 15 || dy > 15) return;
            ev.preventDefault();
            ev.stopPropagation();
            var tid = this.getAttribute('data-uf-tt');
            var p = document.getElementById(tid);
            if (!p) return;
            if (p.classList.contains('uf-tt-show')) {
                _tt.pinned = null;
                hidePopup(this);
            } else {
                _tt.pinned = this;
                hideAllPopups();
                showPopup(this);
            }
        });
    }

    function ufNavPage(popup, dir) {
        var pages = JSON.parse(popup.getAttribute('data-pages'));
        var idx = parseInt(popup.getAttribute('data-page'), 10);
        idx += dir;
        if (idx < 0) idx = 0;
        if (idx >= pages.length) idx = pages.length - 1;
        popup.setAttribute('data-page', idx);
        renderPage(popup);
    }

    function paginate(text) {
        if (text.length <= CHARS_PER_PAGE) return [text];
        var pages = [];
        var remaining = text;
        while (remaining.length > 0) {
            if (remaining.length <= CHARS_PER_PAGE) {
                pages.push(remaining);
                break;
            }
            var cut = CHARS_PER_PAGE;
            var breakChars = '\u3002\u3001\uff0c\uff0e\uff1b.,;!? \n';
            var best = -1;
            for (var j = Math.floor(CHARS_PER_PAGE * 0.6); j <= cut; j++) {
                if (breakChars.indexOf(remaining[j]) !== -1) best = j + 1;
            }
            if (best > 0) cut = best;
            pages.push(remaining.substring(0, cut));
            remaining = remaining.substring(cut);
        }
        return pages;
    }

    function renderPage(popup) {
        var pages = JSON.parse(popup.getAttribute('data-pages'));
        var idx = parseInt(popup.getAttribute('data-page'), 10);
        var body = popup.querySelector('.uf-tt-body');
        body.textContent = pages[idx];
        var info = popup.querySelector('.uf-tt-info');
        if (info) info.textContent = (idx + 1) + '/' + pages.length;
        var prev = popup.querySelector('.uf-tt-prev');
        var next = popup.querySelector('.uf-tt-next');
        if (prev) prev.style.opacity = idx > 0 ? '1' : '0.25';
        if (next) next.style.opacity = idx < pages.length - 1 ? '1' : '0.25';
    }

    function getPopupForEl(el) {
        var tid = el.getAttribute('data-uf-tt');
        return tid ? document.getElementById(tid) : null;
    }

    function showPopup(el) {
        var popup = getPopupForEl(el);
        if (!popup) return;
        popup.setAttribute('data-page', '0');
        renderPage(popup);
        // Defer layout reads to next frame so the mouseenter handler
        // doesn't force a synchronous reflow (which causes 1px jitter).
        requestAnimationFrame(function() {
            var elRect = el.getBoundingClientRect();
            popup.style.left = elRect.left + 'px';
            popup.style.top = (elRect.bottom + 2) + 'px';
            var pRect = popup.getBoundingClientRect();
            if (pRect.right > window.innerWidth - 4) {
                popup.style.left = Math.max(4, window.innerWidth - pRect.width - 4) + 'px';
            }
            pRect = popup.getBoundingClientRect();
            if (pRect.left < 4) {
                popup.style.left = '4px';
            }
            pRect = popup.getBoundingClientRect();
            if (pRect.bottom > window.innerHeight) {
                popup.style.top = (elRect.top - pRect.height - 2) + 'px';
            }
            popup.classList.add('uf-tt-show');
        });
    }

    function hidePopup(el) {
        var popup = getPopupForEl(el);
        if (popup) {
            popup.classList.remove('uf-tt-show');
        }
    }

    function hideAllPopups() {
        var popups = document.getElementsByClassName('uf-tooltip');
        for (var i = 0; i < popups.length; i++) {
            popups[i].classList.remove('uf-tt-show');
        }
    }

    // Store tooltip state on window so it survives re-injection across cards.
    // Each re-injection (new IIFE scope) shares the same state objects.
    if (!window._ufTT) window._ufTT = { pinned: null, hoverEl: null, hoverTimer: null };
    var _tt = window._ufTT;

    // Global event listeners — only register once even when the script
    // is re-injected on each card show (AnkiDroid).
    if (_ufFirstLoad) {
        window._ufGlobalListenersReady = true;

        // Desktop: hover to preview (only when nothing is pinned)
        document.body.addEventListener('mouseenter', function(e) {
            if (_tt.pinned) return;
            var el = e.target.closest('.uf-has-info');
            var inPopup = e.target.closest('.uf-tooltip');
            if (el) {
                if (_tt.hoverTimer) { clearTimeout(_tt.hoverTimer); _tt.hoverTimer = null; }
                if (_tt.hoverEl && _tt.hoverEl !== el) hidePopup(_tt.hoverEl);
                _tt.hoverEl = el;
                showPopup(el);
            } else if (inPopup) {
                if (_tt.hoverTimer) { clearTimeout(_tt.hoverTimer); _tt.hoverTimer = null; }
            }
        }, true);
        document.body.addEventListener('mouseleave', function(e) {
            if (_tt.pinned) return;
            var el = e.target.closest('.uf-has-info');
            var inPopup = e.target.closest('.uf-tooltip');
            if (el || inPopup) {
                if (_tt.hoverTimer) clearTimeout(_tt.hoverTimer);
                _tt.hoverTimer = setTimeout(function() {
                    if (_tt.hoverEl && !_tt.pinned) {
                        hidePopup(_tt.hoverEl);
                        _tt.hoverEl = null;
                    }
                }, 120);
            }
        }, true);

        // Click to pin/unpin (desktop + mobile fallback)
        document.body.addEventListener('click', function(e) {
            if (e.target.closest('.uf-tt-prev, .uf-tt-next')) return;
            if (e.target.closest('.uf-tooltip')) return;
            var el = e.target.closest('.uf-has-info');
            if (el) {
                if (_tt.pinned === el) {
                    _tt.pinned = null;
                    hidePopup(el);
                } else {
                    if (_tt.pinned) hidePopup(_tt.pinned);
                    _tt.pinned = el;
                    _tt.hoverEl = null;
                    if (_tt.hoverTimer) { clearTimeout(_tt.hoverTimer); _tt.hoverTimer = null; }
                    hideAllPopups();
                    showPopup(el);
                }
            } else {
                _tt.pinned = null;
                hideAllPopups();
            }
        });

        // Mobile: tap outside to dismiss all popups
        document.body.addEventListener('touchend', function(e) {
            if (!e.target.closest('.uf-has-info') && !e.target.closest('.uf-tooltip')) {
                _tt.pinned = null;
                hideAllPopups();
            }
        });

        // Hidden furigana: click/tap to lock revealed, click again to re-hide
        document.body.addEventListener('click', function(e) {
            var hid = e.target.closest('.uf-hidden');
            if (!hid) return;
            hid.classList.toggle('uf-revealed');
        }, true);
    }  // end _ufFirstLoad

    function processCard() {
        // ---- Cleanup from previous card ----
        // Remove stale tooltip portal so tooltips from the old card
        // don't leak into the new one.
        var oldPortal = document.getElementById('uf-tooltip-portal');
        if (oldPortal) oldPortal.remove();
        _tt.pinned = null;
        _tt.hoverEl = null;
        if (_tt.hoverTimer) { clearTimeout(_tt.hoverTimer); _tt.hoverTimer = null; }
        _ufTooltipId = 0;

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

    if (_ufFirstLoad && typeof MutationObserver !== 'undefined') {
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
ruby rt { font-size: %%RT_FONT_SIZE%%em; color: inherit; opacity: 0.85; font-weight: normal; line-height: 1.2; text-align: center; }

/* Info tooltip system — portal-based (tooltip lives outside text flow) */
.uf-has-info { cursor: default; -webkit-tap-highlight-color: rgba(0,0,0,0.05); }
#uf-tooltip-portal { position: fixed; top: 0; left: 0; width: 0; height: 0; z-index: 99999; pointer-events: none; overflow: visible; }
.uf-info-dot {
    font-size: 0.55em;
    opacity: 0.35;
    cursor: help;
    vertical-align: super;
    line-height: 0;
    pointer-events: none;
    margin-left: 0;
    margin-right: 0;
    display: inline;
    width: 0;
    overflow: visible;
}
.uf-info-dot.uf-info-dot-rt {
    vertical-align: middle;
    margin-left: 2px;
    font-size: 0.7em;
}
.uf-tooltip {
    visibility: hidden;
    pointer-events: none;
    position: fixed;
    z-index: 99999;
    background: #2a2a3e;
    color: #ddd;
    border: 1px solid #555;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    line-height: 1.5;
    width: max-content;
    max-width: min(75vw, 320px);
    max-height: 30vh;
    overflow-y: auto;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    white-space: normal;
    word-wrap: break-word;
}
.uf-tooltip.uf-tt-show {
    visibility: visible;
    pointer-events: auto;
}
.uf-tt-nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 6px;
    padding-top: 5px;
    border-top: 1px solid #444;
    font-size: 12px;
    user-select: none;
    -webkit-user-select: none;
}
.uf-tt-prev, .uf-tt-next {
    cursor: pointer;
    padding: 4px 10px;
    border-radius: 4px;
    background: rgba(255,255,255,0.08);
}
.uf-tt-prev:active, .uf-tt-next:active { background: rgba(255,255,255,0.18); }
.uf-tt-info { color: #999; font-size: 11px; }

/* Night / dark mode overrides
   Force white text for ruby elements so they are visible on dark
   backgrounds even when the parent element lacks a color override.
   Pitch-accented text keeps its inline color (set in settings).
   Anki desktop uses .nightMode (camelCase), AnkiDroid uses .night_mode. */
.nightMode ruby, .night_mode ruby { color: #fff !important; }
.nightMode ruby rt, .night_mode ruby rt { color: #fff !important; }
.nightMode .uf-info-dot, .night_mode .uf-info-dot { color: #fff !important; opacity: 0.5; }

/* Hidden furigana (! prefix) — blurred until hover/tap */
.uf-hidden rt,
.uf-hidden .uf-pitch-word {
    filter: blur(5px);
    -webkit-filter: blur(5px);
    transition: filter 0.15s ease;
    -webkit-transition: -webkit-filter 0.15s ease;
}
.uf-hidden:hover rt,
.uf-hidden:hover .uf-pitch-word,
.uf-hidden.uf-revealed rt,
.uf-hidden.uf-revealed .uf-pitch-word {
    filter: blur(0);
    -webkit-filter: blur(0);
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
    color_words = json.dumps({
        "enabled": cfg.get("color_words_enabled", False),
        "furigana": cfg.get("color_words_furigana", True),
        "kanji": cfg.get("color_words_kanji", False),
    })
    script = script.replace("%%COLOR_WORDS%%", color_words)
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
# Dictionary lookup: mora counter, pitch code converter
# ---------------------------------------------------------------------------

_SMALL_KANA = set('ゃゅょャュョァィゥェォ')


def _count_mora(kana):
    """Count mora in a kana string, combining digraphs."""
    count = 0
    i = 0
    while i < len(kana):
        count += 1
        if i + 1 < len(kana) and kana[i + 1] in _SMALL_KANA:
            i += 2
        else:
            i += 1
    return count


def _position_to_uf_code(position, reading):
    """Convert Yomitan pitch position number to UF pitch code."""
    if position == 0:
        return "h"
    elif position == 1:
        return "a"
    else:
        mora_count = _count_mora(reading)
        if position == mora_count:
            return "o"
        else:
            return "n%d" % position


def _extract_text_from_content(content, parts):
    """Recursively extract text from Yomitan structured-content."""
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for item in content:
            _extract_text_from_content(item, parts)
    elif isinstance(content, dict):
        if "content" in content:
            _extract_text_from_content(content["content"], parts)
        elif "text" in content:
            parts.append(content["text"])


# ---------------------------------------------------------------------------
# Dictionary database manager
# ---------------------------------------------------------------------------

class _DictDB:
    """Manages the SQLite dictionary database."""

    def __init__(self):
        self._conn = None
        self._db_path = None

    def _get_db_path(self):
        if self._db_path is None:
            addon_dir = os.path.dirname(os.path.abspath(__file__))
            self._db_path = os.path.join(
                addon_dir, "user_files", "dictionaries.db"
            )
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        return self._db_path

    def conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self._get_db_path())
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._ensure_tables()
        return self._conn

    def _ensure_tables(self):
        c = self.conn()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS dictionaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                revision TEXT,
                entry_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS terms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dict_id INTEGER NOT NULL,
                expression TEXT NOT NULL,
                reading TEXT NOT NULL,
                score INTEGER DEFAULT 0,
                definitions TEXT NOT NULL,
                FOREIGN KEY (dict_id) REFERENCES dictionaries(id)
            );
            CREATE TABLE IF NOT EXISTS pitch_accents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dict_id INTEGER NOT NULL,
                expression TEXT NOT NULL,
                reading TEXT NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY (dict_id) REFERENCES dictionaries(id)
            );
            CREATE INDEX IF NOT EXISTS idx_terms_expr
                ON terms(expression);
            CREATE INDEX IF NOT EXISTS idx_terms_expr_read
                ON terms(expression, reading);
            CREATE INDEX IF NOT EXISTS idx_pitch_expr
                ON pitch_accents(expression);
            CREATE INDEX IF NOT EXISTS idx_pitch_expr_read
                ON pitch_accents(expression, reading);
        """)
        c.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_dictionaries(self):
        """Return list of dicts ordered by priority."""
        rows = self.conn().execute(
            "SELECT id, name, type, priority, revision, entry_count "
            "FROM dictionaries ORDER BY priority ASC, id ASC"
        ).fetchall()
        return [
            {"id": r[0], "name": r[1], "type": r[2], "priority": r[3],
             "revision": r[4], "entry_count": r[5]}
            for r in rows
        ]

    def delete_dictionary(self, dict_id):
        c = self.conn()
        c.execute("DELETE FROM terms WHERE dict_id=?", (dict_id,))
        c.execute("DELETE FROM pitch_accents WHERE dict_id=?", (dict_id,))
        c.execute("DELETE FROM dictionaries WHERE id=?", (dict_id,))
        c.commit()

    def set_priority(self, dict_id, priority):
        c = self.conn()
        c.execute(
            "UPDATE dictionaries SET priority=? WHERE id=?",
            (priority, dict_id)
        )
        c.commit()

    def import_dictionary(self, zip_path, progress_cb=None):
        """Import a Yomitan .zip dictionary. Returns dict name."""
        import zipfile as zf

        with zf.ZipFile(zip_path, 'r') as z:
            try:
                index_data = json.loads(z.read("index.json"))
            except (KeyError, json.JSONDecodeError):
                raise ValueError(
                    "Invalid dictionary: missing or bad index.json"
                )

            dict_name = index_data.get("title", "Unknown Dictionary")
            revision = str(index_data.get("revision", ""))

            names = z.namelist()
            term_banks = sorted(
                [n for n in names
                 if n.startswith("term_bank_") and n.endswith(".json")]
            )
            meta_banks = sorted(
                [n for n in names
                 if n.startswith("term_meta_bank_") and n.endswith(".json")]
            )

            has_terms = len(term_banks) > 0
            has_pitch = False

            if has_terms and meta_banks:
                dict_type = "both"
            elif has_terms:
                dict_type = "term"
            elif meta_banks:
                dict_type = "pitch"
            else:
                raise ValueError(
                    "Dictionary contains no term or pitch data"
                )

            c = self.conn()
            max_pri = c.execute(
                "SELECT COALESCE(MAX(priority), -1) FROM dictionaries"
            ).fetchone()[0]

            cur = c.execute(
                "INSERT INTO dictionaries "
                "(name, type, priority, revision) VALUES (?, ?, ?, ?)",
                (dict_name, dict_type, max_pri + 1, revision)
            )
            dict_id = cur.lastrowid
            entry_count = 0
            total_files = len(term_banks) + len(meta_banks)
            processed = 0

            # --- term banks ---
            for bank_name in term_banks:
                try:
                    entries = json.loads(z.read(bank_name))
                except json.JSONDecodeError:
                    continue

                batch = []
                for entry in entries:
                    if not isinstance(entry, list) or len(entry) < 6:
                        continue
                    expression = str(entry[0])
                    reading = str(entry[1]) if entry[1] else expression
                    score = (
                        int(entry[4])
                        if isinstance(entry[4], (int, float)) else 0
                    )
                    raw_defs = entry[5]
                    defs = []
                    if isinstance(raw_defs, str):
                        defs = [raw_defs]
                    elif isinstance(raw_defs, list):
                        for d in raw_defs:
                            if isinstance(d, str):
                                defs.append(d)
                            elif isinstance(d, dict):
                                dt = d.get("type", "")
                                if dt == "text":
                                    defs.append(d.get("text", ""))
                                elif dt == "structured-content":
                                    parts = []
                                    _extract_text_from_content(
                                        d.get("content", ""), parts
                                    )
                                    if parts:
                                        defs.append(" ".join(parts))
                                elif dt != "image":
                                    txt = d.get(
                                        "text", d.get("content", "")
                                    )
                                    if isinstance(txt, str) and txt:
                                        defs.append(txt)
                    if not defs:
                        defs = [""]
                    batch.append((
                        dict_id, expression, reading, score,
                        json.dumps(defs, ensure_ascii=False)
                    ))
                    entry_count += 1

                if batch:
                    c.executemany(
                        "INSERT INTO terms "
                        "(dict_id, expression, reading, score, definitions) "
                        "VALUES (?,?,?,?,?)",
                        batch
                    )
                processed += 1
                if progress_cb:
                    progress_cb(processed, total_files)

            # --- meta banks (pitch) ---
            for bank_name in meta_banks:
                try:
                    entries = json.loads(z.read(bank_name))
                except json.JSONDecodeError:
                    continue

                pitch_batch = []
                for entry in entries:
                    if not isinstance(entry, list) or len(entry) < 3:
                        continue
                    if entry[1] != "pitch":
                        continue
                    has_pitch = True
                    data = entry[2]
                    if not isinstance(data, dict):
                        continue
                    rd = data.get("reading", str(entry[0]))
                    for p in data.get("pitches", []):
                        if isinstance(p, dict) and isinstance(
                            p.get("position"), int
                        ):
                            pitch_batch.append((
                                dict_id, str(entry[0]), rd, p["position"]
                            ))
                            entry_count += 1

                if pitch_batch:
                    c.executemany(
                        "INSERT INTO pitch_accents "
                        "(dict_id, expression, reading, position) "
                        "VALUES (?,?,?,?)",
                        pitch_batch
                    )
                processed += 1
                if progress_cb:
                    progress_cb(processed, total_files)

            # Finalize type
            if has_pitch and not has_terms:
                c.execute(
                    "UPDATE dictionaries SET type='pitch' WHERE id=?",
                    (dict_id,)
                )
            elif has_pitch and has_terms:
                c.execute(
                    "UPDATE dictionaries SET type='both' WHERE id=?",
                    (dict_id,)
                )

            c.execute(
                "UPDATE dictionaries SET entry_count=? WHERE id=?",
                (entry_count, dict_id)
            )
            c.commit()
            return dict_name

    # ---- Lookup methods ----

    def lookup(self, word):
        """Look up a word. User words first, then dicts by priority."""
        # Check user words first (highest priority)
        uw = _user_word_lookup(word)
        if uw and (uw["reading"] or uw["pitch_code"] or uw["definition"]):
            return uw

        c = self.conn()
        result = {"reading": None, "pitch_code": None, "definition": None}
        dicts = self.get_dictionaries()

        # Pitch
        for d in dicts:
            if d["type"] not in ("pitch", "both"):
                continue
            row = c.execute(
                "SELECT reading, position FROM pitch_accents "
                "WHERE expression=? AND dict_id=? LIMIT 1",
                (word, d["id"])
            ).fetchone()
            if row:
                result["pitch_code"] = _position_to_uf_code(row[1], row[0])
                if result["reading"] is None:
                    result["reading"] = row[0]
                break

        # Definition
        for d in dicts:
            if d["type"] not in ("term", "both"):
                continue
            row = c.execute(
                "SELECT reading, definitions FROM terms "
                "WHERE expression=? AND dict_id=? "
                "ORDER BY score DESC LIMIT 1",
                (word, d["id"])
            ).fetchone()
            if row:
                if result["reading"] is None:
                    result["reading"] = row[0]
                try:
                    defs = json.loads(row[1])
                    meaningful = [x for x in defs if x.strip()]
                    if meaningful:
                        result["definition"] = meaningful[0]
                except (json.JSONDecodeError, TypeError):
                    pass
                break

        return result

    def lookup_all(self, word):
        """Look up a word and return ALL definitions from all dicts.

        Returns dict with same shape as lookup(), plus:
            all_definitions — list of {"text": ..., "dict_name": ...}
        User words are checked first and appear at the top.
        """
        c = self.conn()
        result = {"reading": None, "pitch_code": None, "definition": None,
                  "all_definitions": []}

        # Check user words first (highest priority)
        uw = _user_word_lookup(word)
        if uw:
            if uw.get("reading"):
                result["reading"] = uw["reading"]
            if uw.get("pitch_code"):
                result["pitch_code"] = uw["pitch_code"]
            if uw.get("definition"):
                result["all_definitions"].append({
                    "text": uw["definition"],
                    "dict_name": "\u2605 User Words",
                })

        dicts = self.get_dictionaries()

        # Pitch (first match wins — skip if user words already provided)
        if not result["pitch_code"]:
            for d in dicts:
                if d["type"] not in ("pitch", "both"):
                    continue
                row = c.execute(
                    "SELECT reading, position FROM pitch_accents "
                    "WHERE expression=? AND dict_id=? LIMIT 1",
                    (word, d["id"])
                ).fetchone()
                if row:
                    result["pitch_code"] = _position_to_uf_code(row[1], row[0])
                    if result["reading"] is None:
                        result["reading"] = row[0]
                    break

        # Definitions — collect ALL across all term dicts
        # Store per-entry reading + pitch so dict-switch UI can update
        for d in dicts:
            if d["type"] not in ("term", "both"):
                continue
            rows = c.execute(
                "SELECT reading, definitions FROM terms "
                "WHERE expression=? AND dict_id=? "
                "ORDER BY score DESC",
                (word, d["id"])
            ).fetchall()
            for row in rows:
                entry_reading = row[0] or None
                if result["reading"] is None:
                    result["reading"] = entry_reading
                # Look up pitch for this entry's reading
                entry_pitch = ""
                if entry_reading:
                    pr = c.execute(
                        "SELECT position FROM pitch_accents "
                        "WHERE expression=? AND reading=? LIMIT 1",
                        (word, entry_reading)
                    ).fetchone()
                    if pr:
                        entry_pitch = _position_to_uf_code(
                            pr[0], entry_reading
                        )
                try:
                    defs = json.loads(row[1])
                    meaningful = [x for x in defs if x.strip()]
                    for defn in meaningful:
                        result["all_definitions"].append({
                            "text": defn,
                            "dict_name": d["name"],
                            "reading": entry_reading,
                            "pitch": entry_pitch,
                        })
                except (json.JSONDecodeError, TypeError):
                    pass

        if result["all_definitions"] and not result["definition"]:
            result["definition"] = result["all_definitions"][0]["text"]

        return result


_dict_db = None


def _get_dict_db():
    global _dict_db
    if _dict_db is None:
        _dict_db = _DictDB()
    return _dict_db


# ---------------------------------------------------------------------------
# User Words — personal dictionary stored as JSON, highest priority
# ---------------------------------------------------------------------------

def _user_words_path():
    """Path to user_words.json in user_files."""
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_files")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "user_words.json")


def _load_user_words():
    """Load the user words dict.  {word: {reading, pitch, tooltip}}."""
    p = _user_words_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_user_words(words):
    """Persist the user words dict."""
    p = _user_words_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)


def _user_word_lookup(word):
    """Look up a word in the user dictionary.

    Returns None if not found, otherwise a result dict.
    """
    uw = _load_user_words()
    entry = uw.get(word)
    if not entry:
        return None
    return {
        "reading": entry.get("reading") or None,
        "pitch_code": entry.get("pitch") or None,
        "definition": entry.get("tooltip") or None,
    }


def _save_user_word(word, reading, pitch, tooltip):
    """Save or update a word in the user dictionary."""
    uw = _load_user_words()
    uw[word] = {
        "reading": reading or "",
        "pitch": pitch or "",
        "tooltip": tooltip or "",
    }
    _save_user_words(uw)


# ---------------------------------------------------------------------------
# Dictionary lookup: annotation builder
# ---------------------------------------------------------------------------

def _build_annotation(word, result):
    """Build the UF annotation string from lookup result."""
    reading = result.get("reading")
    pitch = result.get("pitch_code")
    definition = result.get("definition")

    if not reading and not pitch and not definition:
        return None

    parts = []
    if reading:
        parts.append(reading)
    if pitch:
        parts.append(pitch)
    elif definition and reading:
        parts.append("?")
    if definition:
        clean_def = definition.replace(";", ",")
        if len(clean_def) > 200:
            clean_def = clean_def[:197] + "..."
        parts.append(clean_def)

    if not parts:
        return None
    return "%s{%s}" % (word, ";".join(parts))


# ---------------------------------------------------------------------------
# MeCab tokenizer integration (bundled binary — no pip install needed)
# ---------------------------------------------------------------------------

_mecab_process = None   # lazy subprocess.Popen singleton
_mecab_available = None  # None = not checked, True/False

_SUPPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "support")

# ipadic node format: surface\tPOS\tsub-POS\tlemma\treading  (tab-separated)
_MECAB_NODE_FMT = r"%m\t%f[0]\t%f[1]\t%f[6]\t%f[7]\n"
_MECAB_EOS_FMT = r"EOS\n"
_MECAB_UNK_FMT = r"%m\t%m\t*\t%m\t\n"

# (Skip/merge POS logic is now inline in _merge_tokens using pos+pos2)


def _mecab_cmd():
    """Build the MeCab command for the current platform."""
    from anki.utils import is_win, is_mac
    exe = os.path.join(_SUPPORT_DIR, "mecab")
    if is_win:
        exe = os.path.normpath(exe) + ".exe"
    elif not is_mac:
        exe += ".lin"
    return [
        exe,
        "--node-format=" + _MECAB_NODE_FMT,
        "--eos-format=" + _MECAB_EOS_FMT,
        "--unk-format=" + _MECAB_UNK_FMT,
        "-d", _SUPPORT_DIR,
        "-r", os.path.join(_SUPPORT_DIR, "mecabrc"),
    ]


def _check_mecab():
    """Check if the bundled MeCab binary is usable."""
    global _mecab_available
    if _mecab_available is not None:
        return _mecab_available
    try:
        cmd = _mecab_cmd()
        # Set library paths so the binary can find libmecab
        env = os.environ.copy()
        env["DYLD_LIBRARY_PATH"] = _SUPPORT_DIR
        env["LD_LIBRARY_PATH"] = _SUPPORT_DIR
        # Make sure the binary is executable (macOS/Linux)
        from anki.utils import is_win
        if not is_win:
            os.chmod(cmd[0], 0o755)
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            startupinfo=_si(),
        )
        p.stdin.write("\u30c6\u30b9\u30c8\n".encode("utf-8"))  # テスト
        p.stdin.flush()
        line = p.stdout.readline()
        p.terminate()
        _mecab_available = len(line) > 0
    except Exception:
        _mecab_available = False
    return _mecab_available


def _si():
    """Return STARTUPINFO on Windows to hide console window."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        try:
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        except AttributeError:
            pass
        return si
    return None


def _get_mecab():
    """Return a running MeCab subprocess (lazy singleton)."""
    global _mecab_process
    if _mecab_process is None or _mecab_process.poll() is not None:
        cmd = _mecab_cmd()
        env = os.environ.copy()
        env["DYLD_LIBRARY_PATH"] = _SUPPORT_DIR
        env["LD_LIBRARY_PATH"] = _SUPPORT_DIR
        from anki.utils import is_win
        if not is_win:
            os.chmod(cmd[0], 0o755)
        _mecab_process = subprocess.Popen(
            cmd,
            bufsize=-1,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            startupinfo=_si(),
        )
    return _mecab_process


def _tokenize_sentence_raw(text):
    """Get raw tokens from MeCab (before merging)."""
    mecab = _get_mecab()
    mecab.stdin.write(text.strip().encode("utf-8", "ignore") + b"\n")
    mecab.stdin.flush()

    tokens = []
    while True:
        line = mecab.stdout.readline().rstrip(b"\r\n").decode("utf-8", "replace")
        if not line or line == "EOS":
            break
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        surface = parts[0]
        pos1 = parts[1]        # e.g. 動詞, 助詞, 助動詞, 名詞
        pos2 = parts[2]        # e.g. 接続助詞, 自立, 非自立
        lemma = parts[3]
        reading_kata = parts[4]
        if not lemma or lemma == '*':
            lemma = surface
        reading_hira = _kata_to_hira(reading_kata) if reading_kata else surface
        tokens.append({
            "surface": surface,
            "lemma": lemma,
            "reading": reading_hira,
            "pos": pos1,
            "pos2": pos2,
        })
    return tokens


def _merge_tokens(tokens):
    """Merge conjugation fragments into whole words using POS/sub-POS.

    Uses MeCab's POS tags to decide what merges:
    - 助動詞 (auxiliary verbs) always merge onto preceding verb/adj
    - 助詞/接続助詞 (conjunctive particles like て/で) merge when
      followed by a non-independent verb (動詞/非自立) or 助動詞

    No surface forms are hardcoded — everything is driven by POS tags.
    """
    if not tokens:
        return tokens

    cfg = _get_config()
    skip_particles = cfg.get("skip_particles", True)

    # POS tags that can start a merge chain
    _HEAD_POS = {
        "\u52d5\u8a5e",    # 動詞
        "\u5f62\u5bb9\u8a5e",  # 形容詞
        "\u5f62\u72b6\u8a5e",  # 形状詞 (形容動詞 stem)
    }

    merged = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # If this is a verb/adj, try to absorb following aux tokens
        if tok["pos"] in _HEAD_POS:
            combined_surface = tok["surface"]
            combined_reading = tok["reading"]
            base_lemma = tok["lemma"]
            j = i + 1
            while j < len(tokens):
                nt = tokens[j]
                # Rule 1: 助動詞 always merges (た, ない, れる, ます, です, etc.)
                if nt["pos"] == "\u52a9\u52d5\u8a5e":  # 助動詞
                    combined_surface += nt["surface"]
                    combined_reading += nt["reading"]
                    j += 1
                # Rule 2: 接続助詞 (て/で/ちゃ) + non-independent verb/aux
                elif (nt["pos"] == "\u52a9\u8a5e"  # 助詞
                      and nt.get("pos2") == "\u63a5\u7d9a\u52a9\u8a5e"  # 接続助詞
                      and j + 1 < len(tokens)
                      and (tokens[j + 1]["pos"] in
                           ("\u52d5\u8a5e",       # 動詞
                            "\u52a9\u52d5\u8a5e")  # 助動詞
                           and tokens[j + 1].get("pos2") in
                           ("\u975e\u81ea\u7acb",  # 非自立
                            "*", None))):
                    # Absorb the particle and the following verb/aux
                    combined_surface += nt["surface"]
                    combined_reading += nt["reading"]
                    combined_surface += tokens[j + 1]["surface"]
                    combined_reading += tokens[j + 1]["reading"]
                    j += 2
                else:
                    break
            merged.append({
                "surface": combined_surface,
                "lemma": base_lemma,
                "reading": combined_reading,
                "pos": tok["pos"],
                "pos2": tok.get("pos2", "*"),
                "skip": False,
            })
            i = j
        else:
            # Determine skip status
            is_particle = tok["pos"] == "\u52a9\u8a5e"  # 助詞
            is_aux_verb = tok["pos"] == "\u52a9\u52d5\u8a5e"  # 助動詞
            is_symbol = tok["pos"] in (
                "\u8a18\u53f7",  # 記号
                "\u7a7a\u767d",  # 空白
                "\u88dc\u52a9\u8a18\u53f7",  # 補助記号
            )
            is_empty = not tok["surface"].strip()
            # ASCII/fullwidth-only tokens (punctuation, roman)
            is_non_jp = (tok["surface"].strip() and all(
                ord(c) < 0x3000 or ord(c) in range(0xFF01, 0xFF5F)
                for c in tok["surface"].strip()
            ))

            if is_symbol or is_empty or is_non_jp:
                skip = True
            elif is_particle and skip_particles:
                skip = True
            elif is_aux_verb:
                # Standalone 助動詞 that didn't merge (rare) — skip
                skip = True
            else:
                skip = False

            merged.append({
                "surface": tok["surface"],
                "lemma": tok["lemma"],
                "reading": tok["reading"],
                "pos": tok["pos"],
                "pos2": tok.get("pos2", "*"),
                "skip": skip,
            })
            i += 1
    return merged


def _tokenize_sentence(text):
    """Tokenize a Japanese sentence with the bundled MeCab binary.

    Returns list of dicts:
        surface  — the word as it appears in text
        lemma    — dictionary form
        reading  — kana reading (katakana → hiragana)
        pos      — top-level part of speech (e.g. 名詞, 動詞)
        skip     — True if this token should not be annotated
    """
    raw = _tokenize_sentence_raw(text)
    return _merge_tokens(raw)


def _kata_to_hira(text):
    """Convert katakana to hiragana."""
    result = []
    for ch in text:
        cp = ord(ch)
        if 0x30A1 <= cp <= 0x30F6:  # katakana ァ-ヶ
            result.append(chr(cp - 0x60))
        else:
            result.append(ch)
    return "".join(result)


def _is_sentence(text):
    """Heuristic: text is a sentence if it has >4 chars and looks Japanese."""
    # If MeCab is available and text is long enough, treat as sentence
    jp_chars = sum(
        1 for c in text
        if 0x3000 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF
    )
    return jp_chars >= 4


# ---------------------------------------------------------------------------
# Migaku format conversion helpers
# ---------------------------------------------------------------------------

_MIGAKU_RE = re.compile(r"(\S+?)\[([^\]]*)\]")

# Matches a Migaku space: ASCII space between two characters where at least
# one side is CJK/kana/fullwidth.
_MIGAKU_SPACE_RE = re.compile(
    r"(?<=[\u3000-\u9fff\u3040-\u309f\u30a0-\u30ff\uff00-\uffef]) "
    r"|"
    r" (?=[\u3000-\u9fff\u3040-\u309f\u30a0-\u30ff\uff00-\uffef])"
)


def _convert_migaku(text):
    """Convert Migaku word[reading;pitch] to UF word{reading;pitch} format.

    Handles:
      word[reading;pitch]   -> word{reading;pitch}
      word[,dictform;pitch] -> word{;pitch;dictform}  (conjugated)
      word[;pitch]          -> word{;pitch}            (no reading)
      word[reading]         -> word{reading}           (no pitch)
    Also removes Migaku-style spaces between Japanese characters.
    """
    def _replace(m):
        base = m.group(1)
        inside = m.group(2)
        # Conjugated form: starts with comma -> ,dictform;pitch
        if inside.startswith(","):
            rest = inside[1:]  # strip leading comma
            parts = rest.split(";", 1)
            if len(parts) == 2:
                dictform, pitch = parts
                return base + "{;" + pitch + ";" + dictform + "}"
            else:
                # Only dictform, no pitch
                return base + "{;;" + rest + "}"
        else:
            # Standard: reading;pitch or reading or ;pitch
            return base + "{" + inside + "}"

    # Convert brackets only.  Keep all Migaku spaces — they serve as
    # word boundaries that UF needs to separate annotations.
    return _MIGAKU_RE.sub(_replace, text)


def _strip_migaku(text):
    """Remove all Migaku [...] annotations and Migaku spaces from text."""
    result = _MIGAKU_RE.sub(r"\1", text)
    result = _MIGAKU_SPACE_RE.sub("", result)
    return result


# ---------------------------------------------------------------------------
# Editor integration: toolbar button + lookup
# ---------------------------------------------------------------------------

def _do_wrap_brackets(editor):
    """Wrap selected text in 【】 brackets."""
    editor.web.eval(
        "(function(){"
        "  var s = window.getSelection();"
        "  if (!s || !s.toString()) return;"
        "  var txt = s.toString();"
        "  document.execCommand('insertText', false, '\\u3010' + txt + '\\u3011');"
        "})()"
    )


def _do_convert_migaku(editor):
    """Convert Migaku brackets in selected text to UF format."""
    selected = (editor.web.selectedText() or "").strip()
    if not selected:
        return
    converted = _convert_migaku(selected)
    if converted != selected:
        js_text = json.dumps(converted)
        editor.web.eval(
            "(function(){"
            "  var s = window.getSelection();"
            "  if (!s || !s.toString()) return;"
            "  document.execCommand('insertText', false, " + js_text + ");"
            "})()"
        )


def _do_strip_migaku(editor):
    """Strip all Migaku [...] annotations from selected text."""
    selected = (editor.web.selectedText() or "").strip()
    if not selected:
        return
    stripped = _strip_migaku(selected)
    if stripped != selected:
        js_text = json.dumps(stripped)
        editor.web.eval(
            "(function(){"
            "  var s = window.getSelection();"
            "  if (!s || !s.toString()) return;"
            "  document.execCommand('insertText', false, " + js_text + ");"
            "})()"
        )


def _on_editor_did_init_buttons(buttons, editor):
    """Add toolbar buttons to the editor.  Each button is in its own
    try/except so a failure in one doesn't prevent the rest from loading."""
    _button_defs = [
        dict(
            cmd="uf_lookup",
            func=lambda ed: _do_lookup(ed),
            tip="Universal Furigana: Dictionary Lookup (Ctrl+Shift+F)",
            label="UF\u8f9e",
            keys="Ctrl+Shift+F",
        ),
        dict(
            cmd="uf_brackets",
            func=lambda ed: _do_wrap_brackets(ed),
            tip="Universal Furigana: Wrap in \u3010\u3011 (Ctrl+Shift+B)",
            label="\u3010\u3011",
            keys="Ctrl+Shift+B",
        ),
        dict(
            cmd="uf_migaku_convert",
            func=lambda ed: _do_convert_migaku(ed),
            tip="Universal Furigana: Convert Migaku [] to UF {}",
            label="[]\u2192{}",
        ),
        dict(
            cmd="uf_migaku_strip",
            func=lambda ed: _do_strip_migaku(ed),
            tip="Universal Furigana: Strip Migaku [] annotations",
            label="[\u00d7]",
        ),
    ]
    for bdef in _button_defs:
        try:
            b = editor.addButton(icon=None, **bdef)
            buttons.append(b)
        except Exception as exc:
            sys.stdout.write(
                "[UF] editor button '%s' error: %s\n" % (bdef.get('cmd', '?'), exc)
            )


def _do_lookup(editor):
    """Perform dictionary lookup on selected text in editor."""
    # Use synchronous selectedText() to avoid stale/cached selection
    # from previous field or card that evalWithCallback can return.
    selected = (editor.web.selectedText() or "").strip()
    _handle_lookup_result(editor, selected)


def _handle_lookup_result(editor, selected_text):
    """Handle the lookup after getting selected text."""
    if not selected_text:
        from aqt.utils import showInfo
        showInfo(
            "Select some text first, then click the lookup button."
        )
        return

    db = _get_dict_db()
    field_idx = editor.currentField

    # Decide: single-word mode or sentence mode
    use_sentence_mode = False
    if _check_mecab() and _is_sentence(selected_text):
        # Try single-word first; if no result, fall through to sentence
        single = db.lookup(selected_text)
        if not single["reading"] and not single["pitch_code"]:
            use_sentence_mode = True
        else:
            # Exact match found — use single-word mode
            pass

    if use_sentence_mode:
        _handle_sentence_lookup(editor, selected_text, field_idx)
        return

    # --- Single-word mode ---
    result = db.lookup_all(selected_text)

    if (not result["reading"] and not result["pitch_code"]
            and not result["all_definitions"]):
        # If MeCab is available, try lemma (dictionary form)
        if _check_mecab():
            tokens = _tokenize_sentence(selected_text)
            # If it tokenized to 1 content token, try its lemma
            content = [t for t in tokens if not t["skip"]]
            if len(content) == 1 and content[0]["lemma"] != selected_text:
                result = db.lookup_all(content[0]["lemma"])
                if result["reading"] is None:
                    result["reading"] = content[0]["reading"]

    # Even if no results found, open the dialog so the user can
    # manually enter reading / pitch / definition.

    dialog = _LookupPreviewDialog(
        editor.parentWindow, selected_text, result
    )
    if dialog.exec():
        # Save user edits to user_words.json
        dialog.save_user_edit()
        annotation = dialog.get_annotation()
        if annotation:
            # Use execCommand to replace the *currently selected* text
            # in the editor webview.  This respects the cursor position
            # so if the same word appears multiple times only the
            # highlighted occurrence is replaced.
            # Pad with spaces so the annotation doesn't merge into
            # adjacent text.  Double spaces are harmless.
            padded = " " + annotation + " "
            js_ann = json.dumps(padded)
            editor.web.eval(
                "(function(){"
                "  var s = window.getSelection();"
                "  if (!s || !s.rangeCount || !s.toString()) return;"
                "  document.execCommand('insertText', false, " + js_ann + ");"
                "})()"
            )
            # Sync the webview change back into the note object
            editor.saveNow(lambda: None)


def _insert_with_spaces(html, old, new):
    """Replace *old* with *new* in *html*, adding a space before/after
    the annotation when the neighboring character is not already a space,
    newline, or tag boundary.  This prevents {annotations} from merging
    into adjacent text."""
    idx = html.find(old)
    if idx == -1:
        return html
    before = html[:idx]
    after = html[idx + len(old):]
    # Add space before if needed
    if before and before[-1] not in (' ', '\n', '\t', '>', '\u3000'):
        before += ' '
    # Add space after if needed
    if after and after[0] not in (' ', '\n', '\t', '<', '\u3000'):
        new = new + ' '
    return before + new + after


# ---------------------------------------------------------------------------
# Single-word dialog helper (used when user wants to treat selection as one word)
# ---------------------------------------------------------------------------

def _open_single_word_dialog(editor, word):
    """Open the single-word LookupPreviewDialog for *word*.

    Looks up the word in the dictionary first; if nothing is found the
    dialog still opens with empty fields so the user can type manually.
    """
    db = _get_dict_db()
    result = db.lookup_all(word)

    # Also try lemma via MeCab if no hit on the surface
    if (not result["reading"] and not result["pitch_code"]
            and not result["all_definitions"] and _check_mecab()):
        tokens = _tokenize_sentence(word)
        content = [t for t in tokens if not t["skip"]]
        if len(content) == 1 and content[0]["lemma"] != word:
            lemma_result = db.lookup_all(content[0]["lemma"])
            if lemma_result["reading"] or lemma_result["pitch_code"]:
                result = lemma_result
            if not result["reading"] and content[0]["reading"]:
                result["reading"] = content[0]["reading"]

    dialog = _LookupPreviewDialog(editor.parentWindow, word, result)
    if dialog.exec():
        dialog.save_user_edit()
        annotation = dialog.get_annotation()
        if annotation:
            padded = " " + annotation + " "
            js_ann = json.dumps(padded)
            editor.web.eval(
                "(function(){"
                "  var s = window.getSelection();"
                "  if (!s || !s.rangeCount || !s.toString()) return;"
                "  document.execCommand('insertText', false, " + js_ann + ");"
                "})()"
            )
            editor.saveNow(lambda: None)


# ---------------------------------------------------------------------------
# Sentence lookup: tokenize → lookup each word → preview all
# ---------------------------------------------------------------------------

def _handle_sentence_lookup(editor, sentence, field_idx):
    """Tokenize a sentence and look up each content word."""
    db = _get_dict_db()
    tokens = _tokenize_sentence(sentence)

    # Build word list with lookup results
    word_results = []
    for tok in tokens:
        if tok["skip"]:
            word_results.append({
                "surface": tok["surface"],
                "lemma": tok["lemma"],
                "skip": True,
                "result": None,
                "enabled": False,
            })
            continue

        # Try surface form first
        result = db.lookup_all(tok["surface"])

        # If no match on surface, try the lemma (dictionary form)
        # but only if lemma is different from surface
        used_lemma = False
        if (not result["reading"] and not result["pitch_code"]
                and tok["lemma"] != tok["surface"]):
            lemma_result = db.lookup_all(tok["lemma"])
            if lemma_result["reading"] or lemma_result["pitch_code"]:
                result = lemma_result
                used_lemma = True

        # If still no reading from DB, use MeCab's reading
        if not result["reading"] and tok["reading"]:
            result["reading"] = tok["reading"]

        has_data = bool(
            result["reading"] or result["pitch_code"]
            or result["definition"]
        )

        word_results.append({
            "surface": tok["surface"],
            "lemma": tok["lemma"],
            "skip": False,
            "result": result,
            "enabled": has_data,
            "used_lemma": used_lemma,
        })

    # Check if we found anything at all
    any_found = any(w["enabled"] for w in word_results)
    if not any_found:
        # No sentence results — fall through to single-word mode
        # so the user can manually annotate the full selection.
        _open_single_word_dialog(editor, sentence)
        return

    dialog = _SentenceLookupDialog(
        editor.parentWindow, sentence, word_results
    )
    ret = dialog.exec()
    if getattr(dialog, "use_single_word", False):
        # User clicked "Single Word" — open the single-word dialog
        _open_single_word_dialog(editor, sentence)
        return
    if ret:
        # Save any user edits to user_words.json
        dialog.save_user_edits()
        annotated = dialog.get_annotated_sentence()
        if annotated:
            # Use execCommand to replace the *currently selected* text
            # so the correct occurrence is targeted when duplicates exist.
            padded = " " + annotated + " "
            js_ann = json.dumps(padded)
            editor.web.eval(
                "(function(){"
                "  var s = window.getSelection();"
                "  if (!s || !s.rangeCount || !s.toString()) return;"
                "  document.execCommand('insertText', false, " + js_ann + ");"
                "})()"
            )
            # Sync the webview change back into the note object
            editor.saveNow(lambda: None)


class _SentenceLookupDialog(QDialog):
    """Sentence-mode lookup dialog.

    Columns: \u2713 | Word | Dictionary | Reading | Pitch | Tooltip
    - Dictionary is a dropdown of available definitions (from all dicts).
      Changing it populates the Tooltip field.
    - Reading, Pitch, Tooltip are editable inline.
    - On Insert, any word the user edited is saved to user_words.json.
    """

    def __init__(self, parent, sentence, word_results):
        super().__init__(parent)
        self.setWindowTitle("Sentence Lookup")
        self.setMinimumWidth(820)
        self.setMinimumHeight(400)
        self.sentence = sentence
        self.word_results = word_results
        self._rows = []  # list of row widget dicts
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "<b>Sentence mode:</b> check the words you want to "
            "annotate, edit reading / pitch / tooltip, then click Insert."
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info)

        # Scrollable word grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        grid = QGridLayout(scroll_widget)
        grid.setContentsMargins(4, 4, 4, 4)

        # Headers
        headers = ["\u2713", "Word", "Dictionary", "Reading", "Pitch", "Tooltip"]
        for col, hdr in enumerate(headers):
            lbl = QLabel("<b>%s</b>" % hdr)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            grid.addWidget(lbl, 0, col)

        row_num = 1
        for w in self.word_results:
            if w["skip"]:
                continue

            cb = QCheckBox()
            cb.setChecked(w["enabled"])

            surface_lbl = QLabel(w["surface"])
            font = surface_lbl.font()
            font.setBold(True)
            surface_lbl.setFont(font)
            if w["lemma"] != w["surface"]:
                surface_lbl.setToolTip(
                    "Dictionary form: %s" % w["lemma"]
                )

            result = w["result"] or {}
            all_defs = result.get("all_definitions") or []
            first_def = result.get("definition") or ""

            # Dictionary dropdown (shows [DictName] definition)
            dict_combo = QComboBox()
            dict_combo.setMinimumWidth(180)
            dict_combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            if all_defs:
                for d in all_defs:
                    label = d["text"]
                    if len(label) > 60:
                        label = label[:57] + "..."
                    src = d.get("dict_name", "")
                    if src:
                        label = "[%s] %s" % (src, label)
                    dict_combo.addItem(label, d["text"])
            dict_combo.addItem("(none)")

            # Reading / Pitch / Tooltip fields
            reading_edit = QLineEdit(result.get("reading") or "")
            reading_edit.setPlaceholderText("reading")
            reading_edit.setMaximumWidth(120)

            pitch_edit = QLineEdit(result.get("pitch_code") or "")
            pitch_edit.setPlaceholderText("h/a/o/nX")
            pitch_edit.setMaximumWidth(70)

            tooltip_edit = QLineEdit(first_def)
            tooltip_edit.setPlaceholderText("tooltip text")

            # When dictionary selection changes, update all fields
            def _on_dict_change(
                index, defs=all_defs, tip=tooltip_edit,
                rdg=reading_edit, pit=pitch_edit
            ):
                if index < 0 or index >= len(defs):
                    tip.clear()
                    return
                entry = defs[index]
                tip.setText(entry["text"])
                r = entry.get("reading") or ""
                p = entry.get("pitch") or ""
                if r:
                    rdg.setText(r)
                if p:
                    pit.setText(p)
            dict_combo.currentIndexChanged.connect(_on_dict_change)

            grid.addWidget(cb, row_num, 0)
            grid.addWidget(surface_lbl, row_num, 1)
            grid.addWidget(dict_combo, row_num, 2)
            grid.addWidget(reading_edit, row_num, 3)
            grid.addWidget(pitch_edit, row_num, 4)
            grid.addWidget(tooltip_edit, row_num, 5)

            self._rows.append({
                "surface": w["surface"],
                "lemma": w["lemma"],
                "cb": cb,
                "dict_combo": dict_combo,
                "reading": reading_edit,
                "pitch": pitch_edit,
                "tooltip": tooltip_edit,
                # Remember original values to detect user edits
                "orig_reading": result.get("reading") or "",
                "orig_pitch": result.get("pitch_code") or "",
                "orig_tooltip": first_def,
            })
            row_num += 1

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Buttons
        bl = QHBoxLayout()
        single_btn = QPushButton("Single Word")
        single_btn.setToolTip(
            "Treat the entire selection as one word instead of a sentence"
        )
        single_btn.clicked.connect(self._use_single_word)
        bl.addWidget(single_btn)
        bl.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        insert_btn = QPushButton("Insert")
        insert_btn.clicked.connect(self.accept)
        insert_btn.setDefault(True)
        bl.addWidget(cancel_btn)
        bl.addWidget(insert_btn)
        layout.addLayout(bl)

    def _use_single_word(self):
        """Signal that the user wants single-word mode instead."""
        self.use_single_word = True
        self.reject()

    def save_user_edits(self):
        """Save any row where the user changed reading/pitch/tooltip."""
        for r in self._rows:
            if not r["cb"].isChecked():
                continue
            reading = r["reading"].text().strip()
            pitch = r["pitch"].text().strip()
            tooltip = r["tooltip"].text().strip()
            changed = (
                reading != r["orig_reading"]
                or pitch != r["orig_pitch"]
                or tooltip != r["orig_tooltip"]
            )
            if changed and (reading or pitch or tooltip):
                _save_user_word(r["surface"], reading, pitch, tooltip)

    def get_annotated_sentence(self):
        """Build annotated sentence, walking token-by-token.

        Adds a space before each annotated word so annotations don't
        merge into surrounding text in the output.
        """
        # Build surface → annotation map for checked rows
        replacements = {}  # surface → annotation string
        for r in self._rows:
            if not r["cb"].isChecked():
                continue
            reading = r["reading"].text().strip()
            pitch = r["pitch"].text().strip()
            tooltip = r["tooltip"].text().strip()
            result = {
                "reading": reading or None,
                "pitch_code": pitch or None,
                "definition": tooltip or None,
            }
            ann = _build_annotation(r["surface"], result)
            if ann:
                replacements[r["surface"]] = ann

        if not replacements:
            return self.sentence

        # Walk through the sentence left-to-right, matching surfaces.
        # Insert a space before annotated words so they don't glue.
        text = self.sentence
        out_parts = []
        pos = 0
        # Sort surfaces longest-first for greedy matching
        surfaces = sorted(replacements.keys(), key=len, reverse=True)
        used = set()  # track which surfaces have been replaced (once each)
        while pos < len(text):
            matched = False
            for surf in surfaces:
                if surf in used:
                    continue
                if text[pos:pos + len(surf)] == surf:
                    if out_parts and not out_parts[-1].endswith(" "):
                        out_parts.append(" ")
                    out_parts.append(replacements[surf])
                    out_parts.append(" ")
                    pos += len(surf)
                    used.add(surf)
                    matched = True
                    break
            if not matched:
                out_parts.append(text[pos])
                pos += 1

        return "".join(out_parts).strip()


class _LookupPreviewDialog(QDialog):
    """Preview dialog showing lookup results before inserting."""

    def __init__(self, parent, word, result):
        super().__init__(parent)
        self.setWindowTitle("Dictionary Lookup \u2014 %s" % word)
        self.setMinimumWidth(480)
        self.word = word
        self.result = result
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        word_label = QLabel("<h2>%s</h2>" % self.word)
        word_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(word_label)

        # Reading
        rg = QGroupBox("Reading")
        rl = QHBoxLayout(rg)
        self.reading_edit = QLineEdit()
        self.reading_edit.setText(self.result.get("reading") or "")
        self.reading_edit.setPlaceholderText("e.g. \u305f\u3079\u308b")
        rl.addWidget(self.reading_edit)
        layout.addWidget(rg)

        # Pitch
        pg = QGroupBox("Pitch Accent")
        pl = QHBoxLayout(pg)
        self.pitch_edit = QLineEdit()
        self.pitch_edit.setText(self.result.get("pitch_code") or "")
        self.pitch_edit.setPlaceholderText("h / a / o / nX")
        pl.addWidget(self.pitch_edit)
        pl.addWidget(QLabel(
            "<small>h=heiban, a=atamadaka, o=odaka, nX=nakadaka</small>"
        ))
        layout.addWidget(pg)

        # Dictionary selector dropdown
        all_defs = self.result.get("all_definitions") or []
        self._all_defs = all_defs  # store for _on_dict_change
        if all_defs:
            dg = QGroupBox("Dictionary")
            dl = QVBoxLayout(dg)
            self.dict_combo = QComboBox()
            self.dict_combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            for d in all_defs:
                label = d["text"]
                if len(label) > 80:
                    label = label[:77] + "..."
                src = d.get("dict_name", "")
                if src:
                    label = "[%s] %s" % (src, label)
                self.dict_combo.addItem(label, d["text"])
            self.dict_combo.addItem("(none)")
            dl.addWidget(self.dict_combo)
            layout.addWidget(dg)

            # When dictionary selection changes, update all fields
            def _on_dict_change(index):
                if index < 0 or index >= len(self._all_defs):
                    self.def_edit.clear()
                    return
                entry = self._all_defs[index]
                self.def_edit.setPlainText(entry["text"])
                rdg = entry.get("reading") or ""
                pit = entry.get("pitch") or ""
                if rdg:
                    self.reading_edit.setText(rdg)
                if pit:
                    self.pitch_edit.setText(pit)
            self.dict_combo.currentIndexChanged.connect(_on_dict_change)
        else:
            self.dict_combo = None

        # Definition / Tooltip (editable)
        tg = QGroupBox("Definition / Tooltip")
        tl = QVBoxLayout(tg)
        self.def_edit = QTextEdit()
        self.def_edit.setPlainText(self.result.get("definition") or "")
        self.def_edit.setPlaceholderText("English definition or notes...")
        self.def_edit.setMaximumHeight(100)
        tl.addWidget(self.def_edit)
        layout.addWidget(tg)

        # Preview
        self.preview_label = QLabel()
        self.preview_label.setTextFormat(Qt.TextFormat.RichText)
        self._update_preview()
        layout.addWidget(self.preview_label)

        self.reading_edit.textChanged.connect(self._update_preview)
        self.pitch_edit.textChanged.connect(self._update_preview)
        self.def_edit.textChanged.connect(self._update_preview)

        # Buttons
        bl = QHBoxLayout()
        bl.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        insert_btn = QPushButton("Insert")
        insert_btn.clicked.connect(self.accept)
        insert_btn.setDefault(True)
        bl.addWidget(cancel_btn)
        bl.addWidget(insert_btn)
        layout.addLayout(bl)

    def _update_preview(self):
        ann = self.get_annotation()
        if ann:
            self.preview_label.setText(
                "<b>Preview:</b> <code>%s</code>"
                % ann.replace("<", "&lt;")
            )
        else:
            self.preview_label.setText(
                "<b>Preview:</b> <i>(no annotation)</i>"
            )

    def save_user_edit(self):
        """Save user edits to user_words.json if anything was changed."""
        reading = self.reading_edit.text().strip()
        pitch = self.pitch_edit.text().strip()
        tooltip = self.def_edit.toPlainText().strip()
        orig_r = (self.result.get("reading") or "")
        orig_p = (self.result.get("pitch_code") or "")
        orig_d = (self.result.get("definition") or "")
        changed = (reading != orig_r or pitch != orig_p or tooltip != orig_d)
        if changed and (reading or pitch or tooltip):
            _save_user_word(self.word, reading, pitch, tooltip)

    def get_annotation(self):
        reading = self.reading_edit.text().strip()
        pitch = self.pitch_edit.text().strip()
        definition = self.def_edit.toPlainText().strip()
        r = {
            "reading": reading or None,
            "pitch_code": pitch or None,
            "definition": definition or None,
        }
        return _build_annotation(self.word, r)


# Register editor hook — try new-style first, fall back to legacy
try:
    gui_hooks.editor_did_init_buttons.append(_on_editor_did_init_buttons)
except AttributeError:
    # Very old Anki without this hook — use legacy filter
    from anki.hooks import addHook
    def _legacy_setup_buttons(buttons, editor):
        _on_editor_did_init_buttons(buttons, editor)
        return buttons
    addHook("setupEditorButtons", _legacy_setup_buttons)


# ---------------------------------------------------------------------------
# Dictionary manager widget (for settings dialog)
# ---------------------------------------------------------------------------

class _DictManagerWidget(QWidget):
    """Widget for managing imported dictionaries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        info = QLabel(
            "Import Yomitan / Yomichan dictionary .zip files to enable "
            "automatic lookup of readings, pitch accent, and definitions.\n"
            "Dictionaries are searched in priority order "
            "(top = highest priority, first match wins)."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.dict_list = QListWidget()
        self.dict_list.setMinimumHeight(140)
        layout.addWidget(self.dict_list)

        bl = QHBoxLayout()
        import_btn = QPushButton("Import .zip\u2026")
        import_btn.clicked.connect(self._on_import)
        bl.addWidget(import_btn)

        up_btn = QPushButton("\u25B2 Up")
        up_btn.clicked.connect(self._on_move_up)
        bl.addWidget(up_btn)

        down_btn = QPushButton("\u25BC Down")
        down_btn.clicked.connect(self._on_move_down)
        bl.addWidget(down_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._on_remove)
        bl.addWidget(remove_btn)

        bl.addStretch()
        layout.addLayout(bl)

    def _refresh_list(self):
        self.dict_list.clear()
        db = _get_dict_db()
        for d in db.get_dictionaries():
            type_label = {
                "term": "\U0001F4D6 Definitions",
                "pitch": "\U0001F3B5 Pitch",
                "both": "\U0001F4D6+\U0001F3B5 Both",
            }
            label = "%s  \u2014  %s  (%d entries)" % (
                d["name"],
                type_label.get(d["type"], d["type"]),
                d["entry_count"],
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, d["id"])
            self.dict_list.addItem(item)

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Yomitan Dictionary", "",
            "Yomitan Dictionary (*.zip);;All Files (*)"
        )
        if not path:
            return

        progress = QProgressDialog(
            "Importing dictionary...", "Cancel", 0, 100, self
        )
        progress.setWindowTitle("Importing")
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def progress_cb(done, total):
            if total > 0:
                progress.setValue(int(done / total * 100))
            QApplication.processEvents()

        try:
            db = _get_dict_db()
            name = db.import_dictionary(path, progress_cb)
            progress.close()
            QMessageBox.information(
                self, "Import Complete",
                "Successfully imported: %s" % name
            )
            self._refresh_list()
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Import Failed", str(e))

    def _get_selected_id(self):
        item = self.dict_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_remove(self):
        dict_id = self._get_selected_id()
        if dict_id is None:
            return
        reply = QMessageBox.question(
            self, "Remove Dictionary",
            "Are you sure you want to remove this dictionary?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            _get_dict_db().delete_dictionary(dict_id)
            self._refresh_list()

    def _on_move_up(self):
        self._swap_priority(-1)

    def _on_move_down(self):
        self._swap_priority(1)

    def _swap_priority(self, direction):
        row = self.dict_list.currentRow()
        if row < 0:
            return
        new_row = row + direction
        if new_row < 0 or new_row >= self.dict_list.count():
            return
        db = _get_dict_db()
        dicts = db.get_dictionaries()
        if row >= len(dicts) or new_row >= len(dicts):
            return
        id_a, pri_a = dicts[row]["id"], dicts[row]["priority"]
        id_b, pri_b = dicts[new_row]["id"], dicts[new_row]["priority"]
        db.set_priority(id_a, pri_b)
        db.set_priority(id_b, pri_a)
        self._refresh_list()
        self.dict_list.setCurrentRow(new_row)


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# User Words manager widget (for settings dialog)
# ---------------------------------------------------------------------------

class _UserWordsManagerWidget(QWidget):
    """Widget for viewing/editing/adding user words."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.word_list = QListWidget()
        self.word_list.setMinimumHeight(200)
        self.word_list.currentItemChanged.connect(self._on_select)
        layout.addWidget(self.word_list)

        # Edit area
        edit_group = QGroupBox("Edit Word")
        eg = QGridLayout(edit_group)
        eg.addWidget(QLabel("Word:"), 0, 0)
        self.word_edit = QLineEdit()
        eg.addWidget(self.word_edit, 0, 1)
        eg.addWidget(QLabel("Reading:"), 1, 0)
        self.reading_edit = QLineEdit()
        self.reading_edit.setPlaceholderText("hiragana reading")
        eg.addWidget(self.reading_edit, 1, 1)
        eg.addWidget(QLabel("Pitch:"), 2, 0)
        self.pitch_edit = QLineEdit()
        self.pitch_edit.setPlaceholderText("h / a / o / nX")
        eg.addWidget(self.pitch_edit, 2, 1)
        eg.addWidget(QLabel("Tooltip:"), 3, 0)
        self.tooltip_edit = QLineEdit()
        self.tooltip_edit.setPlaceholderText("definition or notes")
        eg.addWidget(self.tooltip_edit, 3, 1)
        layout.addWidget(edit_group)

        bl = QHBoxLayout()
        add_btn = QPushButton("Add / Update")
        add_btn.clicked.connect(self._on_add)
        bl.addWidget(add_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._on_remove)
        bl.addWidget(remove_btn)
        bl.addStretch()
        layout.addLayout(bl)

    def _refresh_list(self):
        self.word_list.clear()
        uw = _load_user_words()
        for word, entry in sorted(uw.items()):
            parts = []
            if entry.get("reading"):
                parts.append(entry["reading"])
            if entry.get("pitch"):
                parts.append(entry["pitch"])
            if entry.get("tooltip"):
                tip = entry["tooltip"]
                if len(tip) > 40:
                    tip = tip[:37] + "..."
                parts.append(tip)
            label = "%s  \u2014  %s" % (word, "; ".join(parts)) if parts else word
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, word)
            self.word_list.addItem(item)

    def _on_select(self, current, _prev):
        if not current:
            return
        word = current.data(Qt.ItemDataRole.UserRole)
        uw = _load_user_words()
        entry = uw.get(word, {})
        self.word_edit.setText(word)
        self.reading_edit.setText(entry.get("reading", ""))
        self.pitch_edit.setText(entry.get("pitch", ""))
        self.tooltip_edit.setText(entry.get("tooltip", ""))

    def _on_add(self):
        word = self.word_edit.text().strip()
        if not word:
            QMessageBox.warning(self, "No word", "Enter a word first.")
            return
        reading = self.reading_edit.text().strip()
        pitch = self.pitch_edit.text().strip()
        tooltip = self.tooltip_edit.text().strip()
        _save_user_word(word, reading, pitch, tooltip)
        self._refresh_list()

    def _on_remove(self):
        item = self.word_list.currentItem()
        if not item:
            return
        word = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Remove Word",
            "Remove \u201c%s\u201d from user words?" % word,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            uw = _load_user_words()
            uw.pop(word, None)
            _save_user_words(uw)
            self._refresh_list()
            self.word_edit.clear()
            self.reading_edit.clear()
            self.pitch_edit.clear()
            self.tooltip_edit.clear()


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
        self.setMinimumWidth(580)
        self.cfg = _get_config()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ---- Tab 1: General Settings ----
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)

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
            "<code>\u98df\u3079\u308b{\u305f\u3079\u308b;?;to eat}</code> \u2192 reading + tooltip (no pitch)<br>"
            "<code>\u3077\u3063\u3064\u308a{n3;snapping}</code> \u2192 pitch-only + tooltip<br>"
            "Hover on desktop or tap on mobile to see the description.<br>"
            "Tap elsewhere to dismiss on mobile.<br><br>"
            "<b>Hidden Furigana (self-test mode)</b><br>"
            "Add <code>!</code> before the reading to blur it until hover/tap:<br>"
            "<code>\u98df\u3079\u308b{!\u305f\u3079\u308b}</code> \u2192 furigana hidden until hover/tap<br>"
            "<code>\u79cb{!\u3042\u304d;a}</code> \u2192 hidden reading + pitch<br>"
            "Works with all combinations \u2014 tooltips still show normally.<br><br>"
            "Pitch accent shows colored lines above the furigana:<br>"
            "\u25aa A <b>top line</b> marks high-pitch mora<br>"
            "\u25aa A <b>vertical step</b> marks where the pitch drops<br>"
            "\u25aa No hover needed \u2014 the pattern is always visible"
        )
        info_text.setWordWrap(True)
        info_text.setTextFormat(Qt.TextFormat.RichText)
        info_layout.addWidget(info_text)
        general_layout.addWidget(info_group)

        # -- Enable / Disable --
        self.enabled_cb = QCheckBox("Enable furigana conversion")
        self.enabled_cb.setChecked(self.cfg.get("enabled", True))
        general_layout.addWidget(self.enabled_cb)

        general_layout.addStretch()

        tabs.addTab(general_tab, "General")

        # ---- Tab 2: Appearance ----
        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout(appearance_tab)

        self.pitch_cb = QCheckBox("Enable pitch accent visualization")
        self.pitch_cb.setChecked(self.cfg.get("pitch_accent_enabled", True))
        appearance_layout.addWidget(self.pitch_cb)

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

        appearance_layout.addWidget(color_group)

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
        appearance_layout.addWidget(font_group)

        # -- Word Coloring --
        color_word_group = QGroupBox("Word Coloring")
        cw_layout = QVBoxLayout(color_word_group)

        self.cw_enabled_cb = QCheckBox("Enable pitch-colored words")
        self.cw_enabled_cb.setChecked(self.cfg.get("color_words_enabled", False))

        self.cw_furigana_cb = QCheckBox("Color furigana / reading")
        self.cw_furigana_cb.setChecked(self.cfg.get("color_words_furigana", True))

        self.cw_kanji_cb = QCheckBox("Color kanji / base text")
        self.cw_kanji_cb.setChecked(self.cfg.get("color_words_kanji", False))

        def _update_cw_state():
            enabled = self.cw_enabled_cb.isChecked()
            self.cw_furigana_cb.setEnabled(enabled)
            self.cw_kanji_cb.setEnabled(enabled)

        self.cw_enabled_cb.stateChanged.connect(lambda: _update_cw_state())
        _update_cw_state()

        cw_layout.addWidget(self.cw_enabled_cb)
        cw_layout.addWidget(self.cw_furigana_cb)
        cw_layout.addWidget(self.cw_kanji_cb)

        appearance_layout.addWidget(color_word_group)
        appearance_layout.addStretch()

        tabs.addTab(appearance_tab, "Appearance")

        # ---- Tab 3: Dictionary Lookup ----
        dict_tab = QWidget()
        dict_layout = QVBoxLayout(dict_tab)

        dict_info = QLabel(
            "<b>Dictionary Lookup</b><br>"
            "Import Yomitan / Yomichan dictionary .zip files below. "
            "Then in the card editor, highlight a word (or a whole "
            "sentence) and press "
            "<b>Ctrl+Shift+F</b> (or click the <b>UF\u8f9e</b> button) "
            "to auto-fill reading, pitch accent, and definition."
        )
        dict_info.setWordWrap(True)
        dict_info.setTextFormat(Qt.TextFormat.RichText)
        dict_layout.addWidget(dict_info)

        self._dict_manager = _DictManagerWidget()
        dict_layout.addWidget(self._dict_manager)

        # -- MeCab sentence mode --
        mecab_group = QGroupBox(
            "Sentence Mode (MeCab \u2014 Japanese Tokenizer)"
        )
        mecab_layout = QVBoxLayout(mecab_group)

        mecab_status = (
            "\u2705 MeCab is bundled and working."
            if _check_mecab()
            else "\u274C MeCab binary could not be loaded. "
                 "Sentence mode may not work on this platform."
        )
        mecab_label = QLabel(mecab_status)
        mecab_label.setTextFormat(Qt.TextFormat.RichText)
        mecab_label.setWordWrap(True)
        mecab_layout.addWidget(mecab_label)

        mecab_desc = QLabel(
            "Highlight a sentence in the card editor and "
            "press <b>Ctrl+Shift+F</b>. The add-on will "
            "tokenize the sentence with MeCab, look up each "
            "content word, handle conjugated forms, and show "
            "a dialog where you can check/uncheck which words "
            "to annotate."
        )
        mecab_desc.setTextFormat(Qt.TextFormat.RichText)
        mecab_desc.setWordWrap(True)
        mecab_layout.addWidget(mecab_desc)

        self.skip_particles_cb = QCheckBox(
            "Skip particles (\u52a9\u8a5e) like \u306e, \u306b, \u3092, \u304c, etc."
        )
        self.skip_particles_cb.setChecked(
            self.cfg.get("skip_particles", True)
        )
        mecab_layout.addWidget(self.skip_particles_cb)

        dict_layout.addWidget(mecab_group)
        dict_layout.addStretch()

        tabs.addTab(dict_tab, "Dictionary Lookup")

        # ---- Tab 3: User Words ----
        uw_tab = QWidget()
        uw_layout = QVBoxLayout(uw_tab)

        uw_info = QLabel(
            "Words you edit in the lookup dialogs are automatically "
            "saved here. User words have the <b>highest priority</b> "
            "\u2014 they override all imported dictionaries.\n\n"
            "You can also add or edit words manually below."
        )
        uw_info.setWordWrap(True)
        uw_layout.addWidget(uw_info)

        self._uw_manager = _UserWordsManagerWidget()
        uw_layout.addWidget(self._uw_manager)

        tabs.addTab(uw_tab, "User Words")

        # ---- Tab 5: Mobile ----
        mobile_tab = QWidget()
        mobile_tab_layout = QVBoxLayout(mobile_tab)

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

        mobile_tab_layout.addWidget(mobile_group)
        mobile_tab_layout.addStretch()

        tabs.addTab(mobile_tab, "Mobile")

        # -- Buttons (below tabs) --
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
        self.cfg["skip_particles"] = self.skip_particles_cb.isChecked()
        for key, btn in self._color_buttons.items():
            self.cfg[key] = btn.color()

        self.cfg["color_words_enabled"] = self.cw_enabled_cb.isChecked()
        self.cfg["color_words_furigana"] = self.cw_furigana_cb.isChecked()
        self.cfg["color_words_kanji"] = self.cw_kanji_cb.isChecked()

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
        self.cw_enabled_cb.setChecked(False)
        self.cw_furigana_cb.setChecked(True)
        self.cw_kanji_cb.setChecked(False)
        for cb in self._template_cbs.values():
            cb.setChecked(False)


def _open_settings():
    dialog = SettingsDialog(mw)
    dialog.exec()


# ---------------------------------------------------------------------------
# Bulk Migaku conversion dialog
# ---------------------------------------------------------------------------

class _BulkMigakuDialog(QDialog):
    """Dialog to bulk-convert or strip Migaku annotations across notes."""

    def __init__(self, parent, mode="convert"):
        super().__init__(parent)
        self._mode = mode  # "convert" or "strip"
        if mode == "convert":
            self.setWindowTitle("Bulk Convert Migaku -> UF")
        else:
            self.setWindowTitle("Bulk Strip Migaku Annotations")
        self.setMinimumSize(600, 500)
        self._matched_nids = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Search section
        search_group = QGroupBox("Search")
        sg_layout = QVBoxLayout(search_group)
        sg_layout.addWidget(QLabel(
            "Enter an Anki search query to find notes with Migaku annotations.\n"
            "Leave empty to search all notes."
        ))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("e.g.  deck:Japanese  or  tag:migaku")
        sg_layout.addWidget(self._search_edit)
        self._search_btn = QPushButton("Search")
        self._search_btn.clicked.connect(self._on_search)
        sg_layout.addWidget(self._search_btn)
        layout.addWidget(search_group)

        # Preview section
        preview_group = QGroupBox("Preview")
        pg_layout = QVBoxLayout(preview_group)
        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        pg_layout.addWidget(self._preview_text)
        layout.addWidget(preview_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._on_apply)
        btn_layout.addStretch()
        btn_layout.addWidget(self._apply_btn)
        cancel_btn = QPushButton("Close")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_search(self):
        """Search for notes containing Migaku annotations."""
        query = self._search_edit.text().strip()
        col = mw.col
        if not col:
            return

        # Find note IDs matching query
        try:
            if query:
                nids = col.find_notes(query)
            else:
                nids = col.find_notes("")
        except Exception as exc:
            self._preview_text.setPlainText("Search error: %s" % exc)
            return

        # Filter to notes that actually contain Migaku brackets
        migaku_re = _MIGAKU_RE
        matched = []
        previews = []
        for nid in nids:
            note = col.get_note(nid)
            for fld_name, fld_val in zip(note.keys(), note.values()):
                if migaku_re.search(fld_val):
                    matched.append(nid)
                    # Show first few previews
                    if len(previews) < 50:
                        if self._mode == "convert":
                            after = _convert_migaku(fld_val)
                        else:
                            after = _strip_migaku(fld_val)
                        if after != fld_val:
                            previews.append(
                                "nid %d [%s]:\n  BEFORE: %s\n  AFTER:  %s"
                                % (nid, fld_name, fld_val[:200], after[:200])
                            )
                    break  # only count each note once

        self._matched_nids = list(set(matched))

        if not self._matched_nids:
            self._preview_text.setPlainText(
                "No notes with Migaku annotations found."
            )
            self._apply_btn.setEnabled(False)
            return

        header = "Found %d notes with Migaku annotations.\n\n" % len(
            self._matched_nids
        )
        if previews:
            header += "Preview (first %d changes):\n\n" % len(previews)
        self._preview_text.setPlainText(header + "\n\n".join(previews))
        self._apply_btn.setEnabled(True)

    def _on_apply(self):
        """Apply conversion/stripping to all matched notes."""
        if not self._matched_nids:
            return

        col = mw.col
        if not col:
            return

        # Confirmation dialog
        action_word = "convert" if self._mode == "convert" else "strip"
        reply = QMessageBox.question(
            self,
            "Confirm Bulk %s" % action_word.title(),
            "This will %s Migaku annotations in %d notes.\n\n"
            "This action can be undone with Edit \u2192 Undo.\n\n"
            "Continue?" % (action_word, len(self._matched_nids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Set up undo
        undo_label = (
            "Bulk Migaku Convert" if self._mode == "convert"
            else "Bulk Migaku Strip"
        )
        try:
            undo_entry = col.add_custom_undo_entry(undo_label)
        except AttributeError:
            # Older Anki without new undo API
            try:
                mw.checkpoint(undo_label)
            except Exception:
                pass
            undo_entry = None

        convert_fn = _convert_migaku if self._mode == "convert" else _strip_migaku

        progress = QProgressDialog(
            "Processing notes...", "Cancel", 0, len(self._matched_nids), self
        )
        progress.setWindowTitle(undo_label)
        progress.setMinimumDuration(0)

        changed_count = 0
        for i, nid in enumerate(self._matched_nids):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            QApplication.processEvents()

            note = col.get_note(nid)
            modified = False
            for idx, val in enumerate(note.values()):
                new_val = convert_fn(val)
                if new_val != val:
                    note.fields[idx] = new_val
                    modified = True
            if modified:
                col.update_note(note)
                changed_count += 1

        progress.setValue(len(self._matched_nids))

        # Merge undo entries if available
        if undo_entry is not None:
            try:
                col.merge_undo_entries(undo_entry)
            except Exception:
                pass

        from aqt.utils import showInfo
        showInfo(
            "Done! Modified %d of %d notes.\n\n"
            "Use Edit > Undo to revert."
            % (changed_count, len(self._matched_nids))
        )
        self._apply_btn.setEnabled(False)
        self._matched_nids = []
        self._preview_text.clear()


def _bulk_migaku_convert():
    """Open bulk Migaku convert dialog."""
    dialog = _BulkMigakuDialog(mw, mode="convert")
    dialog.exec()


def _bulk_migaku_strip():
    """Open bulk Migaku strip dialog."""
    dialog = _BulkMigakuDialog(mw, mode="strip")
    dialog.exec()


# -- Menu items --
_action = mw.form.menuTools.addAction("Universal Furigana Settings\u2026")
_action.triggered.connect(_open_settings)
_action2 = mw.form.menuTools.addAction("UF: Bulk Convert Migaku \u2192 UF\u2026")
_action2.triggered.connect(_bulk_migaku_convert)
_action3 = mw.form.menuTools.addAction("UF: Bulk Strip Migaku Annotations\u2026")
_action3.triggered.connect(_bulk_migaku_strip)

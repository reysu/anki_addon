// Extracted UF core functions for testing.
// These mirror the functions embedded in _SCRIPT_TEMPLATE in __init__.py.
// Any changes to __init__.py's JS must be reflected here and vice versa.

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

function parsePitchCode(str, PITCH_ENABLED, COLORS) {
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

function parseAnnotation(annotation, baseWord, PITCH_ENABLED, COLORS) {
    var hidden = false;
    if (annotation.charAt(0) === '!') {
        hidden = true;
        annotation = annotation.substring(1);
    }
    var parts = annotation.split(';');
    var reading = null;
    var pitch = null;
    var gloss = null;

    var firstAsPitch = parsePitchCode(parts[0], PITCH_ENABLED, COLORS);

    if (firstAsPitch) {
        pitch = firstAsPitch;
        if (parts.length > 1 && parts[1].trim().length > 0) {
            gloss = parts[1].trim();
        }
    } else {
        reading = parts[0];
        if (parts.length > 1) {
            pitch = parsePitchCode(parts[1], PITCH_ENABLED, COLORS);
        }
        if (parts.length > 2 && parts[2].trim().length > 0) {
            gloss = parts[2].trim();
        }
    }

    return { reading: reading, pitch: pitch, gloss: gloss, hidden: hidden };
}

function paginate(text, CHARS_PER_PAGE) {
    if (typeof CHARS_PER_PAGE === 'undefined') CHARS_PER_PAGE = 120;
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

function buildPitchHTML(reading, type, dropAt, color, LINE_PX) {
    if (typeof LINE_PX === 'undefined') LINE_PX = 2;
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

// ---- DOM-dependent functions ----
// These need a document context (jsdom provides this in tests)

function isDarkMode() {
    var b = document.body;
    if (!b) return false;
    if (b.classList.contains('nightMode') || b.classList.contains('night_mode')) return true;
    var el = b.parentElement;
    while (el) {
        if (el.classList && (el.classList.contains('nightMode') || el.classList.contains('night_mode'))) return true;
        el = el.parentElement;
    }
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

function convertFurigana(rootNode, opts) {
    opts = opts || {};
    var PITCH_ENABLED = opts.PITCH_ENABLED !== undefined ? opts.PITCH_ENABLED : true;
    var COLORS = opts.COLORS || {"h": "#3366CC", "a": "#CC3333", "n": "#DD8800", "o": "#339933"};
    var LINE_PX = opts.LINE_PX || 2;
    var COLOR_WORDS = opts.COLOR_WORDS || { enabled: false, furigana: true, kanji: false };
    var darkMode = opts.darkMode !== undefined ? opts.darkMode : false;

    // Tooltip setup helpers (simplified for testing — no portal)
    function wrapWithTooltipTest(el, text, rtEl) {
        el.classList.add('uf-has-info');
        el.setAttribute('data-uf-gloss', text);
    }

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
                if (node.nodeValue && (node.nodeValue.indexOf('{') !== -1 || node.nodeValue.indexOf('[') !== -1))
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

        var RE = /([^\s{\[]+?)(?:\{([^}]+)\}|\[([^\]]+)\])/g;
        if (!RE.test(text)) continue;
        RE.lastIndex = 0;

        var parts = [];
        var lastIdx = 0;
        var m;

        while ((m = RE.exec(text)) !== null) {
            if (m.index > lastIdx) {
                parts.push({ t: 'txt', v: text.substring(lastIdx, m.index) });
            }
            parts.push({ t: 'fg', base: m[1], ann: m[2] || m[3] });
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
                var parsed = parseAnnotation(part.ann, part.base, PITCH_ENABLED, COLORS);

                if (!parsed.reading && parsed.pitch) {
                    var container = document.createElement('span');
                    var useColor = parsed.pitch.color;
                    if (COLOR_WORDS.enabled) {
                        if (!COLOR_WORDS.kanji) useColor = 'inherit';
                    }
                    container.innerHTML = buildPitchHTML(part.base, parsed.pitch.type,
                                                        parsed.pitch.drop, useColor, LINE_PX);
                    if (parsed.hidden) container.classList.add('uf-hidden');
                    if (parsed.gloss) {
                        wrapWithTooltipTest(container, parsed.gloss);
                    }
                    frag.appendChild(container);

                } else {
                    var rtContent = '';

                    if (parsed.pitch && parsed.reading) {
                        var fgColor = parsed.pitch.color;
                        if (COLOR_WORDS.enabled && !COLOR_WORDS.furigana) fgColor = 'inherit';
                        rtContent += buildPitchHTML(parsed.reading, parsed.pitch.type,
                                                   parsed.pitch.drop, fgColor, LINE_PX);
                    } else if (parsed.reading) {
                        rtContent += '<span>' + parsed.reading + '</span>';
                    }

                    var ruby = document.createElement('ruby');
                    if (parsed.hidden) ruby.classList.add('uf-hidden');
                    var baseHTML = part.base;
                    if (COLOR_WORDS.enabled && COLOR_WORDS.kanji && parsed.pitch) {
                        baseHTML = '<span style="color:' + parsed.pitch.color + '">' + part.base + '</span>';
                    } else if (darkMode) {
                        ruby.style.color = '#fff';
                    }
                    ruby.innerHTML = baseHTML + '<rt>' + rtContent + '</rt>';

                    if (parsed.gloss) {
                        var rtEl = ruby.querySelector('rt');
                        wrapWithTooltipTest(ruby, parsed.gloss, rtEl);
                    }
                    frag.appendChild(ruby);
                }
            }
        }
        if (textNode.parentNode) {
            textNode.parentNode.replaceChild(frag, textNode);
        }
    }
}

module.exports = {
    splitMora,
    getPitchPattern,
    parsePitchCode,
    parseAnnotation,
    paginate,
    buildPitchHTML,
    isDarkMode,
    convertFurigana,
};

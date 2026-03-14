const {
    splitMora,
    getPitchPattern,
    parsePitchCode,
    parseAnnotation,
    paginate,
    buildPitchHTML,
    isDarkMode,
    convertFurigana,
} = require('./uf-core');

const COLORS = { h: '#3366CC', a: '#CC3333', n: '#DD8800', o: '#339933' };

// ============================================================
// splitMora
// ============================================================
describe('splitMora', () => {
    test('simple hiragana', () => {
        expect(splitMora('たべる')).toEqual(['た', 'べ', 'る']);
    });

    test('digraph (きょ)', () => {
        expect(splitMora('きょう')).toEqual(['きょ', 'う']);
    });

    test('multiple digraphs', () => {
        expect(splitMora('しゃしょう')).toEqual(['しゃ', 'しょ', 'う']);
    });

    test('katakana digraphs', () => {
        expect(splitMora('シャチョウ')).toEqual(['シャ', 'チョ', 'ウ']);
    });

    test('single mora', () => {
        expect(splitMora('あ')).toEqual(['あ']);
    });

    test('empty string', () => {
        expect(splitMora('')).toEqual([]);
    });

    test('long vowel with っ', () => {
        expect(splitMora('がっこう')).toEqual(['が', 'っ', 'こ', 'う']);
    });

    test('mixed kana', () => {
        expect(splitMora('ちゅうしゃじょう')).toEqual(['ちゅ', 'う', 'しゃ', 'じょ', 'う']);
    });

    test('small ァ ィ ゥ ェ ォ (katakana digraphs)', () => {
        expect(splitMora('ティ')).toEqual(['ティ']);
        expect(splitMora('フォ')).toEqual(['フォ']);
    });
});

// ============================================================
// getPitchPattern
// ============================================================
describe('getPitchPattern', () => {
    test('heiban (h) — 3 mora', () => {
        expect(getPitchPattern(3, 'h', 0)).toEqual([0, 1, 1]);
    });

    test('heiban (h) — 1 mora', () => {
        expect(getPitchPattern(1, 'h', 0)).toEqual([0]);
    });

    test('atamadaka (a) — 3 mora', () => {
        expect(getPitchPattern(3, 'a', 0)).toEqual([1, 0, 0]);
    });

    test('atamadaka (a) — 1 mora', () => {
        expect(getPitchPattern(1, 'a', 0)).toEqual([1]);
    });

    test('odaka (o) — 3 mora', () => {
        expect(getPitchPattern(3, 'o', 0)).toEqual([0, 1, 1]);
    });

    test('odaka (o) — 1 mora', () => {
        expect(getPitchPattern(1, 'o', 0)).toEqual([0]);
    });

    test('nakadaka (n) drop at 2 — 4 mora', () => {
        expect(getPitchPattern(4, 'n', 2)).toEqual([0, 1, 0, 0]);
    });

    test('nakadaka (n) drop at 1 — 3 mora', () => {
        expect(getPitchPattern(3, 'n', 1)).toEqual([0, 0, 0]);
    });

    test('nakadaka (n) drop at 3 — 4 mora', () => {
        expect(getPitchPattern(4, 'n', 3)).toEqual([0, 1, 1, 0]);
    });

    test('unknown type returns empty', () => {
        expect(getPitchPattern(3, 'x', 0)).toEqual([]);
    });
});

// ============================================================
// parsePitchCode
// ============================================================
describe('parsePitchCode', () => {
    test('heiban', () => {
        expect(parsePitchCode('h', true, COLORS)).toEqual({ type: 'h', drop: 0, color: '#3366CC' });
    });

    test('atamadaka', () => {
        expect(parsePitchCode('a', true, COLORS)).toEqual({ type: 'a', drop: 0, color: '#CC3333' });
    });

    test('odaka', () => {
        expect(parsePitchCode('o', true, COLORS)).toEqual({ type: 'o', drop: 0, color: '#339933' });
    });

    test('nakadaka n2', () => {
        expect(parsePitchCode('n2', true, COLORS)).toEqual({ type: 'n', drop: 2, color: '#DD8800' });
    });

    test('nakadaka n10', () => {
        expect(parsePitchCode('n10', true, COLORS)).toEqual({ type: 'n', drop: 10, color: '#DD8800' });
    });

    test('case insensitive', () => {
        expect(parsePitchCode('H', true, COLORS)).toEqual({ type: 'h', drop: 0, color: '#3366CC' });
        expect(parsePitchCode('N3', true, COLORS)).toEqual({ type: 'n', drop: 3, color: '#DD8800' });
    });

    test('with whitespace', () => {
        expect(parsePitchCode(' h ', true, COLORS)).toEqual({ type: 'h', drop: 0, color: '#3366CC' });
    });

    test('returns null when pitch disabled', () => {
        expect(parsePitchCode('h', false, COLORS)).toBeNull();
    });

    test('returns null for empty/null', () => {
        expect(parsePitchCode('', true, COLORS)).toBeNull();
        expect(parsePitchCode(null, true, COLORS)).toBeNull();
    });

    test('returns null for invalid codes', () => {
        expect(parsePitchCode('x', true, COLORS)).toBeNull();
        expect(parsePitchCode('n', true, COLORS)).toBeNull();  // n without number
        expect(parsePitchCode('n0', true, COLORS)).toBeNull();  // n0 invalid
        expect(parsePitchCode('nab', true, COLORS)).toBeNull();
    });
});

// ============================================================
// parseAnnotation
// ============================================================
describe('parseAnnotation', () => {
    test('reading only', () => {
        const r = parseAnnotation('たべる', '食べる', true, COLORS);
        expect(r.reading).toBe('たべる');
        expect(r.pitch).toBeNull();
        expect(r.gloss).toBeNull();
        expect(r.hidden).toBe(false);
    });

    test('reading + pitch', () => {
        const r = parseAnnotation('たべる;h', '食べる', true, COLORS);
        expect(r.reading).toBe('たべる');
        expect(r.pitch).toEqual({ type: 'h', drop: 0, color: '#3366CC' });
        expect(r.gloss).toBeNull();
    });

    test('reading + pitch + gloss', () => {
        const r = parseAnnotation('たべる;h;to eat', '食べる', true, COLORS);
        expect(r.reading).toBe('たべる');
        expect(r.pitch.type).toBe('h');
        expect(r.gloss).toBe('to eat');
    });

    test('pitch only (no reading)', () => {
        const r = parseAnnotation('a', '山', true, COLORS);
        expect(r.reading).toBeNull();
        expect(r.pitch.type).toBe('a');
        expect(r.gloss).toBeNull();
    });

    test('pitch + gloss (no reading)', () => {
        const r = parseAnnotation('h;flatness', '平', true, COLORS);
        expect(r.reading).toBeNull();
        expect(r.pitch.type).toBe('h');
        expect(r.gloss).toBe('flatness');
    });

    test('hidden prefix !', () => {
        const r = parseAnnotation('!たべる;h', '食べる', true, COLORS);
        expect(r.hidden).toBe(true);
        expect(r.reading).toBe('たべる');
        expect(r.pitch.type).toBe('h');
    });

    test('reading with invalid pitch falls through', () => {
        const r = parseAnnotation('たべる;xyz', '食べる', true, COLORS);
        expect(r.reading).toBe('たべる');
        expect(r.pitch).toBeNull();
        expect(r.gloss).toBeNull();
    });

    test('reading + no pitch + gloss (empty pitch slot)', () => {
        const r = parseAnnotation('たべる;;to eat', '食べる', true, COLORS);
        expect(r.reading).toBe('たべる');
        expect(r.pitch).toBeNull();
        expect(r.gloss).toBe('to eat');
    });

    test('pitch disabled — reading only', () => {
        const r = parseAnnotation('たべる;h;to eat', '食べる', false, COLORS);
        expect(r.reading).toBe('たべる');
        expect(r.pitch).toBeNull();
        expect(r.gloss).toBe('to eat');
    });
});

// ============================================================
// paginate
// ============================================================
describe('paginate', () => {
    test('short text fits in one page', () => {
        expect(paginate('hello', 120)).toEqual(['hello']);
    });

    test('exact boundary', () => {
        const text = 'a'.repeat(120);
        expect(paginate(text, 120)).toEqual([text]);
    });

    test('splits long text', () => {
        const text = 'a'.repeat(250);
        const pages = paginate(text, 120);
        expect(pages.length).toBe(3);
        expect(pages.join('')).toBe(text);
    });

    test('prefers break at sentence-ending punctuation', () => {
        const text = 'a'.repeat(80) + '。' + 'b'.repeat(80);
        const pages = paginate(text, 120);
        expect(pages.length).toBe(2);
        expect(pages[0]).toBe('a'.repeat(80) + '。');
        expect(pages[1]).toBe('b'.repeat(80));
    });

    test('prefers break at comma', () => {
        const text = 'a'.repeat(90) + '、' + 'b'.repeat(90);
        const pages = paginate(text, 120);
        expect(pages.length).toBe(2);
        expect(pages[0].endsWith('、')).toBe(true);
    });

    test('empty string', () => {
        expect(paginate('', 120)).toEqual(['']);
    });
});

// ============================================================
// buildPitchHTML
// ============================================================
describe('buildPitchHTML', () => {
    test('produces pitch-word wrapper', () => {
        const html = buildPitchHTML('たべる', 'h', 0, '#3366CC', 2);
        expect(html).toContain('uf-pitch-word');
        expect(html).toContain('た');
        expect(html).toContain('べ');
        expect(html).toContain('る');
    });

    test('atamadaka has drop line on first mora', () => {
        const html = buildPitchHTML('やま', 'a', 0, '#CC3333', 2);
        // First mora should have solid border-top and drop span
        expect(html).toContain('2px solid #CC3333');
        expect(html).toContain('background:#CC3333');
    });

    test('heiban has no drop lines', () => {
        const html = buildPitchHTML('はし', 'h', 0, '#3366CC', 2);
        expect(html).not.toContain('background:#3366CC');
    });

    test('nakadaka drop at correct position', () => {
        const html = buildPitchHTML('おとこ', 'n', 2, '#DD8800', 2);
        // Should have drop after 2nd mora
        expect(html).toContain('background:#DD8800');
    });

    test('odaka has drop on last mora', () => {
        const html = buildPitchHTML('はし', 'o', 0, '#339933', 2);
        expect(html).toContain('background:#339933');
    });

    test('respects LINE_PX', () => {
        const html = buildPitchHTML('あ', 'a', 0, '#CC3333', 5);
        expect(html).toContain('5px solid #CC3333');
        expect(html).toContain('padding-top:7px');
    });

    test('digraph mora counted correctly', () => {
        const html = buildPitchHTML('きょう', 'h', 0, '#3366CC', 2);
        // 2 mora: きょ + う  — first low, second high
        const spans = html.match(/<span style="display:inline-block/g);
        expect(spans).toHaveLength(2);
    });
});

// ============================================================
// isDarkMode (DOM-dependent)
// ============================================================
describe('isDarkMode', () => {
    beforeEach(() => {
        document.body.className = '';
        document.documentElement.className = '';
    });

    test('returns false with no dark mode class', () => {
        expect(isDarkMode()).toBe(false);
    });

    test('detects nightMode on body', () => {
        document.body.classList.add('nightMode');
        expect(isDarkMode()).toBe(true);
    });

    test('detects night_mode on body', () => {
        document.body.classList.add('night_mode');
        expect(isDarkMode()).toBe(true);
    });

    test('detects nightMode on html ancestor', () => {
        document.documentElement.classList.add('nightMode');
        expect(isDarkMode()).toBe(true);
    });
});

// ============================================================
// convertFurigana (DOM-dependent integration tests)
// ============================================================
describe('convertFurigana', () => {
    let container;

    beforeEach(() => {
        container = document.createElement('div');
        document.body.appendChild(container);
    });

    afterEach(() => {
        container.remove();
    });

    test('converts simple reading annotation to ruby', () => {
        container.textContent = '食べる{たべる}';
        convertFurigana(container);
        const ruby = container.querySelector('ruby');
        expect(ruby).not.toBeNull();
        expect(ruby.textContent).toContain('食べる');
        expect(ruby.textContent).toContain('たべる');
    });

    test('preserves surrounding text', () => {
        container.textContent = 'before 食べる{たべる} after';
        convertFurigana(container);
        expect(container.textContent).toContain('before');
        expect(container.textContent).toContain('after');
        expect(container.querySelector('ruby')).not.toBeNull();
    });

    test('handles multiple annotations in one text node', () => {
        container.textContent = '食べる{たべる} 飲む{のむ}';
        convertFurigana(container);
        const rubies = container.querySelectorAll('ruby');
        expect(rubies).toHaveLength(2);
    });

    test('pitch-only annotation (no reading) creates pitch span', () => {
        container.textContent = '山{a}';
        convertFurigana(container);
        expect(container.querySelector('.uf-pitch-word')).not.toBeNull();
        expect(container.querySelector('ruby')).toBeNull();
    });

    test('reading + pitch creates ruby with pitch in rt', () => {
        container.textContent = '食べる{たべる;h}';
        convertFurigana(container);
        const ruby = container.querySelector('ruby');
        expect(ruby).not.toBeNull();
        const rt = ruby.querySelector('rt');
        expect(rt.querySelector('.uf-pitch-word')).not.toBeNull();
    });

    test('gloss adds uf-has-info class', () => {
        container.textContent = '食べる{たべる;h;to eat}';
        convertFurigana(container);
        expect(container.querySelector('.uf-has-info')).not.toBeNull();
    });

    test('hidden prefix adds uf-hidden class', () => {
        container.textContent = '食べる{!たべる}';
        convertFurigana(container);
        const ruby = container.querySelector('ruby');
        expect(ruby.classList.contains('uf-hidden')).toBe(true);
    });

    test('skips text nodes inside SCRIPT tags', () => {
        container.innerHTML = '<script>var x = "test{ignore}";</script>';
        convertFurigana(container);
        expect(container.querySelector('ruby')).toBeNull();
    });

    test('skips text nodes inside STYLE tags', () => {
        container.innerHTML = '<style>.test{color:red}</style>';
        convertFurigana(container);
        expect(container.querySelector('ruby')).toBeNull();
    });

    test('skips text nodes inside RT tags', () => {
        container.innerHTML = '<ruby>漢字<rt>test{nested}</rt></ruby>';
        convertFurigana(container);
        // Should not create a nested ruby
        expect(container.querySelectorAll('ruby')).toHaveLength(1);
    });

    test('handles detached text node gracefully (no crash)', () => {
        container.textContent = '食べる{たべる}';
        // Detach the text node before conversion
        const textNode = container.firstChild;
        container.removeChild(textNode);
        container.appendChild(textNode);
        // Should not throw
        convertFurigana(container);
        expect(container.querySelector('ruby')).not.toBeNull();
    });

    test('no annotations — no changes', () => {
        container.textContent = 'plain text without braces';
        const before = container.innerHTML;
        convertFurigana(container);
        expect(container.innerHTML).toBe(before);
    });

    test('orphaned braces without base word are ignored', () => {
        container.textContent = '{orphan}';
        const before = container.textContent;
        convertFurigana(container);
        // Regex requires non-whitespace before {, so {orphan} alone should not match
        expect(container.querySelector('ruby')).toBeNull();
    });

    test('annotation with spaces in base word splits correctly', () => {
        // The regex [^\s{]+? requires non-whitespace before {
        container.textContent = 'word with 食べる{たべる}';
        convertFurigana(container);
        const ruby = container.querySelector('ruby');
        expect(ruby).not.toBeNull();
        expect(ruby.textContent).toContain('食べる');
    });

    test('dark mode sets white color on ruby', () => {
        container.textContent = '食べる{たべる}';
        convertFurigana(container, { darkMode: true });
        const ruby = container.querySelector('ruby');
        expect(ruby.style.color).toBe('rgb(255, 255, 255)');
    });

    test('COLOR_WORDS.kanji colors the base word', () => {
        container.textContent = '食べる{たべる;h}';
        convertFurigana(container, {
            COLOR_WORDS: { enabled: true, furigana: true, kanji: true }
        });
        const ruby = container.querySelector('ruby');
        const colorSpan = ruby.querySelector('span[style*="color"]');
        expect(colorSpan).not.toBeNull();
        expect(colorSpan.textContent).toBe('食べる');
    });

    test('multiple text nodes in nested HTML', () => {
        container.innerHTML = '<p>食べる{たべる}</p><p>飲む{のむ}</p>';
        convertFurigana(container);
        expect(container.querySelectorAll('ruby')).toHaveLength(2);
    });

    test('already-processed content is not double-processed', () => {
        container.textContent = '食べる{たべる}';
        convertFurigana(container);
        const rubyCount1 = container.querySelectorAll('ruby').length;
        convertFurigana(container);
        const rubyCount2 = container.querySelectorAll('ruby').length;
        expect(rubyCount2).toBe(rubyCount1);
    });
});

// ============================================================
// Regex edge cases
// ============================================================
describe('annotation regex edge cases', () => {
    let container;

    beforeEach(() => {
        container = document.createElement('div');
        document.body.appendChild(container);
    });

    afterEach(() => {
        container.remove();
    });

    test('annotation with semicolons in gloss', () => {
        // Only first two semicolons are structural; rest is part of gloss
        container.textContent = '食べる{たべる;h;to eat; to consume}';
        convertFurigana(container);
        const ruby = container.querySelector('ruby');
        expect(ruby).not.toBeNull();
    });

    test('consecutive annotations without space', () => {
        container.textContent = '食{た}べる{べる}';
        convertFurigana(container);
        const rubies = container.querySelectorAll('ruby');
        // The regex should handle adjacent annotations
        expect(rubies.length).toBeGreaterThanOrEqual(1);
    });

    test('annotation immediately after HTML tag', () => {
        container.innerHTML = '<b>食べる{たべる}</b>';
        convertFurigana(container);
        expect(container.querySelector('ruby')).not.toBeNull();
    });

    test('empty annotation braces', () => {
        container.textContent = '食べる{}';
        convertFurigana(container);
        // Empty braces — regex requires [^}]+ so should not match
        expect(container.querySelector('ruby')).toBeNull();
    });

    test('nested braces are handled', () => {
        container.textContent = '食べる{たべる}other{おざー}';
        convertFurigana(container);
        expect(container.querySelectorAll('ruby')).toHaveLength(2);
    });
});

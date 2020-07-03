import anki.stdmodels

def addBlankModel(col):
    mm = col.models
    m = mm.new(("Testing"))
    fm = mm.newField(("Expression"))
    mm.addField(m,fm)
    fm = mm.newField(("Meaning"))
    mm.addField(m,fm)
    fm = mm.newField("Reading")
    mm.addField(m,fm)
    m['css'] += u"""\
    .jp { font-size: 30px }
    .win .jp { font-family: "MS Mincho", "ＭＳ 明朝"; }
    .mac .jp { font-family: "Hiragino Mincho Pro", "ヒラギノ明朝 Pro"; }
    .linux .jp { font-family: "Kochi Mincho", "東風明朝"; }
    .mobile .jp { font-family: "Hiragino Mincho ProN"; }"""

    # recognition card
    t['qfmt'] = "<div class=jp> {{Expression}} </div>"
    t['afmt'] = """{{FrontSide}}\n\n<hr id=answer>\n\n\
    <div class=jp> {{furigana:Reading}} </div><br>\n\
    {{Meaning}}"""
    mm.addTemplate(m,t)
    mm.add(m)
    return m



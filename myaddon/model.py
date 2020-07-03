import anki.stdmodels

def addBlankModel(col):
    mm = col.models
    m = mm.new(("Testing"))
    fm = mm.newField(("Expression"))
    mm.addField(m,fm)
    fm = mm.newField(("Reading"))
    mm.addField(m,fm)
    fm = mm.newField("Meaning")
    mm.addField(m,fm)
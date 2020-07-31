from aqt import mw
import os
from os.path import dirname, join
from anki.stdmodels import models
from anki.hooks import addHook
from shutil import copyfile
modelList = []
name = 'Testing'
fields = ['Front',  'Back']

front = '''<{{Front}}'''

back = '''{{Back}}'''

style = '''
.card {
 font-size: 23px;
 text-align: left;
 color: black;
 background-color: #FFFAF0;
 font-family: yuumichou;
}
@font-face {
font-family: yuumichou;
src: url(_yumin.ttf);
}
.tags {
font-family: yuumichou;
color: #585858;
}
.expression-field{
font-size: 30px;
}
.meaning-field{
font-size: 25px;
}
.padded-top{
padding-top: 15px;
}
'''


modelList.append([name, fields, front, back])
def addModels():
    for model in modelList:
        if not mw.col.models.byName(model[0]):
            modelManager = mw.col.models
            newModel = modelManager.new(model[0])
            for fieldName in model[1]:
                field = modelManager.newField(fieldName)
                modelManager.addField(newModel, field)
            template = modelManager.newTemplate('Sentence')
            template['qfmt'] = model[2]
            template['afmt'] = model[3]
            newModel['css'] = style
            modelManager.addTemplate(newModel, template)
            modelManager.add(newModel)

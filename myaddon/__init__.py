from aqt import mw
from aqt.utils import showInfo
from aqt.qt import *

def testFunction():
    cardCount = mw.col.cardCount()
    showInfo("Card count: %d" % cardCount)

action = QAction("test",mw)
action.triggered.connect(testFunction)
mw.form.menuTools.addAction(action)


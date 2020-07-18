from aqt import mw
from aqt.utils import showInfo
from aqt.qt import *
from . import model
from anki.hooks import addHook

def testFunction():
    cardCount = mw.col.cardCount()
    showInfo("Card count: %d" % cardCount)


action = QAction("test",mw)
#action.triggered.connect(testFunction)
#mw.form.menuTools.addAction(action)


def prepare(html, card, context):
    return html + """
var field = document.querySelectorAll('.test');
sentence = field[0].innerHTML;
sentence = furgianifyBrackets(sentence);
field[0].innerHTML = sentence;
<script>
function curlyBrackets(sentence){
  var regex;
  var tempWord = "";
  regex = sentence.match(/[^ ]+?\{[^\}]+\}*/g);
  if(regex){
    for(var i=0; i<regex.length; i++){
      full = regex[i].match(/[^>]+?\{[^\}]+\}/).toString();
      furigana = full.match(/\{([^\}]+)\}/)[1];
      baseWord = full.replace(/\{([^\}]+)\}/, "")

      html = "<ruby>" + baseWord + "<rt>" + furigana + "</rt> </ruby>";
    // html = "<ruby> hey<rt>你好</rt></ruby>"
     sentence = sentence.split(full).join(html);
   // sentence = typeof full

    }
  }
  return sentence;
}
</script>"""
addHook('prepareQA', prepare)

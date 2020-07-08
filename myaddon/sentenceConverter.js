var field = document.querySelectorAll('.test');
field[0].style.backgroundColor = "white";
sentence = field[0].innerHTML;
sentence = furgianifyBrackets(sentence);
field[0].innerHTML = sentence;
function furiganify(sentence) {
       var regex;
       var tempWord = "";
       if(regex = sentence.match(/[^ ]+?\{[^\]]+\}*/g)){
      	 for(var i=0; i<regex.length; i++){
           	furigana = regex[i].match(/\{([^\]]+)\}/)[1];
		baseWord = regex[i].replace(/\{([^\]]+)\}/, "")
		html = "<ruby>" + baseWord + "<rt>" + furigana + "</rt> </ruby>"
		sentence = sentence.replace(/[^ ]+?\{[^\]]+\}*/g, html)
		}
       }
       return sentence;
}
function furgianifyBrackets(sentence){
       var regex;
       var tempWord = "";
       regex = sentence.match(/[^ ]+?\[[^\]]+\]*/g);
       if(regex){
      	 for(var i=0; i<regex.length; i++){
           	furigana = regex[i].match(/\[([^\]]+)\]/)[1];
		baseWord = regex[i].replace(/\[([^\]]+)\]/, "")
		html = "<ruby>" + baseWord + "<rt>" + furigana + "</rt> </ruby>"
		sentence = sentence.replace(/[^ ]+?\[[^\]]+\]*/g, html)
		}
       }
       return sentence;
}
/*
Basically the goal here is to take a sentence like
僕の 名前<なまえ>はエリックです
and convert it to
僕の　<ruby>名前<rt>なまえ</rt></ruby>　はエリックです
which will convert it into furgiana

todo: use regex

*/

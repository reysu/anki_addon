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
      //the way that it is right now is like you have to add the tags
      //nofurigana in order for the furigana to be invisible on the front

       var regex;
       var tempWord = "";
       regex = sentence.match(/[^ ]+?\[[^\]]+\]*/g);
       if(regex){
      	 for(var i=0; i<regex.length; i++){
           	furigana = regex[i].match(/\[([^\]]+)\]/)[1];
        		baseWord = regex[i].replace(/\[([^\]]+)\]/, "")
        		furiganaWBrackets = baseWord + regex[i].match(/\[([^\]]+)\]/)[0];
        		html = "<ruby>" + baseWord + "<rt>" + furigana + "</rt> </ruby>"
        		//the following line removes the brackets and the word
        		//sentence = sentence.split(" "+ furiganaWBrackets).join("");
        		//the following line replaces the brackets with the furigana
        		sentence = sentence.split(" "+ furiganaWBrackets).join(html);
            //the following was the old one taht used regex
        		//sentence = sentence.replace(/[^ ]+?\[[^\]]+\]*/g, html)
		}
       }
       return sentence;
}

//there's like some bug with when you have something on a new Line
//it makes the thing super high.. 
function curlyBrackets(sentence){
  var regex;
  var tempWord = "";
  regex = sentence.match(/[^ ]+?\{[^\}]+\}*/g);
  if(regex){
    for(var i=0; i<regex.length; i++){
      furigana = regex[i].match(/\{([^\}]+)\}/)[1];
      baseWord = regex[i].replace(/\{([^\}]+)\}/, "")
      html = "<ruby>" + baseWord + "<rt>" + furigana + "</rt> </ruby>";
      sentence = sentence.split(regex[i]).join(html);
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
todo: make it so it works with {} brackets instead of the other one
todo: make it so you can put :furigana in anki brackets for it to actually work
todo: make it add to all the script code on all the cards
todo: make a gui using qt in order to select the decks that you want this added to


*/

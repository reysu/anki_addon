var field = document.querySelectorAll('.test');
field[0].style.backgroundColor = "red";
sentence = field.innerHTML;
sentence = furiganify(sentence);
field[0].innerHTML = sentence

function furiganify(sentence) {
       return "test";
}

/*
Basically the goal here is to take a sentence like
僕の 名前<なまえ>はエリックです
and convert it to
僕の　<ruby>名前<rt>なまえ</rt></ruby>　はエリックです
which will convert it into furgiana

todo: use regex 
*/

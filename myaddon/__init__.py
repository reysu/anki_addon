from aqt import gui_hooks

def myfunc(card):
    print("myfunc")

gui_hooks.reviewer_did_show_answer.append(myfunc)

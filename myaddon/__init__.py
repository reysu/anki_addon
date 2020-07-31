from . import model
from anki.hooks import addHook
addHook("profileLoaded", model.addModels)

from . import main

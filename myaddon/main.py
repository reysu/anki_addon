from os.path import dirname, join, basename, exists, join
import sys, os, platform, re, subprocess, aqt.utils
from anki.utils import stripHTML, isWin, isMac
from aqt import mw
from aqt.qt import *
from shutil import copyfile
from anki.hooks import addHook, wrap, runHook, runFilter
from aqt.utils import shortcut, saveGeom, saveSplitter, showInfo, askUser
import re

config = mw.addonManager.getConfig(__name__)

"""Laptop-only wrapper: runs the app in CPU mode without editing config.py.

Works by monkey-patching the config module at runtime, before app/worker import it.
The default (CUDA) setup is untouched: this file and the whole laptop/ folder are self-contained.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import config
config.WHISPER_DEVICE = "cpu"
config.WHISPER_COMPUTE = "int8"
config.WHISPER_MODEL = "small"

import runpy
runpy.run_module("app", run_name="__main__")

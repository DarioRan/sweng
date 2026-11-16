"""Answering a question from the indexed manuals (/ask): retrieve, gate, generate, verify.

retrieval.py   hybrid search, then a cross-encoder that scores each passage
gate.py        Rule 1: decides, before any model call, whether to answer at all
generation.py  the vision-language model, given the passages and their page images
grounding.py   checks the model's answer against the passages; a failure abstains
pipeline.py    the order of the steps above, and the AskResponse it builds
text.py        part codes and values, shared by the gate and the grounding check
"""

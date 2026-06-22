"""macOS "hands" for VibeFlow.

These modules are the platform-specific layer the Mac app needs — microphone
trigger, text insertion, focused-element detection, frontmost-app identity, the
menu-bar UI — all built on top of the shared, platform-agnostic ``vibeflow.core``
brain (which they must never modify). The Windows top-level modules
(``app.py``, ``output.py``, ``focus_detect.py``, …) are the reference behaviour
for each counterpart here.
"""

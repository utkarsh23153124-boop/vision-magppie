"""Maggpie local face detection and footfall prototype."""
import os

# Avoid backend diagnostics printing credential-bearing stream URLs.
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")

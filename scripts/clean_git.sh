#!/bin/bash

# Remove large files from Git tracking
git rm --cached "ffmpeg/ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe"
git rm --cached "ffmpeg/ffmpeg-master-latest-win64-gpl/bin/ffplay.exe"
git rm --cached "ffmpeg/ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe"

# Commit the changes
git commit -m "Remove large FFmpeg executables from Git tracking"

# Push the changes
git push 
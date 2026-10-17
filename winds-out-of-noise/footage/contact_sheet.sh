#!/bin/sh
# Timestamped 10x6 contact sheet of a film, for picking shots. Usage: contact_sheet.sh in.mp4 out.jpg
d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" | cut -d. -f1)
iv=$(( d / 60 )); [ "$iv" -lt 2 ] && iv=2
ffmpeg -hide_banner -loglevel error -i "$1" -vf "fps=1/$iv,scale=240:134:force_original_aspect_ratio=decrease,pad=240:136:-1:-1,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf:text='%{pts\:hms}':x=4:y=4:fontsize=13:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=10x6" -frames:v 1 -update 1 -y "$2" && echo "$(basename "$1") dur=${d}s step=${iv}s"

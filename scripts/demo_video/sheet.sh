#!/bin/zsh
# Contact sheet of a clip: sheet.sh clip.mp4 out.png [cols rows]
clip=$1; out=$2; cols=${3:-3}; rows=${4:-3}
n=$((cols*rows)); d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$clip")
fps=$(python3 -c "print(${n}/${d})")
ffmpeg -y -loglevel error -i "$clip" -vf "fps=${fps},scale=640:-1,tile=${cols}x${rows}" -frames:v 1 "$out"

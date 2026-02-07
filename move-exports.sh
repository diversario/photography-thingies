#!/bin/zsh

echo $@ > /tmp/move-exports.log

# this script receives a file path
# the file contains a list of files like so:
#
# /Users/diversario/Library/Mobile Documents/com~apple~CloudDocs/Photos/2026-01-24 Amsterdam, GS645, Kodak Gold/negatives/film-scan3954.jpg
# /Users/diversario/Library/Mobile Documents/com~apple~CloudDocs/Photos/2026-01-24 Amsterdam, GS645, Kodak Gold/negatives/film-scan3954-2.jpg
# ...
#
# Take each file, and move it one level up if it is in a "negatives" folder. So the above files would be moved to:
# /Users/diversario/Library/Mobile Documents/com~apple~CloudDocs/Photos/2026-01-24 Amsterdam, GS645, Kodak Gold/film-scan3954.jpg
# /Users/diversario/Library/Mobile Documents/com~apple~CloudDocs/Photos/2026-01-24 Amsterdam, GS645, Kodak Gold/film-scan3954-2.jpg

while IFS= read -r file; do
  dir=$(dirname "$file")
  name=$(basename "$dir")
  up=$(dirname "$dir")
  if [ "$name" = "negatives" ]; then
    mv "$file" "$up/"
  fi
done < "$1"

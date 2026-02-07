#!/bin/zsh

# called after Lightroom exports files, with the path to a text file containing the list of exported files as an argument

# first, invoke the move-exports.sh script to move any files in "negatives" folders up one level

# then, run the resize_for_export.py with the argument being the parent folder of the `negatives` folder

script_dir=$(dirname "$0")

"$script_dir/move-exports.sh" "$1"

"$script_dir/resize_for_export.py" "$(dirname "$(dirname "$(head -n 1 "$1")")")"

#!/bin/zsh
set -euo pipefail

# Ensure Automator can see Homebrew installs
PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
export PATH

# Locate exiftool
if ! EXIFTOOL=$(command -v exiftool); then
	osascript -e 'display alert "ExifTool not found" message "Install with: brew install exiftool" as warning'
	exit 1
fi

# Collect only regular JPEG files from the selection
typeset -a files

for directory in "$@"; do
	metadata_file="$directory/metadata.json"

	if [ ! -f "$metadata_file" ]; then
		osascript -e 'display dialog "'"$directory"' has no metadata.json file. Enter values." buttons {"OK"} default button 1 with title "Error"'

    camera_make_and_model=$(osascript -e 'text returned of (display dialog "Camera make & model:" default answer "")')

    # take the first word as make, the rest as model
    camera_make=$(echo "$camera_make_and_model" | awk -F ' ' '{print $1}')
    camera_model=$(echo "$camera_make_and_model" | awk -F ' ' '{ $1=""; sub(/^ /, ""); print }')

    # echo "Camera Make: $camera_make"
    # echo "Camera Model: $camera_model"

		# camera_make=$(osascript -e 'text returned of (display dialog "Camera make:" default answer "")')
		# camera_model=$(osascript -e 'text returned of (display dialog "Camera model:" default answer "")')
		film=$(osascript -e 'text returned of (display dialog "Film:" default answer "")')

		jq --null-input --arg cm "$camera_make" --arg cmo "$camera_model" --arg f "$film" \
			'{"cameraMake": $cm, "cameraModel": $cmo, "film": $f}' >"$metadata_file"
	fi

	camera_make=$(jq -r '.cameraMake' "$metadata_file")

	if [[ "$camera_make" == "null" ]]; then
		osascript -e 'display dialog "metadata.json in '"$directory"' is missing cameraMake" buttons {"OK"} default button 1 with title "Error"'
		continue
	fi

	camera_model=$(jq -r '.cameraModel' "$metadata_file")
	if [[ "$camera_model" == "null" ]]; then
		osascript -e 'display dialog "metadata.json in '"$directory"' is missing cameraModel" buttons {"OK"} default button 1 with title "Error"'
		continue
	fi

	film=$(jq -r '.film' "$metadata_file")
	if [[ "$film" == "null" ]]; then
		osascript -e 'display dialog "metadata.json in '"$directory"' is missing film" buttons {"OK"} default button 1 with title "Error"'
		continue
	fi

	for file in $directory/*; do
		[[ -f "$file" ]] || continue

		case "$file" in
		*.jpg | *.JPG | *.jpeg | *.JPEG) files+=("$file") ;;
		*) ;; # skip non-JPEGs
		esac
	done

	# Nothing to do?
	if ((${#files[@]} == 0)); then
		osascript -e 'display dialog "No JPEG files found." buttons {"OK"} default button 1'
		exit 0
	fi

	# Export vars so parallel shells see them
	export EXIFTOOL camera_make camera_model film

	# Temp workspace for results
	td=$(mktemp -d "${TMPDIR:-/tmp}/exifbatch.XXXXXX")
	# Pre-create result files to avoid "no such file" checks later
	: >"$td/success.list"
	: >"$td/error.list"

	# Concurrency limit
	MAX_PROCS=20

	# Run exiftool in parallel; record success/error per file
	# We pass $td as $0 and the filename as $1 inside the -c script.
	printf '%s\0' "${files[@]}" |
		xargs -0 -n 1 -P "$MAX_PROCS" /bin/zsh -c '
    file="$1"
    if "$EXIFTOOL" -P -overwrite_original \
         -Make="$camera_make" \
         -Model="$camera_model" \
         -ImageDescription="film: $film" \
         -XMP:Description="film: $film" \
         -- "$file" >/dev/null 2>&1; then
      print -r -- "$file" >> "$0/success.list"
    else
      print -r -- "$file" >> "$0/error.list"
    fi
  ' "$td"

	# Summarize
	successCount=$(wc -l <"$td/success.list" 2>/dev/null || echo 0)
	errorCount=$(wc -l <"$td/error.list" 2>/dev/null || echo 0)
	total=$((successCount + errorCount))

	# Optional: include first failing filename (if any)
	firstErr=""
	if ((errorCount > 0)); then
		firstErr=$(head -n 1 "$td/error.list")
	fi

	# Show summary popup
	if ((errorCount == 0)); then
		osascript -e 'display dialog "'"$successCount"' of '"$total"' file(s) updated." buttons {"OK"} default button 1 with title "ExifTool: Success"'
	else
		osascript -e 'display dialog "'"$successCount"' succeeded, '"$errorCount"' failed." & return & "'"${firstErr//\"/\\\"}"'" buttons {"OK"} default button 1 with title "ExifTool: Completed with errors"'
	fi

	# Cleanup
	rm -rf "$td"

done

exit 0

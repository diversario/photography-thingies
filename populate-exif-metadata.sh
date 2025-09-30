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
		osascript -e 'display dialog "Directory has no metadata.json file.\n\nEnter values to create one." buttons {"OK"} default button 1 with title "Error"'

    camera_make_and_model=$(osascript -e 'text returned of (display dialog "Camera make & model:" default answer "" with title "Camera")')

    # `camera_make_and_model` must be at least two words
    if [[ $(echo "$camera_make_and_model" | wc -w) -lt 2 ]]; then
      osascript -e 'display dialog "Please enter both camera make and model (at least two words)." buttons {"OK"} default button 1 with title "Error"'
      exit 1
    fi

    # take the first word as make, the rest as model
    camera_make=$(echo "$camera_make_and_model" | awk -F ' ' '{print $1}')
    camera_model=$(echo "$camera_make_and_model" | awk -F ' ' '{ $1=""; sub(/^ /, ""); print }')

    lens_make_and_model=$(osascript -e 'text returned of (display dialog "Lens make & model:" default answer "" with title "Lens (optional)")')

    # same as above: must be at least two words
    if [[ $(echo "$lens_make_and_model" | wc -w) -lt 2 ]]; then
      osascript -e 'display dialog "Please enter both lens make and model (at least two words)." buttons {"OK"} default button 1 with title "Error"'
      exit 1
    fi

    lens_make=$(echo "$lens_make_and_model" | awk -F ' ' '{print $1}')
    lens_model=$(echo "$lens_make_and_model" | awk -F ' ' '{ $1=""; sub(/^ /, ""); print }')

		film=$(osascript -e 'text returned of (display dialog "Film:" default answer "" with title "Film")')

    jq --null-input \
      --arg cm "$camera_make" \
      --arg cmo "$camera_model" --arg lmm "$lens_make" --arg lmo "$lens_model" --arg f "$film" \
      --arg lmm "$lens_make" \
      --arg lmo "$lens_model" \
      --arg f "$film" \
      '{"cameraMake": $cm, "cameraModel": $cmo, "lensMake": $lmm, "lensModel": $lmo, "film": $f}' >"$metadata_file"
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

  # for lens, it's optional
	lens_make=$(jq -r '.lensMake' "$metadata_file")
	if [[ "$lens_make" == "null" ]]; then
		lens_make=""
	fi

	lens_model=$(jq -r '.lensModel' "$metadata_file")
  if [[ "$lens_model" == "null" ]]; then
    lens_model=""
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
	export EXIFTOOL camera_make camera_model film lens_make lens_model

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

    # Update the JPEG file
    jpeg_success=false

    # Build exiftool command with only non-empty values
    exif_args=(-P -overwrite_original)

    # Always add camera info and description
    exif_args+=(-Make="$camera_make")
    exif_args+=(-Model="$camera_model")
    exif_args+=(-ImageDescription="film: $film")
    exif_args+=(-XMP:Description="film: $film")

    # Only add lens info if it is not empty
    if [[ -n "$lens_make" ]]; then
      exif_args+=(-LensMake="$lens_make")
    fi

    if [[ -n "$lens_model" ]]; then
      exif_args+=(-LensModel="$lens_model")
    fi

    exif_args+=(-- "$file")

    if "$EXIFTOOL" "${exif_args[@]}" >/dev/null 2>&1; then
      jpeg_success=true
    fi

    # Check for corresponding XMP sidecar file and update it if it exists
    xmp_success=true  # Default to true since XMP is optional
    base_name="${file%.*}"
    xmp_file="$base_name.xmp"

    # Check for various XMP file extensions (case variations)
    for xmp_ext in .xmp .XMP; do
      xmp_candidate="$base_name$xmp_ext"
      if [[ -f "$xmp_candidate" ]]; then
        xmp_file="$xmp_candidate"
        break
      fi
    done

    # If XMP file exists, update it with the metadata
    if [[ -f "$xmp_file" ]]; then
      echo "❌ Updating XMP sidecar: $xmp_file"

      # Build exiftool command with only non-empty values
      exif_args=(-P -overwrite_original)

      # Always add description
      exif_args+=(-XMP:Description="film: $film")

      # Only add lens info if it is not empty
      if [[ -n "$lens_make" ]]; then
        exif_args+=(-XMP:LensMake="$lens_make")
      fi

      if [[ -n "$lens_model" ]]; then
        exif_args+=(-XMP:LensModel="$lens_model")
      fi

      exif_args+=(-- "$xmp_file")

      if ! "$EXIFTOOL" "${exif_args[@]}" >/dev/null 2>&1; then
        xmp_success=false
      fi
    fi

    # Record success only if both JPEG and XMP (if present) were updated successfully
    if $jpeg_success && $xmp_success; then
      print -r -- "$file" >> "$0/success.list"
    else
      print -r -- "$file" >> "$0/error.list"
    fi
  ' "$td"

	# Count XMP sidecar files that were processed
	xmp_count=0
	for file in "${files[@]}"; do
		base_name="${file%.*}"
		for xmp_ext in .xmp .XMP; do
			xmp_candidate="$base_name$xmp_ext"
			if [[ -f "$xmp_candidate" ]]; then
				xmp_count=$((xmp_count + 1))
				break
			fi
		done
	done

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
		if ((xmp_count > 0)); then
			osascript -e 'display dialog "'"$successCount"' of '"$total"' JPEG file(s) updated.\n'"$xmp_count"' XMP sidecar file(s) also updated." buttons {"OK"} default button 1 with title "ExifTool: Success"'
		else
			osascript -e 'display dialog "'"$successCount"' of '"$total"' JPEG file(s) updated.\nNo XMP sidecar files found." buttons {"OK"} default button 1 with title "ExifTool: Success"'
		fi
	else
		if ((xmp_count > 0)); then
			osascript -e 'display dialog "'"$successCount"' succeeded, '"$errorCount"' failed.\n'"$xmp_count"' XMP sidecar file(s) processed.\nFirst error: '"${firstErr//\"/\\\"}"'" buttons {"OK"} default button 1 with title "ExifTool: Completed with errors"'
		else
			osascript -e 'display dialog "'"$successCount"' succeeded, '"$errorCount"' failed.\nNo XMP sidecar files found.\nFirst error: '"${firstErr//\"/\\\"}"'" buttons {"OK"} default button 1 with title "ExifTool: Completed with errors"'
		fi
	fi

	# Cleanup
	rm -rf "$td"

done

exit 0

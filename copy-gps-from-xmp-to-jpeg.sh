#!/bin/zsh

echo "⚡️ Copying GPS data from XMP files to JPEG files in directory: $1"

exiftool -tagsfromfile %d%f.xmp \
    "-GPS:GPSLatitude<XMP-exif:GPSLatitude" \
    "-GPS:GPSLongitude<XMP-exif:GPSLongitude" \
    -overwrite_original \
    -ext jpg -ext jpeg $1

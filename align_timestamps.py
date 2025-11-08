#!/opt/homebrew/bin/python3

# AppleScript to run this script from Automator
# receives current folders, in Finder

# on run {input, parameters}
# 	set argList to ""
# 	repeat with anItem in input
# 		set argList to argList & " " & quoted form of (POSIX path of anItem)
# 	end repeat
# 	set cmd to "/opt/homebrew/bin/python3 /Users/diversario/Documents/Projects/Personal/photography-thingies/align_timestamps.py" & argList
# 	do shell script cmd
# end run

import sys
import os
import subprocess
import shutil
import concurrent.futures
from typing import List, Tuple

import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def show_toast(title: str, subtitle: str = "", message: str = ""):
    """Show a macOS notification center toast using osascript."""
    cmd = [
        "osascript",
        "-e",
        f'display notification "{message}"\
            with title "{title}"\
                subtitle "{subtitle}"',
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        pass


def update_dates_in_xmp(xmp_file_path: str, new_date: str):
    """
    Delete these XMP attributes/elements if they exist:

    As attributes:
    <rdf:Description
       xmp:ModifyDate="2025-10-30T19:48:30.01+02:00"
       xmp:CreateDate="2025-10-30T19:48:30.01+02:00"
       exif:DateTimeOriginal="2025-10-30T19:48:30.01Z"
       photoshop:DateCreated="2025-10-30T19:48:30.01Z"
    />

    Or as child elements:
    <rdf:Description>
      <exif:DateTimeOriginal>2025-11-08T13:44:00.35Z</exif:DateTimeOriginal>
    </rdf:Description>

    new_date format: YYYY-MM-DDTHH:MM:SS (unused parameter)
    """
    print(f"    Reading XMP file: {xmp_file_path}")

    # Define namespaces
    namespaces = {
        'x': 'adobe:ns:meta/',
        'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
        'xmp': 'http://ns.adobe.com/xap/1.0/',
        'exif': 'http://ns.adobe.com/exif/1.0/',
        'photoshop': 'http://ns.adobe.com/photoshop/1.0/'
    }

    # Register namespaces to preserve prefixes
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)

    # Parse the XMP file
    tree = ET.parse(xmp_file_path)
    root = tree.getroot()

    print(f"    Root tag: {root.tag}")

    # Items to delete (can be attributes or child elements)
    items_to_delete = [
        ('xmp', 'ModifyDate'),
        ('xmp', 'CreateDate'),
        ('exif', 'DateTimeOriginal'),
        ('photoshop', 'DateCreated')
    ]

    modified = False
    deleted_count = 0

    # Find all rdf:Description elements
    rdf_namespace = namespaces['rdf']
    for desc_element in root.iter(f'{{{rdf_namespace}}}Description'):
        # First, delete attributes if they exist
        for prefix, local_name in items_to_delete:
            namespace_uri = namespaces.get(prefix)
            if namespace_uri:
                attr_name = f'{{{namespace_uri}}}{local_name}'
                if attr_name in desc_element.attrib:
                    old_value = desc_element.attrib[attr_name]
                    print(f"    Deleting attribute: {prefix}:{local_name} with value: {old_value}")
                    del desc_element.attrib[attr_name]
                    modified = True
                    deleted_count += 1

        # Second, delete child elements if they exist
        for prefix, local_name in items_to_delete:
            namespace_uri = namespaces.get(prefix)
            if namespace_uri:
                element_name = f'{{{namespace_uri}}}{local_name}'
                for child in list(desc_element):
                    if child.tag == element_name:
                        old_value = child.text
                        print(f"    Deleting element: {prefix}:{local_name} with value: {old_value}")
                        desc_element.remove(child)
                        modified = True
                        deleted_count += 1

    print(f"    Deleted {deleted_count} items, modified={modified}")

    # Write back to file if any modifications were made
    if modified:
        print(f"    Writing changes to file")
        tree.write(xmp_file_path, encoding='utf-8', xml_declaration=True)
        print(f"    File written successfully")
    else:
        print(f"    No items found to delete")


def find_exiftool() -> str:
    """Find exiftool executable."""
    # Add common paths for Homebrew
    paths = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"]

    for path in paths:
        exiftool_path = os.path.join(path, "exiftool")
        if shutil.which(exiftool_path):
            return exiftool_path

    # Try system PATH
    exiftool_path = shutil.which("exiftool")
    if exiftool_path:
        return exiftool_path

    print("ExifTool not found. Install with: brew install exiftool")
    sys.exit(1)


def find_image_files(directory: str) -> List[str]:
    """Find all image files in directory and all subdirectories."""
    image_extensions = [".jpg", ".JPG", ".jpeg", ".JPEG", ".cr3", ".CR3"]
    files = []

    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if any(filename.endswith(ext) for ext in image_extensions):
                filepath = os.path.join(root, filename)
                files.append(filepath)

    return files


def find_xmp_files(directory: str) -> List[str]:
    """Find all XMP files in directory and all subdirectories."""
    xmp_extensions = [".xmp", ".XMP"]
    files = []

    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if any(filename.endswith(ext) for ext in xmp_extensions):
                filepath = os.path.join(root, filename)
                files.append(filepath)

    return files


def update_file_timestamp(args: Tuple[str, str]) -> Tuple[str, bool]:
    """Update DateCreated timestamp from DateTimeOriginal for a single file."""
    exiftool_path, image_file = args

    cmd = [
        exiftool_path,
        "-P",
        "-overwrite_original",
        "-DateCreated<DateTimeOriginal",
        "--",
        image_file,
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return image_file, True
    except subprocess.CalledProcessError:
        return image_file, False


def get_datetime_original(exiftool_path: str, image_file: str) -> str:
    """Extract DateTimeOriginal from an image file."""
    cmd = [
        exiftool_path,
        "-DateTimeOriginal",
        "-s3",
        "-d", "%Y-%m-%dT%H:%M:%S",
        image_file,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def update_xmp_timestamp(args: Tuple[str, str, str]) -> Tuple[str, bool]:
    """Update XMP file timestamps from corresponding image file."""
    exiftool_path, xmp_file, image_file = args

    print(f"Processing XMP: {os.path.basename(xmp_file)} with image: {os.path.basename(image_file)}")

    # Get DateTimeOriginal from the image file
    new_date = get_datetime_original(exiftool_path, image_file)

    if not new_date:
        print(f"  No DateTimeOriginal found for {os.path.basename(image_file)}")
        return xmp_file, False

    print(f"  DateTimeOriginal: {new_date}")

    try:
        update_dates_in_xmp(xmp_file, new_date)
        print(f"  Successfully updated {os.path.basename(xmp_file)}")
        return xmp_file, True
    except Exception as e:
        print(f"  Error updating {os.path.basename(xmp_file)}: {e}")
        return xmp_file, False


def main():
    if len(sys.argv) < 2:
        print("Usage: align_timestamps.py <directory> [directory2] ...")
        sys.exit(1)

    # Find exiftool
    exiftool_path = find_exiftool()

    for directory in sys.argv[1:]:
        if not os.path.isdir(directory):
            print(f"❌ Directory not found: {directory}")
            continue

        dir_name = os.path.basename(os.path.normpath(directory))

        # Show notification that processing is starting
        show_toast("⚡️ Processing started", message=f"🕐 Aligning timestamps in {dir_name}...")

        # Find image files
        image_files = find_image_files(directory)

        if not image_files:
            print(f"ℹ️ No image files found in {directory}")
            continue

        # Find XMP files
        xmp_files = find_xmp_files(directory)

        # Process image files in parallel
        max_workers = 20
        success_files = []
        error_files = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Prepare arguments for each file
            file_args = [
                (exiftool_path, image_file) for image_file in image_files
            ]

            # Submit all tasks
            future_to_file = {
                executor.submit(update_file_timestamp, args): args[1]
                for args in file_args
            }

            # Collect results
            for future in concurrent.futures.as_completed(future_to_file):
                image_file, success = future.result()
                if success:
                    success_files.append(image_file)
                else:
                    error_files.append(image_file)

        # Process XMP files in parallel
        xmp_success_files = []
        xmp_error_files = []

        if xmp_files:
            print(f"Found {len(xmp_files)} XMP files")

            # Create a mapping of base filenames to image files
            image_base_map = {}
            for image_file in image_files:
                base = os.path.splitext(image_file)[0]
                image_base_map[base] = image_file

            print(f"Created mapping for {len(image_base_map)} image files")

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Prepare arguments for each XMP file
                xmp_args = []
                for xmp_file in xmp_files:
                    xmp_base = os.path.splitext(xmp_file)[0]
                    # Find corresponding image file
                    image_file = image_base_map.get(xmp_base)
                    if image_file:
                        xmp_args.append((exiftool_path, xmp_file, image_file))
                    else:
                        print(f"No matching image for XMP: {os.path.basename(xmp_file)}")

                print(f"Matched {len(xmp_args)} XMP files to image files")

                # Submit all tasks
                future_to_xmp = {
                    executor.submit(update_xmp_timestamp, args): args[1]
                    for args in xmp_args
                }

                # Collect results
                for future in concurrent.futures.as_completed(future_to_xmp):
                    xmp_file, success = future.result()
                    if success:
                        xmp_success_files.append(xmp_file)
                    else:
                        xmp_error_files.append(xmp_file)
                        print(f"Failed to update XMP: {os.path.basename(xmp_file)}")

        # Show summary
        success_count = len(success_files)
        error_count = len(error_files)
        total = success_count + error_count

        xmp_success_count = len(xmp_success_files)
        xmp_error_count = len(xmp_error_files)

        msg_header = f"📂 {dir_name}\\n\\n"

        if error_count == 0 and xmp_error_count == 0:
            if xmp_success_count > 0:
                message = f"{msg_header}✅ {success_count}/{total} images, {xmp_success_count} XMPs"
            else:
                message = f"{msg_header}✅ {success_count}/{total} timestamps aligned"
            show_toast("Processing completed", message=message)
        else:
            first_error = os.path.basename(error_files[0]) if error_files else (os.path.basename(xmp_error_files[0]) if xmp_error_files else "")
            if xmp_success_count > 0:
                message = f"{msg_header}✅ {success_count}, ❌ {error_count} images, ✅ {xmp_success_count}, ❌ {xmp_error_count} XMPs.\\nFirst error: {first_error}"
            else:
                message = f"{msg_header}✅ {success_count}, ❌ {error_count}.\\nFirst error: {first_error}"
            show_toast("Processing completed with errors", message=message)


if __name__ == "__main__":
    main()

#!/opt/homebrew/bin/python3

# AppleScript to run this script from Automator
# receives current folders, in Finder

# this does not work with apply python distro for whatever fucking permissions reasons

# on run {input, parameters}
# 	-- Build argument string from Automator input
# 	set argList to ""
# 	repeat with anItem in input
# 		-- Convert to POSIX path if they're files; leave as text otherwise
# 		set argList to argList & " " & quoted form of (POSIX path of anItem)
# 	end repeat

# 	-- Construct command with arguments
# 	set cmd to "/opt/homebrew/bin/python3 /Users/diversario/Documents/Projects/Personal/photography-thingies/populate_exif_metadata.py" & argList

# 	-- Run the command
# 	do shell script cmd
# end run

import sys
import os
import json
import subprocess
import shutil
import tempfile
import concurrent.futures
from pathlib import Path
import pathlib
from typing import Dict, List, Tuple, Optional


def show_dialog(message: str, title: str = "ExifTool", buttons: List[str] = []) -> str:
    """Show a macOS dialog using osascript."""
    if not buttons:
        buttons = ["OK"]

    button_list = '{"' + '", "'.join(buttons) + '"}'
    cmd = [
        "osascript",
        "-e",
        f'display dialog "{message}" buttons {button_list} default button 1 with title "{title}"',
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        sys.exit(1)


def get_input_dialog(prompt: str, title: str = "Input", default: str = "") -> str:
    """Get user input via macOS dialog."""
    cmd = [
        "osascript",
        "-e",
        f'text returned of (display dialog "{prompt}" default answer "{default}" with title "{title}")',
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        sys.exit(1)


def show_alert(title: str, message: str):
    """Show a macOS alert using osascript."""
    cmd = ["osascript", "-e", f'display alert "{title}" message "{message}" as warning']

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        pass


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

    show_alert("ExifTool not found", "Install with: brew install exiftool")
    sys.exit(1)


def parse_make_model(input_str: str) -> Tuple[str, str]:
    """Parse 'make model' input into separate make and model."""
    words = input_str.strip().split()
    if len(words) < 2:
        show_dialog("Please enter both make and model (at least two words).", "Error")
        sys.exit(1)

    make = words[0]
    model = " ".join(words[1:])
    return make, model


def get_metadata_from_user() -> Dict[str, str]:
    """Get metadata from user input dialogs."""
    # Get camera make and model
    camera_input = get_input_dialog("Camera make & model:", "Camera")
    camera_make, camera_model = parse_make_model(camera_input)

    # Get lens make and model (optional)
    lens_input = get_input_dialog("Lens make & model:", "Lens (optional)")
    lens_make = lens_model = ""

    if lens_input.strip():
        lens_make, lens_model = parse_make_model(lens_input)

    # Get film
    film = get_input_dialog("Film:", "Film")

    return {
        "cameraMake": camera_make,
        "cameraModel": camera_model,
        "lensMake": lens_make,
        "lensModel": lens_model,
        "film": film,
    }


def load_or_create_metadata(directory: str) -> Dict[str, str]:
    """Load metadata from JSON file or create it from user input."""
    metadata_file = os.path.join(directory, "metadata.json")

    if not os.path.isfile(metadata_file):
        show_dialog(
            "Directory has no metadata.json file.\\n\\nEnter values to create one.",
            "Error",
        )
        metadata = get_metadata_from_user()

        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata

    # Load existing metadata
    try:
        with open(metadata_file, "r") as f:
            metadata = json.load(f)
    except (json.JSONDecodeError, IOError):
        show_dialog(f"Invalid metadata.json in {directory}", "Error")
        return {}

    # Validate required fields
    required_fields = ["cameraMake", "cameraModel", "film"]
    for field in required_fields:
        if field not in metadata or metadata[field] is None:
            show_dialog(f"metadata.json in {directory} is missing {field}", "Error")
            return {}

    # Optional lens fields
    for field in ["lensMake", "lensModel"]:
        if field not in metadata or metadata[field] is None:
            metadata[field] = ""

    return metadata


def find_jpeg_files(directory: str) -> List[str]:
    """Find all JPEG files in directory."""
    jpeg_extensions = [".jpg", ".JPG", ".jpeg", ".JPEG"]
    files = []

    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            for ext in jpeg_extensions:
                if filename.endswith(ext):
                    files.append(filepath)
                    break

    return files


def find_xmp_sidecars(jpeg_file: str) -> List[str]:
    """Find corresponding XMP sidecar files for a JPEG."""
    xmp_files = []

    dir_name = os.path.dirname(jpeg_file)
    base_name = os.path.basename(jpeg_file)

    # get base filename without extension
    filename = base_name.split(".")[0]

    # but also get all extensions, except the last one
    extensions = base_name.split(".")[1:-1]

    for ext in [".xmp", ".XMP"]:
        xmp_file = pathlib.Path(dir_name) / (filename + ext)
        if os.path.isfile(xmp_file):
            xmp_files.append(xmp_file)

        for extension in extensions:
            xmp_file = pathlib.Path(dir_name) / (filename + f".{extension}" + ext)
            if os.path.isfile(xmp_file):
                xmp_files.append(xmp_file)

    return xmp_files


def update_file_metadata(args: Tuple[str, str, Dict[str, str]]) -> Tuple[str, bool]:
    """Update metadata for a single file (JPEG + optional XMP)."""
    exiftool_path, jpeg_file, metadata = args

    # Build exiftool command for JPEG
    jpeg_cmd = [
        exiftool_path,
        "-P",
        "-overwrite_original",
        f"-Make={metadata['cameraMake']}",
        f"-Model={metadata['cameraModel']}",
        f"-ImageDescription=film: {metadata['film']}",
        f"-XMP:Description=film: {metadata['film']}",
    ]

    # Add lens info if available
    if metadata["lensMake"]:
        jpeg_cmd.append(f"-LensMake={metadata['lensMake']}")
    if metadata["lensModel"]:
        jpeg_cmd.append(f"-LensModel={metadata['lensModel']}")

    jpeg_cmd.extend(["--", jpeg_file])

    # Update JPEG file
    try:
        subprocess.run(jpeg_cmd, capture_output=True, check=True)
        jpeg_success = True
    except subprocess.CalledProcessError:
        jpeg_success = False

    # Check for XMP sidecar file
    xmp_files = find_xmp_sidecars(jpeg_file)
    xmp_success = True  # Default to true since XMP is optional

    for xmp_file in xmp_files:
        # print(f"🚙 Updating XMP sidecar: {xmp_file}")

        # Build exiftool command for XMP
        xmp_cmd = [
            exiftool_path,
            "-P",
            "-overwrite_original",
            f"-XMP:Make={metadata['cameraMake']}",
            f"-XMP:Model={metadata['cameraModel']}",
            f"-XMP:Description=film: {metadata['film']}",
        ]

        # Add lens info if available
        if metadata["lensMake"]:
            xmp_cmd.append(f"-XMP:LensMake={metadata['lensMake']}")
        if metadata["lensModel"]:
            xmp_cmd.append(f"-XMP:LensModel={metadata['lensModel']}")

        xmp_cmd.extend(["--", xmp_file])

        try:
            subprocess.run(xmp_cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            xmp_success = False

    return jpeg_file, jpeg_success and xmp_success


def count_xmp_files(jpeg_files: List[str]) -> int:
    """Count how many JPEG files have corresponding XMP sidecar files."""
    count = 0
    for jpeg_file in jpeg_files:
        xmp_files = find_xmp_sidecars(jpeg_file)
        if xmp_files:
            count += len(xmp_files)
    return count


def main():
    if len(sys.argv) < 2:
        print("Usage: populate_exif_metadata.py <directory> [directory2] ...")
        sys.exit(1)

    # Find exiftool
    exiftool_path = find_exiftool()

    for directory in sys.argv[1:]:
        if not os.path.isdir(directory):
            show_dialog(f"Directory not found: {directory}", "Error")
            continue

        # Load or create metadata
        metadata = load_or_create_metadata(directory)
        if not metadata:
            continue

        # Find JPEG files
        jpeg_files = find_jpeg_files(directory)

        if not jpeg_files:
            show_dialog("No JPEG files found.", "Info")
            continue

        # Count XMP sidecar files
        xmp_count = count_xmp_files(jpeg_files)

        # Process files in parallel
        max_workers = 20
        success_files = []
        error_files = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Prepare arguments for each file
            file_args = [
                (exiftool_path, jpeg_file, metadata) for jpeg_file in jpeg_files
            ]

            # Submit all tasks
            future_to_file = {
                executor.submit(update_file_metadata, args): args[1]
                for args in file_args
            }

            # Collect results
            for future in concurrent.futures.as_completed(future_to_file):
                jpeg_file, success = future.result()
                if success:
                    success_files.append(jpeg_file)
                else:
                    error_files.append(jpeg_file)

        # Show summary
        success_count = len(success_files)
        error_count = len(error_files)
        total = success_count + error_count

        if error_count == 0:
            if xmp_count > 0:
                message = f"{success_count} of {total} JPEG file(s) updated.\\n{xmp_count} XMP sidecar file(s) also updated."
            else:
                message = f"{success_count} of {total} JPEG file(s) updated.\\nNo XMP sidecar files found."

            show_dialog(message, "ExifTool: Success")
        else:
            first_error = error_files[0] if error_files else ""
            if xmp_count > 0:
                message = f"{success_count} succeeded, {error_count} failed.\\n{xmp_count} XMP sidecar file(s) processed.\\nFirst error: {first_error}"
            else:
                message = f"{success_count} succeeded, {error_count} failed.\\nNo XMP sidecar files found.\\nFirst error: {first_error}"

            show_dialog(message, "ExifTool: Completed with errors")


if __name__ == "__main__":
    main()

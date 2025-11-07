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

        # Process files in parallel
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

        # Show summary
        success_count = len(success_files)
        error_count = len(error_files)
        total = success_count + error_count

        msg_header = f"📂 {dir_name}\\n\\n"

        if error_count == 0:
            message = f"{msg_header}✅ {success_count}/{total} timestamps aligned"
            show_toast("Processing completed", message=message)
        else:
            first_error = os.path.basename(error_files[0]) if error_files else ""
            message = f"{msg_header}✅ {success_count}, ❌ {error_count}.\\nFirst error: {first_error}"
            show_toast("Processing completed with errors", message=message)


if __name__ == "__main__":
    main()

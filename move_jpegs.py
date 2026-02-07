#!/opt/homebrew/bin/python3

# AppleScript to run this script from Automator
# on run {input, parameters}
# 	set argList to ""
# 	repeat with anItem in input
# 		set argList to argList & " " & quoted form of (POSIX path of anItem)
# 	end repeat
# 	set cmd to "/opt/homebrew/bin/python3 /Users/diversario/Documents/Projects/Personal/photography-thingies/move_jpegs.py" & argList
# 	do shell script cmd
# end run

import sys
import os
import subprocess
import shutil
from pathlib import Path
from typing import List, Set


# DRY RUN MODE - set to False to actually perform actions
DRY_RUN = False


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


def log_debug(message: str):
    """Print a debug message."""
    print(f"[DEBUG] {message}")


def find_jpegs_in_directory(directory: str) -> List[str]:
    """Find all JPEG files in a directory (non-recursive)."""
    jpeg_extensions = [".jpg", ".JPG", ".jpeg", ".JPEG"]
    files = []

    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            if any(filename.endswith(ext) for ext in jpeg_extensions):
                files.append(filepath)

    return files


def get_jpeg_filenames(filepaths: List[str]) -> Set[str]:
    """Extract just the filenames from a list of file paths."""
    return {os.path.basename(f) for f in filepaths}


def move_jpegs_from_negatives(root_dir: str) -> bool:
    """
    Move JPEGs from negatives subfolder to root directory.
    Delete JPEGs in root that weren't in negatives.

    Returns True if successful, False otherwise.
    """
    negatives_dir = os.path.join(root_dir, "negatives")

    # Check if negatives subfolder exists
    if not os.path.isdir(negatives_dir):
        log_debug(f"No 'negatives' subfolder found in {root_dir}")
        return False

    log_debug(f"Found 'negatives' subfolder: {negatives_dir}")

    # Find JPEGs in negatives subfolder
    negatives_jpegs = find_jpegs_in_directory(negatives_dir)
    negatives_filenames = get_jpeg_filenames(negatives_jpegs)

    log_debug(f"Found {len(negatives_jpegs)} JPEG(s) in negatives subfolder:")
    for f in negatives_jpegs:
        log_debug(f"  - {os.path.basename(f)}")

    if not negatives_jpegs:
        log_debug("No JPEGs found in negatives subfolder, nothing to do")
        return True

    # Find JPEGs currently in root directory
    root_jpegs = find_jpegs_in_directory(root_dir)
    root_filenames = get_jpeg_filenames(root_jpegs)

    log_debug(f"Found {len(root_jpegs)} JPEG(s) in root directory:")
    for f in root_jpegs:
        log_debug(f"  - {os.path.basename(f)}")

    # Determine which files to delete (in root but not in negatives)
    files_to_delete = root_filenames - negatives_filenames

    log_debug(f"\nFiles to DELETE from root ({len(files_to_delete)}):")
    for filename in sorted(files_to_delete):
        filepath = os.path.join(root_dir, filename)
        log_debug(f"  - {filename}")
        if not DRY_RUN:
            os.remove(filepath)
            log_debug(f"    DELETED: {filepath}")
        else:
            log_debug(f"    [DRY RUN] Would delete: {filepath}")

    # Move/copy JPEGs from negatives to root
    files_to_move = negatives_filenames
    files_overwritten = negatives_filenames & root_filenames
    files_new = negatives_filenames - root_filenames

    log_debug(f"\nFiles to MOVE from negatives to root ({len(files_to_move)}):")
    log_debug(f"  - New files: {len(files_new)}")
    log_debug(f"  - Overwrites: {len(files_overwritten)}")

    for jpeg_path in negatives_jpegs:
        filename = os.path.basename(jpeg_path)
        dest_path = os.path.join(root_dir, filename)
        action = "OVERWRITE" if filename in files_overwritten else "MOVE"

        log_debug(f"  - {filename} ({action})")
        if not DRY_RUN:
            shutil.move(jpeg_path, dest_path)
            log_debug(f"    MOVED: {jpeg_path} -> {dest_path}")
        else:
            log_debug(f"    [DRY RUN] Would move: {jpeg_path} -> {dest_path}")

    return True


def main():
    """
    Move JPEGs from negatives subfolder to root directory.
    Delete JPEGs in root that weren't in negatives.
    """
    if len(sys.argv) < 2:
        print("Usage: move_jpegs.py <directory> [directory2] ...")
        sys.exit(1)

    if DRY_RUN:
        print("=" * 60)
        print("DRY RUN MODE - No files will be modified")
        print("=" * 60)
        print()

    for directory in sys.argv[1:]:
        if not os.path.isdir(directory):
            print(f"❌ Directory not found: {directory}")
            continue

        dir_name = os.path.basename(os.path.normpath(directory))

        log_debug(f"Processing directory: {directory}")
        log_debug(f"Directory name: {dir_name}")
        print()

        # Show notification that processing is starting
        show_toast("⚡️ Processing started", message=f"📁 Moving JPEGs in {dir_name}...")

        success = move_jpegs_from_negatives(directory)

        if success:
            if DRY_RUN:
                message = f"📂 {dir_name}\\n\\n[DRY RUN] Would sync JPEGs from negatives"
            else:
                message = f"📂 {dir_name}\\n\\n✅ JPEGs synced from negatives"
            show_toast("Processing completed", message=message)
            print(f"\n✅ Finished processing {dir_name}")
        else:
            message = f"📂 {dir_name}\\n\\n⚠️ No negatives subfolder found"
            show_toast("Processing skipped", message=message)
            print(f"\n⚠️ Skipped {dir_name} - no negatives subfolder")

        print()


if __name__ == "__main__":
    main()

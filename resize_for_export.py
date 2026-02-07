#!/opt/homebrew/bin/python3

# AppleScript to run this script from Automator
# on run {input, parameters}
# 	set argList to ""
# 	repeat with anItem in input
# 		set argList to argList & " " & quoted form of (POSIX path of anItem)
# 	end repeat
# 	set cmd to "/opt/homebrew/bin/python3 /Users/diversario/Documents/Projects/Personal/photography-thingies/resize-for-export.py" & argList
# 	do shell script cmd
# end run

import sys
import os
import subprocess
import shutil
import concurrent.futures
from pathlib import Path
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


def find_magick() -> str:
    """Find ImageMagick's magick executable."""
    # Add common paths for Homebrew
    paths = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"]

    for path in paths:
        magick_path = os.path.join(path, "magick")
        if shutil.which(magick_path):
            return magick_path

    # Try system PATH
    magick_path = shutil.which("magick")
    if magick_path:
        return magick_path

    print("ImageMagick not found. Install with: brew install imagemagick")
    sys.exit(1)


def get_export_path(original_file: str) -> str:
    """Generate export path: ~/Pictures/exports/original-dir-name/original-file-name"""
    home = Path.home()
    original_path = Path(original_file).resolve()

    # Get the parent directory name
    parent_dir_name = original_path.parent.name

    # Create export directory structure
    export_dir = home / "Pictures" / "exports" / parent_dir_name
    export_dir.mkdir(parents=True, exist_ok=True)

    # Return full export path
    return str(export_dir / original_path.name)


def find_jpeg_files(directory: str) -> List[str]:
    """Find all JPEG files in directory and all subdirectories."""
    jpeg_extensions = [".jpg", ".JPG", ".jpeg", ".JPEG"]
    files = []

    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if any(filename.endswith(ext) for ext in jpeg_extensions):
                filepath = os.path.join(root, filename)
                files.append(filepath)

    return files


def resize_image(args: Tuple[str, str]) -> Tuple[str, bool]:
    """Resize a single image to max 3000px while maintaining aspect ratio."""
    magick_path, image_file = args

    try:
        export_path = get_export_path(image_file)

        # magick input.jpg -resize 3000x3000\> output.jpg
        # The \> flag means "only shrink larger images"
        cmd = [
            magick_path,
            image_file,
            "-resize",
            "3000x3000>",
            export_path,
        ]

        subprocess.run(cmd, capture_output=True, check=True)
        return image_file, True
    except Exception as e:
        print(f"Error resizing {os.path.basename(image_file)}: {e}")
        return image_file, False


def main():
    """
    Resize images to a maximum dimension of 3000 pixels while maintaining aspect ratio
    and write them out to ~/Pictures/exports/$original-dir-name/$original-file-name
    """
    if len(sys.argv) < 2:
        print("Usage: resize-for-export.py [directory1 directory2 | file1.jpg file2.png] ...")
        sys.exit(1)

    # Find ImageMagick
    magick_path = find_magick()

    # Get all image files from arguments (files or directories)
    image_files = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            # Recursively find all JPEGs in the directory
            found_files = find_jpeg_files(arg)
            image_files.extend(found_files)
            print(f"Found {len(found_files)} JPEG(s) in directory: {arg}")
        elif os.path.isfile(arg):
            # Filter to JPEGs only
            if arg.lower().endswith((".jpg", ".jpeg")):
                image_files.append(arg)
            else:
                print(f"Warning: {arg} is not a JPEG, skipping")
        else:
            print(f"Warning: {arg} is not a file or directory, skipping")

    if not image_files:
        print("No valid image files provided")
        sys.exit(1)

    # Show notification that processing is starting
    show_toast("⚡️ Processing started", message=f"📐 Resizing {len(image_files)} image(s)...")

    # Process files in parallel
    max_workers = 8  # ImageMagick can be CPU intensive
    success_files = []
    error_files = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Prepare arguments for each file
        file_args = [
            (magick_path, image_file) for image_file in image_files
        ]

        # Submit all tasks
        future_to_file = {
            executor.submit(resize_image, args): args[1]
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

    if error_count == 0:
        message = f"✅ {success_count}/{total} images resized"
        show_toast("Processing completed", message=message)
        print(f"✅ Successfully resized {success_count} image(s)")
        print(f"📁 Exported to: ~/Pictures/exports/")
    else:
        first_error = os.path.basename(error_files[0]) if error_files else ""
        message = f"✅ {success_count}, ❌ {error_count}.\\nFirst error: {first_error}"
        show_toast("Processing completed with errors", message=message)
        print(f"⚠️ {success_count} succeeded, {error_count} failed")


if __name__ == "__main__":
    main()

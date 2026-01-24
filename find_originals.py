#!/opt/homebrew/bin/python3

# Arguments: --copies <copies directory> --originals <originals directory> [options]

# Given a path to `copies directory`, read all filenames in the `thumbs/` subdirectory
# there. Find the files with the same names in the `originals directory` and copy them
# to the <copies directory>/originals/ subdirectory. If the original files have a
# corresponding .xmp file, copy that too if the option to do that is set.

# If there is a filename conflict, append a number to the filename and to the .xmp file to make it unique, and log the change.

# Options:
#   -n : dry run, do not actually copy files
#   -v : verbose, print more information about what is being done
#   --copy-xmp : also copy .xmp files if they exist for the original files
#   --date-start <YYYY-MM-DD> : only consider files in the originals directory whose name starts on or after the given date (example dir name `YYYY-MM-DD Some place`)
#   --date-end <YYYY-MM-DD> : only consider files in the originals directory whose name starts on or before the given date (example dir name `YYYY-MM-DD Some place`)

import argparse
import os
import shutil
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Find original files matching thumbs and copy them to an originals directory."
    )
    parser.add_argument("--copies", required=True, help="Path to the copies directory containing thumbs/")
    parser.add_argument("--originals", required=True, help="Path to the originals directory to search")
    parser.add_argument("-n", "--dry-run", action="store_true", default=True, help="Dry run, do not actually copy files (default)")
    parser.add_argument("--no-dry-run", action="store_false", dest="dry_run", help="Actually copy files")
    parser.add_argument("-v", "--verbose", action="store_true", default=True, help="Verbose, print more information")
    parser.add_argument("--no-missing-report", action="store_false", dest="missing_report", help="Do not report missing files")
    parser.add_argument("--copy-xmp", action="store_true", default=False, help="Also copy .xmp files if they exist")
    parser.add_argument("--date-start", metavar="YYYY-MM-DD", help="Only consider originals directories on or after this date (inclusive)")
    parser.add_argument("--date-end", metavar="YYYY-MM-DD", help="Only consider originals directories on or before this date (inclusive)")
    return parser.parse_args()


def parse_date(date_str):
    """Parse a YYYY-MM-DD date string."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def extract_date_from_dirname(dirname):
    """Extract date from directory name starting with YYYY-MM-DD."""
    # Try to extract the first 10 characters as a date (YYYY-MM-DD)
    if len(dirname) >= 10:
        date_part = dirname[:10]
        parsed = parse_date(date_part)
        if parsed:
            return parsed

    # Fallback: split on space and strip non-alphanumeric chars
    parts = dirname.split(" ")
    if parts:
        # Strip trailing punctuation like comma
        date_str = parts[0].rstrip(',-_')
        return parse_date(date_str)
    return None


def is_dir_in_date_range(dirname, date_start, date_end):
    """Check if directory falls within the specified date range (inclusive)."""
    dir_date = extract_date_from_dirname(dirname)
    if dir_date is None:
        # If we can't parse a date from the directory name, exclude it
        return False

    if date_start and dir_date < date_start:
        return False
    if date_end and dir_date > date_end:
        return False

    return True


def get_thumb_filenames(thumbs_dir):
    """Get all filenames from the thumbs directory."""
    if not os.path.isdir(thumbs_dir):
        print(f"Error: Thumbs directory does not exist: {thumbs_dir}")
        return set()

    filenames = set()
    for filename in os.listdir(thumbs_dir):
        filepath = os.path.join(thumbs_dir, filename)
        if os.path.isfile(filepath):
            filenames.add(filename)
    return filenames


VALID_EXTENSIONS = {'.jpeg', '.jpg', '.JPEG', '.JPG'}

# RAW extensions that may appear before the final JPEG extension (e.g., .CR3.jpg)
RAW_EXTENSIONS = {'.cr3', '.cr2', '.nef', '.arw', '.raf', '.orf', '.dng', '.rw2'}


def build_basename_map(filenames):
    """Build a map of lowercase basenames to original filenames."""
    basenames_to_find = {}
    for filename in filenames:
        base, ext = os.path.splitext(filename)
        base_lower = base.lower()
        basenames_to_find[base_lower] = (filename, None)
    return basenames_to_find


def matches_basename(file_base, search_bases):
    """
    Check if file_base matches any search base name.

    Matching rules:
    - Exact match (file_base == search_base)
    - search_base followed by a space, dash, or underscore (e.g., "IMG_0002 1", "IMG_0002-edit")

    Does NOT match if search_base is followed by a dot (to avoid IMG_0002 matching IMG_0002.CR3).

    When multiple patterns match, prefer the longest (most specific) match.

    Returns the original thumb filename if matched, None otherwise.
    """
    file_base_lower = file_base.lower()

    best_match = None
    best_match_len = 0

    # Debug: check if this specific file is being searched
    if 'img_0002' in file_base_lower:
        print(f"DEBUG: Checking file_base='{file_base_lower}'")
        print(f"DEBUG: Looking for 'img_0002.cr3' in search_bases: {'img_0002.cr3' in search_bases}")

    for base_lower, (original_filename, _) in search_bases.items():
        # Check for exact match
        if file_base_lower == base_lower:
            if 'img_0002' in file_base_lower:
                print(f"DEBUG: EXACT MATCH: '{file_base_lower}' == '{base_lower}' -> {original_filename}")
            if len(base_lower) > best_match_len:
                best_match = original_filename
                best_match_len = len(base_lower)
            continue

        # Check if file starts with base and is followed by allowed separator
        if file_base_lower.startswith(base_lower):
            remainder = file_base_lower[len(base_lower):]
            if remainder:
                # Allow: space, dash, underscore
                if remainder[0] in ' -_':
                    if len(base_lower) > best_match_len:
                        best_match = original_filename
                        best_match_len = len(base_lower)
                # Allow: dot followed by RAW extension (e.g., .CR3)
                elif remainder[0] == '.':
                    # Check if remainder is a known RAW extension
                    ext_part = remainder.split('.')[1] if '.' in remainder[1:] else remainder[1:]
                    if f'.{ext_part.lower()}' in RAW_EXTENSIONS or f'.{remainder[1:].lower()}' in RAW_EXTENSIONS:
                        if len(base_lower) > best_match_len:
                            best_match = original_filename
                            best_match_len = len(base_lower)

    if 'img_0002' in file_base_lower:
        print(f"DEBUG: best_match for '{file_base_lower}' = {best_match}")

    return best_match


def get_filtered_directories(originals_dir, date_start, date_end, verbose):
    """Filter top-level directories based on date range."""
    try:
        top_level_entries = os.listdir(originals_dir)
    except OSError as e:
        print(f"Error reading originals directory: {e}")
        return []

    filtered_dirs = []
    for entry in top_level_entries:
        entry_path = os.path.join(originals_dir, entry)
        if os.path.isdir(entry_path):
            if is_dir_in_date_range(entry, date_start, date_end):
                filtered_dirs.append(entry_path)
            elif verbose:
                print(f"Skipping directory (date filter): {entry}")

    return filtered_dirs


def find_originals(originals_dir, filenames, date_start, date_end, verbose):
    """
    Search the originals directory for files matching the given filenames.
    The original file may have a different extension, so look for files with the
    same name and any of these extensions:
      - JPEG, JPG, jpeg, jpg

    The original file name may have a suffix after it, such as `$name $number.jpg`.

    Additionally, there may be a .CR3 extension _before_ the .jpg extension, e.g., `$name.CR3.jpg`.

    Copy all files whose base name matches the searched name and is followed by some
    sort of a separator (space, underscore, dash) plus a number, and potentially an extra
    extension like .CR3 before the final extension.

    Returns a dict mapping filename -> list of full paths to the original files.
    """
    found = {}
    basenames_to_find = build_basename_map(filenames)

    if date_start is None and date_end is None:
        filtered_dirs = [originals_dir]
    else:
        filtered_dirs = get_filtered_directories(originals_dir, date_start, date_end, verbose)

    if verbose:
        print(f"Searching in {len(filtered_dirs)} directories after applying date filters:")
        for d in filtered_dirs:
            print(f"  {d}")

    # Search for files in the filtered directories
    for dir_path in filtered_dirs:
        for root, dirs, files in os.walk(dir_path):
            # Skip directories whose path contains 'Photobook' (case-insensitive)
            if 'photobook/' in root.lower():
                continue

            for filename in files:
                if verbose:
                    print(f"Checking file: {os.path.join(root, filename)}")

                base, ext = os.path.splitext(filename)

                # Check if this file has a valid extension and matches a thumb basename
                if ext in VALID_EXTENSIONS:
                    original_thumb_name = matches_basename(base, basenames_to_find)
                    if original_thumb_name:
                        file_path = os.path.join(root, filename)
                        if original_thumb_name not in found:
                            found[original_thumb_name] = []
                        found[original_thumb_name].append(file_path)
                        if verbose:
                            print(f"Found original: {filename} at {file_path}")

    return found


def get_unique_dest_path(dest_dir, filename):
    """
    Get a unique destination path. If the file already exists,
    append a number to make it unique.
    Returns (new_filename, was_renamed)
    """
    base, ext = os.path.splitext(filename)
    dest_path = os.path.join(dest_dir, filename)

    if not os.path.exists(dest_path):
        return filename, False

    counter = 1
    while True:
        new_filename = f"{base}_{counter}{ext}"
        dest_path = os.path.join(dest_dir, new_filename)
        if not os.path.exists(dest_path):
            return new_filename, True
        counter += 1


def copy_file(src, dest, dry_run, verbose):
    """Copy a file, respecting dry_run flag."""
    if dry_run:
        print(f"[DRY RUN] Would copy: {src} -> {dest}")
    else:
        shutil.copy2(src, dest)
        if verbose:
            print(f"Copied: {src} -> {dest}")


def main():
    args = parse_args()

    copies_dir = os.path.abspath(args.copies)
    originals_dir = os.path.abspath(args.originals)
    thumbs_dir = os.path.join(copies_dir, "thumbs")
    dest_dir = os.path.join(copies_dir, "originals")

    # Validate directories exist
    if not os.path.isdir(copies_dir):
        print(f"Error: Copies directory does not exist: {copies_dir}")
        return 1
    if not os.path.isdir(originals_dir):
        print(f"Error: Originals directory does not exist: {originals_dir}")
        return 1

    # Parse date filters
    date_start = parse_date(args.date_start) if args.date_start else None
    date_end = parse_date(args.date_end) if args.date_end else None

    if args.date_start and not date_start:
        print(f"Error: Invalid date format for --date-start: {args.date_start}")
        return 1
    if args.date_end and not date_end:
        print(f"Error: Invalid date format for --date-end: {args.date_end}")
        return 1

    # Get thumb filenames
    thumb_filenames = get_thumb_filenames(thumbs_dir)
    if not thumb_filenames:
        print("No files found in thumbs directory.")
        return 1

    if args.verbose:
        print(f"Found {len(thumb_filenames)} files in thumbs directory")

    # Find originals
    found_originals = find_originals(originals_dir, thumb_filenames, date_start, date_end, args.verbose)

    if not found_originals:
        print("No matching original files found.")
        return 1

    print(f"Found {len(found_originals)} matching original files out of {len(thumb_filenames)} thumbs")

    # Build list of copy tasks (src, dest, is_xmp)
    copy_tasks = []
    renamed_files = []

    for original_filename, original_paths in found_originals.items():
        for original_path in original_paths:
            # Use the actual filename from the original path
            actual_filename = os.path.basename(original_path)

            # Get unique destination filename
            dest_filename, was_renamed = get_unique_dest_path(dest_dir, actual_filename)
            dest_path = os.path.join(dest_dir, dest_filename)

            if was_renamed:
                renamed_files.append((actual_filename, dest_filename))
                print(f"Filename conflict: {actual_filename} -> {dest_filename}")

            # Add main file copy task
            copy_tasks.append((original_path, dest_path))

            # Handle .xmp file if requested
            if args.copy_xmp:
                xmp_src = original_path + ".xmp"
                if os.path.exists(xmp_src):
                    xmp_dest_filename = dest_filename + ".xmp"
                    xmp_dest_path = os.path.join(dest_dir, xmp_dest_filename)
                    copy_tasks.append((xmp_src, xmp_dest_path))
                elif args.verbose:
                    print(f"No .xmp file found for: {actual_filename}")

    # Copy files in parallel (2 workers)
    copied_count = 0

    def do_copy(task):
        src, dest = task
        copy_file(src, dest, args.dry_run, args.verbose)
        return 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(do_copy, task) for task in copy_tasks]
        for future in as_completed(futures):
            copied_count += future.result()

    # Summary
    action = "Would copy" if args.dry_run else "Copied"
    print(f"\n{action} {copied_count} files to {dest_dir}")

    if renamed_files:
        print(f"\nRenamed {len(renamed_files)} files due to conflicts:")
        for original, renamed in renamed_files:
            print(f"  {original} -> {renamed}")

    if args.missing_report:
      # Report missing files
      missing = thumb_filenames - set(found_originals.keys())
      if missing:
          print(f"\nCould not find originals for {len(missing)} files:")
          for filename in sorted(missing):
              print(f"  {filename}")

    print("DEBUG: Exiting main()", flush=True)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

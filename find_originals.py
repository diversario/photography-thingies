#!/opt/homebrew/bin/python3

# Arguments: [options] <copies directory> <originals directory>

# Given a path to `copies directory`, read all filenames in the `thumbs/` subdirectory
# there. Find the files with the same names in the `originals directory` and copy them
# to the <copies directory>/originals/ subdirectory. If the original files have a
# corresponding .xmp file, copy that too if the option to do that is set.

# If there is a filename conflict, append a number to the filename and to the .xmp file to make it unique, and log the change.

# Options:
#   -n : dry run, do not actually copy files
#   -v : verbose, print more information about what is being done
#   --copy-xmp : also copy .xmp files if they exist for the original files
#   --before <YYYY-MM-DD> : only consider files in the originals directory whose name starts before the given date (example dir name `YYYY-MM-DD Some place`)
#   --after <YYYY-MM-DD> : only consider files in the originals directory whose name starts after the given date (example dir name `YYYY-MM-DD Some place`)

import argparse
import os
import shutil
import re
from datetime import datetime
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Find original files matching thumbs and copy them to an originals directory."
    )
    parser.add_argument("copies_directory", help="Path to the copies directory containing thumbs/")
    parser.add_argument("originals_directory", help="Path to the originals directory to search")
    parser.add_argument("-n", "--dry-run", action="store_true", default=True, help="Dry run, do not actually copy files")
    parser.add_argument("-v", "--verbose", action="store_true", default=True, help="Verbose, print more information")
    parser.add_argument("--copy-xmp", action="store_true", default=False, help="Also copy .xmp files if they exist")
    parser.add_argument("--before", metavar="YYYY-MM-DD", help="Only consider originals directories before this date")
    parser.add_argument("--after", metavar="YYYY-MM-DD", help="Only consider originals directories after this date")
    return parser.parse_args()


def parse_date(date_str):
    """Parse a YYYY-MM-DD date string."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def extract_date_from_dirname(dirname):
    """Extract date from directory name starting with YYYY-MM-DD."""
    parts = dirname.split(" ")
    if parts:
        return parse_date(parts[0])
    return None


def is_dir_in_date_range(dirname, before_date, after_date):
    """Check if directory falls within the specified date range."""
    dir_date = extract_date_from_dirname(dirname)
    if dir_date is None:
        # If we can't parse a date from the directory name, include it
        return False

    if before_date and dir_date >= before_date:
        return False
    if after_date and dir_date <= after_date:
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


def find_originals(originals_dir, filenames, before_date, after_date, verbose):
    """
    Search the originals directory for files matching the given filenames.
    Returns a dict mapping filename -> full path to the original file.
    """
    found = {}

    # First, filter top-level directories based on date filters
    try:
        top_level_entries = os.listdir(originals_dir)
    except OSError as e:
        print(f"Error reading originals directory: {e}")
        return found

    filtered_dirs = []
    for entry in top_level_entries:
        entry_path = os.path.join(originals_dir, entry)
        if os.path.isdir(entry_path):
            if is_dir_in_date_range(entry, before_date, after_date):
                filtered_dirs.append(entry_path)
            elif verbose:
                print(f"Skipping directory (date filter): {entry}")

    if verbose:
        print(f"Searching in {len(filtered_dirs)} directories after applying date filters")

    # Now search for files in the filtered directories
    for dir_path in filtered_dirs:
        for root, dirs, files in os.walk(dir_path):
            for filename in files:
                if filename in filenames and filename not in found:
                    found[filename] = os.path.join(root, filename)
                    if verbose:
                        print(f"Found original: {filename} at {found[filename]}")

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

    copies_dir = os.path.abspath(args.copies_directory)
    originals_dir = os.path.abspath(args.originals_directory)
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
    before_date = parse_date(args.before) if args.before else None
    after_date = parse_date(args.after) if args.after else None

    if args.before and not before_date:
        print(f"Error: Invalid date format for --before: {args.before}")
        return 1
    if args.after and not after_date:
        print(f"Error: Invalid date format for --after: {args.after}")
        return 1

    # Get thumb filenames
    thumb_filenames = get_thumb_filenames(thumbs_dir)
    if not thumb_filenames:
        print("No files found in thumbs directory.")
        return 1

    if args.verbose:
        print(f"Found {len(thumb_filenames)} files in thumbs directory")

    # Find originals
    found_originals = find_originals(originals_dir, thumb_filenames, before_date, after_date, args.verbose)

    if not found_originals:
        print("No matching original files found.")
        return 1

    print(f"Found {len(found_originals)} matching original files out of {len(thumb_filenames)} thumbs")

    # Copy files
    copied_count = 0
    renamed_files = []

    for original_filename, original_path in found_originals.items():
        # Get unique destination filename
        dest_filename, was_renamed = get_unique_dest_path(dest_dir, original_filename)
        dest_path = os.path.join(dest_dir, dest_filename)

        if was_renamed:
            renamed_files.append((original_filename, dest_filename))
            print(f"Filename conflict: {original_filename} -> {dest_filename}")

        # Copy the original file
        copy_file(original_path, dest_path, args.dry_run, args.verbose)
        copied_count += 1

        # Handle .xmp file if requested
        # TODO: this doesn't always work because some files are like $name.$ext.xmp
        # and others are like $name.xmp
        if args.copy_xmp:
            xmp_src = original_path + ".xmp"
            if os.path.exists(xmp_src):
                xmp_dest_filename = dest_filename + ".xmp"
                xmp_dest_path = os.path.join(dest_dir, xmp_dest_filename)
                copy_file(xmp_src, xmp_dest_path, args.dry_run, args.verbose)
            elif args.verbose:
                print(f"No .xmp file found for: {original_filename}")

    # Summary
    action = "Would copy" if args.dry_run else "Copied"
    print(f"\n{action} {copied_count} files to {dest_dir}")

    if renamed_files:
        print(f"\nRenamed {len(renamed_files)} files due to conflicts:")
        for original, renamed in renamed_files:
            print(f"  {original} -> {renamed}")

    # Report missing files
    missing = thumb_filenames - set(found_originals.keys())
    if missing:
        print(f"\nCould not find originals for {len(missing)} files:")
        for filename in sorted(missing):
            print(f"  {filename}")

    return 0


if __name__ == "__main__":
    exit(main())

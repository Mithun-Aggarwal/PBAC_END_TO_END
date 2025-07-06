#!/bin/bash

# ==============================================================================
# SCRIPT: process_json_recursively.sh
#
# DESCRIPTION:
#   This script recursively finds all .json files in a specified directory
#   and its subdirectories. It copies the first 10,000 lines of each into a
#   new .txt file in a single output folder.
#
#   To prevent name conflicts, the new filename is created from the relative
#   path of the original file (e.g., "subdir/data.json" becomes
#   "subdir_data_TIMESTAMP.txt").
#
# USAGE:
#   1. Save this file as "process_json_recursively.sh".
#   2. Make it executable: chmod +x process_json_recursively.sh
#   3. Run it in one of two ways:
#      - To process the current directory and its subfolders: ./process_json_recursively.sh
#      - To process a different directory: ./process_json_recursively.sh /path/to/your/folder
# ==============================================================================

# --- Configuration ---
# The number of lines (rows) to keep from the top of each file.
LINES_TO_KEEP=1000

# The directory to search for JSON files. Defaults to the current directory "."
TARGET_DIR="${1:-.}"

# The name of the subdirectory where all new .txt files will be saved.
# This keeps your project directory clean.
OUTPUT_DIR="processed_txt_files"

# --- Pre-flight Checks ---

# Resolve the absolute path of the target directory for robust path manipulation later
TARGET_DIR=$(realpath "$TARGET_DIR")

# Check if the target directory actually exists.
if [ ! -d "$TARGET_DIR" ]; then
  echo "Error: Directory '$TARGET_DIR' not found."
  exit 1
fi

# Create the output directory at the top level of the target directory.
# The "-p" flag ensures it doesn't throw an error if the directory already exists.
mkdir -p "${TARGET_DIR}/${OUTPUT_DIR}"
echo "Recursively searching for .json files in: $TARGET_DIR"
echo "Processed files will be saved in: ${TARGET_DIR}/${OUTPUT_DIR}"
echo "--------------------------------------------------"

# --- Main Processing Loop ---

# A counter to see if we actually found any files.
file_count=0

# Use 'find' to locate all files ending in .json in the target directory and all subdirectories.
# -type f ensures we only match files, not directories.
# We exclude our own output directory from the search to prevent re-processing files.
find "$TARGET_DIR" -type f -name "*.json" -not -path "*/${OUTPUT_DIR}/*" | while IFS= read -r json_file; do
  
  # Increment our counter
  ((file_count++))

  echo "Processing: $json_file"

  # --- Create a Unique and Descriptive Filename ---

  # Get the path of the json file relative to the target directory.
  # This is important for creating a unique name. e.g., "subdir/data.json"
  relative_path="${json_file#$TARGET_DIR/}"

  # Remove the .json extension from the relative path. e.g., "subdir/data"
  path_without_ext="${relative_path%.json}"

  # Replace all slashes '/' with underscores '_' to create a flat filename.
  # e.g., "subdir/data" becomes "subdir_data"
  sanitized_name="${path_without_ext//\//_}"

  # Create a unique timestamp (e.g., 20231027_153000).
  timestamp=$(date +%Y%m%d_%H%M%S)

  # Construct the new, unique filename for the .txt file.
  new_txt_filename="${sanitized_name}_${timestamp}.txt"
  
  # Define the full path for the new file inside our single output directory.
  output_path="${TARGET_DIR}/${OUTPUT_DIR}/${new_txt_filename}"

  # Use the 'head' command to take the first N lines of the JSON file
  # and redirect (>) the output to create the new .txt file.
  head -n "$LINES_TO_KEEP" "$json_file" > "$output_path"

  echo "  -> Saved first $LINES_TO_KEEP lines to: $new_txt_filename"
done

# --- Final Report ---

echo "--------------------------------------------------"
if [ "$file_count" -eq 0 ]; then
  echo "No .json files were found in '$TARGET_DIR' or its subdirectories."
else
  echo "Processing complete. Total files processed: $file_count."
fi
#!/bin/bash

# ==============================================================================
# SCRIPT: process_json.sh
#
# DESCRIPTION:
#   This script finds all .json files in a specified directory, copies the
#   first 10,000 lines of each into a new .txt file, and gives each new
#   file a unique name based on the original filename and a timestamp.
#
# USAGE:
#   1. Save this file as "process_json.sh".
#   2. Make it executable: chmod +x process_json.sh
#   3. Run it in one of two ways:
#      - To process the current directory: ./process_json.sh
#      - To process a different directory: ./process_json.sh /path/to/your/folder
#
# LLM ANALYSIS NOTE:
#   The resulting .txt files are truncated to the first 10,000 lines to keep
#   them a manageable size for Large Language Model (LLM) context windows.
# ==============================================================================

# --- Configuration ---
# The number of lines (rows) to keep from the top of each file.
# You can change this value if needed.
LINES_TO_KEEP=10000

# The directory to search for JSON files.
# It defaults to the current directory "." if no argument is provided.
# The ${1:-.} syntax means: use the first argument ($1), or use "." if it's not set.
TARGET_DIR="${1:-.}"

# The name of the subdirectory where the new .txt files will be saved.
# This keeps your original directory clean.
OUTPUT_DIR="processed_txt_files"

# --- Pre-flight Checks ---

# Check if the target directory actually exists.
if [ ! -d "$TARGET_DIR" ]; then
  echo "Error: Directory '$TARGET_DIR' not found."
  exit 1
fi

# Create the output directory inside the target directory.
# The "-p" flag ensures it doesn't throw an error if the directory already exists.
mkdir -p "${TARGET_DIR}/${OUTPUT_DIR}"
echo "Searching for .json files in: $TARGET_DIR"
echo "Processed files will be saved in: ${TARGET_DIR}/${OUTPUT_DIR}"
echo "--------------------------------------------------"

# --- Main Processing Loop ---

# A counter to see if we actually found any files.
file_count=0

# Use 'find' to locate all files ending in .json in the target directory.
# We use "-maxdepth 1" to only search the top-level of the directory, not subdirectories.
# We pipe the results into a 'while read' loop. This is the safest way to handle
# filenames that might contain spaces or other special characters.
find "$TARGET_DIR" -maxdepth 1 -name "*.json" | while IFS= read -r json_file; do
  
  # Increment our counter
  ((file_count++))

  echo "Processing: $json_file"

  # Get the base name of the file (e.g., "my_data" from "/path/to/my_data.json").
  base_name=$(basename "$json_file" .json)

  # Create a unique timestamp (e.g., 20231027_153000).
  timestamp=$(date +%Y%m%d_%H%M%S)

  # Construct the new, unique filename for the .txt file.
  new_txt_filename="${base_name}_${timestamp}.txt"
  
  # Define the full path for the new file inside our output directory.
  output_path="${TARGET_DIR}/${OUTPUT_DIR}/${new_txt_filename}"

  # Use the 'head' command to take the first N lines of the JSON file
  # and redirect (>) the output to create the new .txt file.
  head -n "$LINES_TO_KEEP" "$json_file" > "$output_path"

  echo "  -> Saved first $LINES_TO_KEEP lines to: $new_txt_filename"
done

# --- Final Report ---

echo "--------------------------------------------------"
if [ "$file_count" -eq 0 ]; then
  echo "No .json files were found in '$TARGET_DIR'."
else
  echo "Processing complete. Total files processed: $file_count."
fi
#!/bin/bash

# This script helps identify common files/folders that might be good candidates
# for exclusion in a .gitignore file.
# It does NOT directly generate a .gitignore file, but rather a list for review.

OUTPUT_FILE="potential_gitignore_candidates.txt"

echo "Generating potential .gitignore candidates to $OUTPUT_FILE..."
echo "--- Common Build/Dependency Folders ---" > "$OUTPUT_FILE"
find . -maxdepth 2 -type d \( -name "node_modules" -o -name "venv" -o -name "__pycache__" -o -name "build" -o -name "dist" -o -name "target" -o -name ".gradle" -o -name "logs" -o -name "output" \) -print >> "$OUTPUT_FILE"

echo -e "\n--- Common Log/Temp Files ---" >> "$OUTPUT_FILE"
find . -type f \( -name "*.log" -o -name "*.tmp" -o -name "*.swp" -o -name "*.bak" \) -print >> "$OUTPUT_FILE"

echo -e "\n--- Common IDE/OS Files ---" >> "$OUTPUT_FILE"
find . -type d \( -name ".vscode" -o -name ".idea" \) -print >> "$OUTPUT_FILE"
find . -type f \( -name ".DS_Store" -o -name "Thumbs.db" \) -print >> "$OUTPUT_FILE"

echo -e "\n--- Other potential candidates (review carefully!) ---" >> "$OUTPUT_FILE"
# Add any other specific patterns you might want to look for
# For example, if you know you generate specific report files:
# find . -type f -name "*.report" -print >> "$OUTPUT_FILE"

echo "Scan complete. Please review '$OUTPUT_FILE' for patterns to add to your .gitignore."
echo "Remember to manually add rules to .gitignore (e.g., 'node_modules/' instead of './node_modules')."
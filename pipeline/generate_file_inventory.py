"""
File Inventory Generator
-------------------------
Scans a directory (input_folder) and generates an inventory CSV or JSON
containing filename, path, size, extension, and last modified time.
"""

import os
import argparse
import csv
import json
from pathlib import Path
from datetime import datetime

def scan_input_folder(input_folder: str, output_file: str, output_format: str = "csv"):
    records = []
    for root, _, files in os.walk(input_folder):
        for f in files:
            full_path = os.path.join(root, f)
            if not os.path.isfile(full_path):
                continue
            
            stat = os.stat(full_path)
            record = {
                "file_name": f,
                "relative_path": str(Path(full_path).relative_to(input_folder)),
                "size_kb": round(stat.st_size / 1024, 2),
                "extension": Path(f).suffix.lower().replace(".", ""),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            }
            records.append(record)

    if output_format == "csv":
        with open(output_file, mode="w", newline="") as out_csv:
            writer = csv.DictWriter(out_csv, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
    else:
        with open(output_file, "w") as out_json:
            json.dump(records, out_json, indent=2)

    print(f"✅ Inventory saved to {output_file} with {len(records)} entries.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_folder", required=True, help="Folder to scan")
    parser.add_argument("--output_file", default="input_inventory.csv", help="Where to save the inventory")
    parser.add_argument("--format", choices=["csv", "json"], default="csv")
    args = parser.parse_args()

    scan_input_folder(args.input_folder, args.output_file, args.format)

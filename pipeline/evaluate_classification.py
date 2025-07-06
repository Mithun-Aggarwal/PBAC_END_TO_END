# evaluate_classification.py

"""
Evaluate LLM classification output vs. manually curated golden dataset.
Calculates precision, recall, and accuracy across classification labels.
"""

import os
import json
from sklearn.metrics import classification_report, confusion_matrix
from collections import defaultdict
from glob import glob

# Paths
GOLDEN_DIR = "/home/mit/Learning_and_growing/AI_DATA_EXTRACTION_AND_SEARCH_V1/Curated_information/documents/golden_dataset"
LLM_OUTPUT_DIR = "/home/mit/Learning_and_growing/AI_DATA_EXTRACTION_AND_SEARCH_V1/Curated_information/documents/golden_dataset_manual"


# Load ground truth

def load_labels(directory):
    labels = {}
    for file in glob(os.path.join(directory, "*.json")):
        with open(file) as f:
            data = json.load(f)
            fname = os.path.basename(file)
            label = data.get("metadata", {}).get("detected_type")
            if label:
                labels[fname] = label if isinstance(label, str) else label[0]  # flatten if multi-label
    return labels

# Compare

def evaluate():
    y_true = []
    y_pred = []
    
    golden = load_labels(GOLDEN_DIR)
    predicted = load_labels(LLM_OUTPUT_DIR)

    all_files = set(golden.keys()) & set(predicted.keys())
    if not all_files:
        print("❌ No overlapping files to compare.")
        return

    print(f"🔍 Evaluating {len(all_files)} files with both golden & predicted labels\n")

    for fname in sorted(all_files):
        y_true.append(golden[fname])
        y_pred.append(predicted[fname])

    print("📊 Classification Report:")
    print(classification_report(y_true, y_pred, digits=3))

    print("\n🧾 Confusion Matrix:")
    labels = sorted(set(y_true + y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    print(f"Labels: {labels}\n")
    for i, row in enumerate(cm):
        print(f"{labels[i]:<20}: {row}")

if __name__ == "__main__":
    evaluate()

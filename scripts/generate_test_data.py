#!/usr/bin/env python3
"""
Test Data Generator for BuildTrace Challenge

This script creates fake drawing pairs (simulated construction drawings) 
to test the diff system. Each drawing is a JSON file with geometric objects.
"""

import argparse
import json
import random
import sys
from pathlib import Path
from typing import List, Dict, Any

from google.cloud import storage
from tqdm import tqdm

# Add parent directory to path so we can import config if needed
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration - these match your GCP setup
PROJECT_ID = "buildtrace-challenge-476923"
BUCKET_NAME = "bt-challenge-buildtrace-challenge-476923"
INPUTS_PREFIX = "inputs"  # Files go in gs://bucket/inputs/


def generate_random_object(obj_id: str, existing_objects: List[Dict] = None) -> Dict[str, Any]:
    """Create one random geometric object (wall, door, or window)."""
    obj_type = random.choices(
        ["wall", "door", "window"], 
        weights=[70, 20, 10]  # More walls than doors/windows
    )[0]
    
    return {
        "id": obj_id,
        "type": obj_type,
        "x": random.randint(0, 100),
        "y": random.randint(0, 100),
        "width": random.randint(1, 10),
        "height": random.randint(1, 10)
    }


def generate_version_a(num_objects: int) -> List[Dict[str, Any]]:
    """Generate the original version of a drawing (Version A)."""
    objects = []
    for i in range(num_objects):
        obj_id = f"OBJ_{i}"
        obj = generate_random_object(obj_id)
        objects.append(obj)
    return objects


def generate_version_b(version_a: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate modified version (Version B) from Version A with random changes."""
    version_b = [obj.copy() for obj in version_a]
    
    if random.random() < 0.3:
        num_to_add = random.randint(1, 2)
        max_id = -1
        for obj in version_b:
            try:
                max_id = max(max_id, int(obj["id"].split("_")[1]))
            except (IndexError, ValueError):
                pass
        for i in range(num_to_add):
            new_id = f"OBJ_{max_id + i + 1}"
            version_b.append(generate_random_object(new_id))
    
    if random.random() < 0.3 and len(version_b) > 1:
        version_b.remove(random.choice(version_b))
    
    if random.random() < 0.5:
        for obj in random.sample(version_b, min(random.randint(1, 2), len(version_b))):
            obj["x"] = max(0, obj["x"] + random.randint(-10, 10))
            obj["y"] = max(0, obj["y"] + random.randint(-10, 10))
    
    return version_b


def upload_to_gcs(gcs_client: storage.Client, content: str, gcs_path: str) -> None:
    """Upload JSON content to Google Cloud Storage."""
    bucket = gcs_client.bucket(BUCKET_NAME)
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(content, content_type="application/json")


def generate_pair(pair_id: str, gcs_client: storage.Client) -> Dict[str, str]:
    """Generate one drawing pair (A and B) and upload to GCS."""
    version_a = generate_version_a(random.randint(3, 10))
    version_b = generate_version_b(version_a)
    
    path_a = f"{INPUTS_PREFIX}/{pair_id}_A.json"
    path_b = f"{INPUTS_PREFIX}/{pair_id}_B.json"
    
    upload_to_gcs(gcs_client, json.dumps(version_a, indent=2), path_a)
    upload_to_gcs(gcs_client, json.dumps(version_b, indent=2), path_b)
    
    return {
        "id": pair_id,
        "a": f"gs://{BUCKET_NAME}/{path_a}",
        "b": f"gs://{BUCKET_NAME}/{path_b}"
    }


def main():
    """Generate test data and upload to GCS."""
    parser = argparse.ArgumentParser(
        description="Generate random drawing pairs and upload to GCS for testing"
    )
    parser.add_argument(
        "--num-pairs",
        type=int,
        default=10,
        help="Number of drawing pairs to generate (default: 10)"
    )
    args = parser.parse_args()
    
    print("Connecting to Google Cloud Storage...")
    gcs_client = storage.Client(project=PROJECT_ID)
    
    print(f"Generating {args.num_pairs} drawing pairs...")
    manifest_pairs = []
    for i in tqdm(range(args.num_pairs), desc="Generating pairs"):
        pair_id = f"drawing-{i+1:04d}"
        manifest_pairs.append(generate_pair(pair_id, gcs_client))
    
    manifest_path = Path(__file__).parent.parent / "sample" / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({"pairs": manifest_pairs}, f, indent=2)
    
    # Print summary
    print(f"\n✅ Success!")
    print(f"Generated {args.num_pairs} pairs")
    print(f"Uploaded to: gs://{BUCKET_NAME}/{INPUTS_PREFIX}/")
    print(f"Manifest saved to: {manifest_path}")


if __name__ == "__main__":
    main()


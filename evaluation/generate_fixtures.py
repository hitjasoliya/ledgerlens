"""CLI helper to generate synthetic deterministic financial PDF fixtures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.fixtures import (
    AUDITED_REPORT_FILENAME,
    DRAFT_PROJECTIONS_FILENAME,
    compute_file_sha256,
    generate_evaluation_pdfs,
)


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic evaluation PDF fixtures")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory to save generated PDF fixtures (default: evaluation/)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    print(f"Generating synthetic financial PDF fixtures in: {output_dir}")
    files = generate_evaluation_pdfs(output_dir)

    manifest = {
        "dataset_name": "synthetic_deterministic_financial_evaluation",
        "description": (
            "Deterministic multi-page financial documents with conflicting values on same page, "
            "explicit table units/period headers, and known figures for grounded evaluation."
        ),
        "documents": [
            {
                "filename": AUDITED_REPORT_FILENAME,
                "path": str(files["audited"]),
                "sha256": compute_file_sha256(files["audited"]),
                "pages": 2,
                "role": "audited_source_of_truth",
                "page_1_content": "Audited Consolidated Statements of Operations (FY24 Revenue: $1,250.0M)",
                "page_2_content": "Audited Segment Breakdown (Cloud Platforms: $750.0M)",
            },
            {
                "filename": DRAFT_PROJECTIONS_FILENAME,
                "path": str(files["draft"]),
                "sha256": compute_file_sha256(files["draft"]),
                "pages": 2,
                "role": "conflicting_draft_to_exclude",
                "page_1_content": "Confidential Draft Operations (FY24 Revenue: $1,100.0M - CONFLICT ON PAGE 1)",
                "page_2_content": "Preliminary Segment Targets (Cloud Platforms: $660.0M)",
            },
        ],
    }

    manifest_path = output_dir / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Generated manifest: {manifest_path}")
    for item in manifest["documents"]:
        print(f" - {item['filename']} ({item['pages']} pages, sha256={item['sha256'][:16]}...)")


if __name__ == "__main__":
    main()

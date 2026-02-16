#!/usr/bin/env python3
"""
Tests that loading the same EDL twice produces identical timeline segments.

This ensures the parser is deterministic and doesn't introduce any randomness
or non-deterministic behavior during parsing.

Usage:
    cd backend
    python -m tests.contract.determinism_test
"""

import json
import sys
from pathlib import Path
from typing import Any

from app.schemas.edit_request import EditRequest


def test_determinism(filepath: Path) -> dict[str, Any]:
    """
    Test that loading the same EDL file twice produces identical results.

    Args:
        filepath: Path to the JSON file to test

    Returns:
        Dictionary with test results including:
        - file: filename
        - identical: whether both loads produced identical output
        - segment_count: number of timeline segments
    """
    with open(filepath) as f:
        data = json.load(f)

    # Load twice using real parser
    edl1 = EditRequest.model_validate(data)
    edl2 = EditRequest.model_validate(data)

    # Compare serialized output (exclude_none for consistent comparison)
    json1 = edl1.model_dump_json(exclude_none=True)
    json2 = edl2.model_dump_json(exclude_none=True)

    return {
        "file": filepath.name,
        "identical": json1 == json2,
        "segment_count": len(edl1.timeline),
    }


def main() -> int:
    """
    Main entry point - tests determinism for all valid test vectors.

    Returns:
        Exit code (0 for success, 1 if any test fails)
    """
    vectors_dir = Path(__file__).parent / "test_vectors"

    if not vectors_dir.exists():
        print(f"Error: Test vectors directory not found at {vectors_dir}", file=sys.stderr)
        return 1

    results = []
    failed = False

    for filepath in sorted(vectors_dir.glob("*.json")):
        # Skip invalid test vectors
        if "invalid" in filepath.name:
            continue

        try:
            result = test_determinism(filepath)
            results.append(result)
            if not result["identical"]:
                failed = True
        except Exception as e:
            results.append({"file": filepath.name, "error": str(e)})
            failed = True

    # Output results
    print(json.dumps(results, indent=2))

    # Summary
    passed = sum(1 for r in results if r.get("identical", False))
    total = len(results)
    print(f"\n# Summary: {passed}/{total} determinism tests passed", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Load EDL -> serialize -> reload -> compare structures.

This tests that the EDL can survive a full roundtrip through serialization
and deserialization without losing or corrupting data.

Usage:
    cd backend
    python -m tests.contract.roundtrip_test
"""

import json
import sys
from pathlib import Path
from typing import Any

from app.schemas.edit_request import EditRequest


def test_roundtrip(filepath: Path) -> dict[str, Any]:
    """
    Test that an EDL survives a load -> serialize -> reload cycle.

    Args:
        filepath: Path to the JSON file to test

    Returns:
        Dictionary with test results including:
        - file: filename
        - roundtrip_identical: whether roundtrip produced identical output
        - original_keys: number of top-level keys in original
        - final_keys: number of top-level keys after roundtrip
    """
    with open(filepath) as f:
        original = json.load(f)

    # Load with real parser
    edl = EditRequest.model_validate(original)

    # Serialize back to dict
    serialized = edl.model_dump(exclude_none=True)

    # Reload from serialized
    reloaded = EditRequest.model_validate(serialized)

    # Compare final serialization
    final = reloaded.model_dump(exclude_none=True)

    # Deep comparison of the two serialized forms
    # (serialized == final ensures the model is stable after roundtrip)
    roundtrip_identical = serialized == final

    return {
        "file": filepath.name,
        "roundtrip_identical": roundtrip_identical,
        "original_keys": len(original),
        "final_keys": len(final),
    }


def main() -> int:
    """
    Main entry point - tests roundtrip for all valid test vectors.

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
            result = test_roundtrip(filepath)
            results.append(result)
            if not result["roundtrip_identical"]:
                failed = True
        except Exception as e:
            results.append({"file": filepath.name, "error": str(e)})
            failed = True

    # Output results
    print(json.dumps(results, indent=2))

    # Summary
    passed = sum(1 for r in results if r.get("roundtrip_identical", False))
    total = len(results)
    print(f"\n# Summary: {passed}/{total} roundtrip tests passed", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

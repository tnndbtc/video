#!/usr/bin/env python3
"""
EDL v1 Contract Validator - validates schema and attempts dry-run render.

This script validates all test vectors against both JSON Schema and Pydantic
models to ensure the EDL v1 contract is properly enforced.

Usage:
    cd backend
    python -m tests.contract.validator
"""

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import ValidationError

# Import real schemas
from app.schemas.edit_request import EditRequest


def validate_file(filepath: Path, schema: dict) -> dict[str, Any]:
    """
    Validate a single EDL file against both JSON Schema and Pydantic.

    Args:
        filepath: Path to the JSON file to validate
        schema: JSON Schema dict to validate against

    Returns:
        Dictionary with validation results including:
        - file: filename
        - schema_valid: whether JSON Schema validation passed
        - renderer_loaded: whether Pydantic validation passed
        - errors: list of error messages
        - warnings: list of warning messages
    """
    result: dict[str, Any] = {
        "file": str(filepath.name),
        "schema_valid": False,
        "renderer_loaded": False,
        "errors": [],
        "warnings": [],
    }

    # Load JSON
    try:
        with open(filepath) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result["errors"].append(f"JSON parse error: {e}")
        return result

    # JSON Schema validation
    try:
        jsonschema.validate(data, schema)
        result["schema_valid"] = True
    except jsonschema.ValidationError as e:
        result["errors"].append(f"Schema: {e.message}")
        # Add path info for better debugging
        if e.absolute_path:
            path_str = ".".join(str(p) for p in e.absolute_path)
            result["errors"][-1] += f" (at {path_str})"

    # Pydantic validation (real loader)
    try:
        EditRequest.model_validate(data)
        result["renderer_loaded"] = True
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            result["errors"].append(f"Pydantic: {err['msg']} at {loc}")

    return result


def main() -> int:
    """
    Main entry point - validates all test vectors and outputs results.

    Returns:
        Exit code (0 for success)
    """
    schema_path = Path(__file__).resolve().parents[3] / "third_party" / "contracts" / "schemas" / "EditRequest.v1.json"
    vectors_dir = Path(__file__).parent / "test_vectors"

    # Check paths exist
    if not schema_path.exists():
        print(f"Error: Schema not found at {schema_path}", file=sys.stderr)
        return 1

    if not vectors_dir.exists():
        print(f"Error: Test vectors directory not found at {vectors_dir}", file=sys.stderr)
        return 1

    # Load schema
    with open(schema_path) as f:
        schema = json.load(f)

    # Validate all test vectors
    results = []
    for filepath in sorted(vectors_dir.glob("*.json")):
        results.append(validate_file(filepath, schema))

    # Output results
    print(json.dumps(results, indent=2))

    # Summary
    valid_count = sum(1 for r in results if r["schema_valid"] and r["renderer_loaded"])
    total_count = len(results)
    print(f"\n# Summary: {valid_count}/{total_count} test vectors fully valid", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

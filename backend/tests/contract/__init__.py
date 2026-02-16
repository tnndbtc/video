"""
EDL v1 Contract Validation Package.

This package provides tools for auditing EDL v1 schema stability using real
parsers/loaders (no mocks). It includes:

- edl_schema.json: JSON Schema (draft-07) describing the full EDL v1 structure
- test_vectors/: Sample EDL documents for validation testing
- validator.py: Validates test vectors against JSON Schema and Pydantic
- determinism_test.py: Tests that loading the same EDL twice produces identical results
- roundtrip_test.py: Tests load -> serialize -> reload -> compare

Usage:
    cd backend
    python -m tests.contract.validator
    python -m tests.contract.determinism_test
    python -m tests.contract.roundtrip_test
"""

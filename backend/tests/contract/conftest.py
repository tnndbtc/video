"""
Contract test conftest - isolates these tests from main app dependencies.

This file prevents the parent conftest.py from loading heavy app dependencies
(FastAPI, SQLAlchemy, etc.) that aren't needed for pure schema validation tests.
"""
# Empty conftest to override parent and prevent heavy imports

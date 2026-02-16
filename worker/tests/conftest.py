"""
Root conftest for worker tests.

Sets up Python path to allow 'from app.tasks...' imports.
"""
import sys
from pathlib import Path

# Add worker directory to path for imports
WORKER_DIR = Path(__file__).parent.parent
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

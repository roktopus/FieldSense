import os
import sys
from pathlib import Path

# Eval tests assert exact tool results. The running app defaults to the model.
os.environ.setdefault("ANSWER_MODE", "router")

# Allow `import harness...` from tests/
sys.path.insert(0, str(Path(__file__).parent))

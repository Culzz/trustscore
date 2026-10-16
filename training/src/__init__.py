"""TrustScore training pipeline.

Run from the repository root:

    python -m training.src.train

Everything in this package is offline-only. It produces the model artifact and
the JSON reports that the API serves at runtime.

The runtime decision policy, the reason vocabulary and the counterfactual search
live inside the API package (``api/app/services``) so that training and serving
share one implementation. We put ``api/`` on ``sys.path`` here so those modules
import as the ``app`` package, exactly as they do on Vercel.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_API_DIR = _REPO_ROOT / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

"""Shared pytest fixtures for the API tests.

Storage is forced off so tests never touch a real database, and the API package
is imported from this repository (mirroring how Vercel imports it).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_API_DIR = Path(__file__).resolve().parents[1]
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

# Disable storage + docs side effects before the app is imported.
os.environ.setdefault("STORAGE_BACKEND", "none")
os.environ.setdefault("LOG_PREDICTIONS", "false")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def strong_applicant() -> dict:
    return {
        "person_age": 40,
        "person_income": 85000,
        "person_home_ownership": "MORTGAGE",
        "person_emp_length": 12,
        "loan_intent": "PERSONAL",
        "loan_grade": "A",
        "loan_amnt": 7000,
        "loan_int_rate": 7.2,
        "cb_person_default_on_file": "N",
        "cb_person_cred_hist_length": 16,
    }


@pytest.fixture
def risky_applicant() -> dict:
    return {
        "person_age": 23,
        "person_income": 22000,
        "person_home_ownership": "RENT",
        "person_emp_length": 0,
        "loan_intent": "VENTURE",
        "loan_grade": "E",
        "loan_amnt": 18000,
        "loan_int_rate": 18.5,
        "cb_person_default_on_file": "Y",
        "cb_person_cred_hist_length": 3,
    }

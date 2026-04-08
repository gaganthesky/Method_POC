from __future__ import annotations

from source.reference_data import load_reference_data


REFERENCE_DATA = load_reference_data()

COMMON_REFERENCE = REFERENCE_DATA["common"]
APP_REFERENCE = COMMON_REFERENCE["app"]
STEP_TITLES = COMMON_REFERENCE["steps"]

METHOD_API_REFERENCE = REFERENCE_DATA["method_api"]
METHOD_REFERENCE = METHOD_API_REFERENCE["method"]
REFERENCE_RESPONSES = METHOD_API_REFERENCE["reference_responses"]

TEST_DATA_REFERENCE = REFERENCE_DATA["test_data"]
DEFAULT_BORROWER = TEST_DATA_REFERENCE["demo_borrower"]
DEFAULTS_REFERENCE = TEST_DATA_REFERENCE["defaults"]

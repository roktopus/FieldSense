"""Final-question harness (DATASET_PROFILE=test, test dataset imported)."""

from __future__ import annotations

import os

import pytest

from harness.runner import run_scenario_file, scenario_paths


@pytest.mark.skipif(
    os.environ.get("DATASET_PROFILE", "sample") != "test",
    reason="Final harness requires DATASET_PROFILE=test and test-data import",
)
@pytest.mark.parametrize("path", scenario_paths("final"), ids=lambda p: p.stem)
def test_final_scenario(path):
    run_scenario_file(path)

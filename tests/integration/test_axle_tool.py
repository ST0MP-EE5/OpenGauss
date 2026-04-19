"""Optional live integration tests for the AXLE proof-service adapter."""

from __future__ import annotations

import asyncio
import os

import pytest

from gauss_cli.lean_service import AxleProofService

pytestmark = pytest.mark.integration


def test_axle_check_live():
    pytest.importorskip("axle")

    if not os.getenv("RUN_AXLE_INTEGRATION"):
        pytest.skip("Set RUN_AXLE_INTEGRATION=1 to run live AXLE integration checks.")

    service = AxleProofService()
    environments = asyncio.run(service.list_environments(timeout_seconds=30))
    assert environments

    target_environment = os.getenv("AXLE_INTEGRATION_ENVIRONMENT") or environments[0]["name"]
    result = asyncio.run(
        service.check(
            content="import Mathlib\n\ndef x := 1\n",
            environment=target_environment,
            timeout_seconds=30,
        )
    )

    assert isinstance(result, dict)
    assert "okay" in result

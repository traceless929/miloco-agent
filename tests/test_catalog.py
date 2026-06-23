"""Device catalog injection tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from miloco_agent.prompt import catalog


@pytest.mark.asyncio
async def test_run_cli_catalog_uses_resolved_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        catalog,
        "resolve_miloco_cli",
        lambda: {"path": "/venv/bin/miloco-cli"},
    )
    monkeypatch.setattr(catalog, "miloco_home", lambda: Path("/tmp/mh"))

    proc = AsyncMock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(b"device-a", b""))

    with patch.object(catalog.asyncio, "create_subprocess_exec", return_value=proc) as mock_exec:
        text = await catalog._run_cli_catalog()

    assert text == "device-a"
    args, kwargs = mock_exec.call_args
    assert args[0] == "/venv/bin/miloco-cli"
    assert kwargs["env"]["MILOCO_HOME"] == "/tmp/mh"

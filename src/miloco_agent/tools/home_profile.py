"""Home profile tool helpers (Miloco /api/home-profile)."""

from __future__ import annotations

import json
from typing import Any, Literal

from miloco_agent.tools.miloco_client import MilocoApiClient, MilocoApiError

ProfileTarget = Literal["profile", "candidates"]


async def tool_home_profile_read(client: MilocoApiClient) -> str:
    md = await client.home_profile_rendered()
    return json.dumps(
        {"ok": True, "markdown": md, "empty": not md.strip()},
        ensure_ascii=False,
    )


async def tool_home_profile_list(
    client: MilocoApiClient,
    *,
    target: str = "both",
) -> str:
    data = await client.home_profile_list(target=target)
    return json.dumps({"ok": True, "data": data}, ensure_ascii=False)


async def tool_home_profile_write(
    client: MilocoApiClient,
    *,
    ops_json: str,
    target: ProfileTarget = "profile",
    user_edit: bool = False,
) -> str:
    ops = json.loads(ops_json)
    if not isinstance(ops, list):
        raise ValueError("ops_json must be a JSON array")
    if target == "candidates":
        result = await client.home_profile_candidate_write(ops)
    else:
        result = await client.home_profile_write(ops, user_edit=user_edit)
    return json.dumps({"ok": True, "results": result}, ensure_ascii=False)


async def tool_home_profile_commit(client: MilocoApiClient) -> str:
    result = await client.home_profile_commit()
    return json.dumps({"ok": True, "result": result}, ensure_ascii=False)


async def run_home_profile_tool(
    client: MilocoApiClient,
    name: str,
    arguments: dict[str, Any],
) -> str:
    try:
        if name == "home_profile_read":
            return await tool_home_profile_read(client)
        if name == "home_profile_list":
            return await tool_home_profile_list(
                client,
                target=str(arguments.get("target") or "both"),
            )
        if name == "home_profile_write":
            ops_json = str(arguments.get("ops_json") or "")
            if not ops_json:
                raise ValueError("ops_json is required")
            return await tool_home_profile_write(
                client,
                ops_json=ops_json,
                target=str(arguments.get("target") or "profile"),  # type: ignore[arg-type]
                user_edit=bool(arguments.get("user_edit")),
            )
        if name == "home_profile_commit":
            return await tool_home_profile_commit(client)
        raise ValueError(f"unknown home profile tool: {name}")
    except MilocoApiError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

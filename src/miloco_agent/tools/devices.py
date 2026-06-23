"""Device list / control tool implementations."""

from __future__ import annotations

import json
from typing import Any

from miloco_agent.tools.miloco_client import MilocoApiClient, MilocoApiError


def compact_device_row(device: dict[str, Any]) -> dict[str, Any]:
    return {
        "did": device.get("did"),
        "name": device.get("name"),
        "online": device.get("online"),
        "room": device.get("room_name"),
        "model": device.get("model"),
    }


async def tool_device_list(
    client: MilocoApiClient,
    *,
    room: str | None = None,
    online_only: bool = False,
) -> str:
    devices = await client.device_list()
    rows = [compact_device_row(d) for d in devices if isinstance(d, dict)]
    if room:
        needle = room.strip().lower()
        rows = [r for r in rows if needle in str(r.get("room") or "").lower()]
    if online_only:
        rows = [r for r in rows if r.get("online")]
    return json.dumps({"count": len(rows), "devices": rows}, ensure_ascii=False)


async def tool_device_spec(client: MilocoApiClient, *, did: str) -> str:
    spec = await client.device_spec(did)
    return json.dumps(spec, ensure_ascii=False)


async def tool_device_control(
    client: MilocoApiClient,
    *,
    did: str,
    control_type: str,
    iid: str | None = None,
    value: Any = None,
    properties_json: str | None = None,
    params_json: str | None = None,
) -> str:
    properties = None
    params = None
    if properties_json:
        parsed = json.loads(properties_json)
        if not isinstance(parsed, list):
            raise ValueError("properties_json must be a JSON array")
        properties = parsed
    if params_json:
        parsed = json.loads(params_json)
        if not isinstance(parsed, list):
            raise ValueError("params_json must be a JSON array")
        params = parsed
    result = await client.device_control(
        did,
        control_type=control_type,
        iid=iid,
        value=value,
        properties=properties,
        params=params,
    )
    return json.dumps({"ok": True, "result": result}, ensure_ascii=False)


def _find_play_text_action_iid(spec: dict[str, Any]) -> str | None:
    services = spec.get("services")
    if not isinstance(services, list):
        return None
    for svc in services:
        if not isinstance(svc, dict):
            continue
        for act in svc.get("actions") or []:
            if not isinstance(act, dict):
                continue
            iid = act.get("iid")
            if not iid:
                continue
            label = " ".join(
                str(act.get(k) or "")
                for k in ("name", "description", "type", "spec_name")
            ).lower()
            if "play-text" in label or "play_text" in label:
                return str(iid)
    return None


async def tool_speaker_tts(
    client: MilocoApiClient,
    *,
    did: str,
    text: str,
    action_iid: str | None = None,
) -> str:
    content = text.strip()
    if not content:
        raise ValueError("text is required")
    iid = action_iid
    if not iid:
        spec = await client.device_spec(did)
        iid = _find_play_text_action_iid(spec)
    if not iid:
        raise ValueError("play-text action not found; pass action_iid from device_spec")
    result = await client.device_control(
        did,
        control_type="call_action",
        iid=iid,
        params=[content],
    )
    return json.dumps({"ok": True, "did": did, "iid": iid, "result": result}, ensure_ascii=False)


async def run_device_tool(
    client: MilocoApiClient,
    name: str,
    arguments: dict[str, Any],
) -> str:
    try:
        if name == "device_list":
            return await tool_device_list(
                client,
                room=arguments.get("room"),
                online_only=bool(arguments.get("online_only")),
            )
        if name == "device_spec":
            did = str(arguments.get("did") or "")
            if not did:
                raise ValueError("did is required")
            return await tool_device_spec(client, did=did)
        if name == "device_control":
            did = str(arguments.get("did") or "")
            if not did:
                raise ValueError("did is required")
            control_type = str(arguments.get("control_type") or "")
            if not control_type:
                raise ValueError("control_type is required")
            return await tool_device_control(
                client,
                did=did,
                control_type=control_type,
                iid=arguments.get("iid"),
                value=arguments.get("value"),
                properties_json=arguments.get("properties_json"),
                params_json=arguments.get("params_json"),
            )
        if name == "device_speaker_tts":
            did = str(arguments.get("did") or "")
            if not did:
                raise ValueError("did is required")
            return await tool_speaker_tts(
                client,
                did=did,
                text=str(arguments.get("text") or ""),
                action_iid=arguments.get("action_iid"),
            )
        raise ValueError(f"unknown device tool: {name}")
    except MilocoApiError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 — return to LLM as tool output
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

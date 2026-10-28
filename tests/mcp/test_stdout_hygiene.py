import asyncio
import json
import shutil

import pytest


@pytest.mark.live
@pytest.mark.asyncio
async def test_stdout_hygiene_and_jsonrpc():
    uv_bin = shutil.which("uv")
    assert uv_bin is not None, "uv binary not found"

    # Spawn job-scout via uv run
    proc = await asyncio.create_subprocess_exec(
        uv_bin,
        "run",
        "job-scout",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=10 * 1024 * 1024,
    )

    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None

    async def read_stdout_line() -> str:
        line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=15.0)
        return line_bytes.decode("utf-8")

    # 1. Send initialize
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "hygiene-client", "version": "1.0"},
        },
    }
    proc.stdin.write((json.dumps(init_req) + "\n").encode("utf-8"))
    await proc.stdin.drain()

    # Read response
    init_line = await read_stdout_line()
    assert init_line.strip(), "Empty line received on stdout"
    init_json = json.loads(init_line)
    assert init_json.get("jsonrpc") == "2.0"
    assert init_json.get("id") == 1

    # 2. Send initialized notification
    notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    proc.stdin.write((json.dumps(notif) + "\n").encode("utf-8"))
    await proc.stdin.drain()

    # 3. Send tools/call search_jobs
    tool_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "search_jobs",
            "arguments": {"sources": ["justjoin"], "limit": 2},
        },
    }
    proc.stdin.write((json.dumps(tool_req) + "\n").encode("utf-8"))
    await proc.stdin.drain()

    # Read response (might get notifications or the result)
    tool_line = await read_stdout_line()
    assert tool_line.strip(), "Empty line received on stdout"
    tool_json = json.loads(tool_line)
    assert tool_json.get("jsonrpc") == "2.0"
    assert tool_json.get("id") == 2

    # Close stdin and terminate cleanly
    proc.stdin.close()
    await proc.stdin.wait_closed()

    try:
        proc.terminate()
    except ProcessLookupError:
        pass

    stdout_rest, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=10.0)

    # Any remaining stdout lines must also be valid JSON
    if stdout_rest:
        for line in stdout_rest.decode("utf-8").splitlines():
            clean = line.strip()
            if clean:
                parsed = json.loads(clean)
                assert parsed.get("jsonrpc") == "2.0"

    stderr_text = stderr_bytes.decode("utf-8")
    print(f"\nCaptured stderr length: {len(stderr_text)} characters")
    print(f"Sample stderr:\n{stderr_text[:500]}")

    # Assertions per Gate F:
    # - every line on stdout is valid JSON-RPC 2.0 (verified above via json.loads)
    # - stderr has non-zero length (confirming logs went there)
    assert len(stderr_text) > 0, "Expected non-zero stderr logging output"
    assert "job_scout" in stderr_text or "mcp" in stderr_text or "INFO" in stderr_text, (
        "Expected server logging in stderr"
    )

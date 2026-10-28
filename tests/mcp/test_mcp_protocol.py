import json
import shutil
from pathlib import Path

import jsonschema
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SCHEMA_PATH = Path("schema/search_result.schema.json")
SEARCH_RESULT_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.mark.live
@pytest.mark.asyncio
async def test_mcp_protocol_full_suite():
    uv_path = shutil.which("uv")
    assert uv_path is not None, "uv binary not found in PATH"

    project_dir = str(Path.cwd().resolve())

    server_params = StdioServerParameters(
        command=uv_path,
        args=["--directory", project_dir, "run", "job-scout"],
        env=None,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize succeeds
            init_res = await session.initialize()
            assert init_res is not None

            # 2. list_tools returns 4 tools with schemas
            tools_res = await session.list_tools()
            tool_names = [t.name for t in tools_res.tools]
            print("\nTools reported by server:", tool_names)
            assert len(tools_res.tools) == 4
            assert set(tool_names) == {
                "search_jobs",
                "get_job_details",
                "check_validity",
                "list_sources",
            }

            # 3. search_jobs(keywords="python", limit=10): result validates against schema
            search_call = await session.call_tool(
                "search_jobs",
                arguments={"keywords": "python", "limit": 10},
            )
            assert search_call is not None
            assert len(search_call.content) > 0

            # Content is JSON text
            raw_json = search_call.content[0].text
            parsed_result = json.loads(raw_json)
            print(f"search_jobs returned {parsed_result.get('returned')} jobs (total {parsed_result.get('total')})")

            # Validate against search_result.schema.json
            jsonschema.validate(instance=parsed_result, schema=SEARCH_RESULT_SCHEMA)

            # 4. get_job_details on a returned link returns full description
            jobs = parsed_result.get("jobs", [])
            test_url = jobs[0]["link"] if jobs else "https://justjoin.it/job-offers/warszawa"

            details_call = await session.call_tool(
                "get_job_details",
                arguments={"url": test_url},
            )
            assert details_call is not None
            raw_details = details_call.content[0].text
            parsed_details = json.loads(raw_details)
            assert parsed_details.get("title")
            assert "description" in parsed_details
            assert parsed_details.get("link")

            # 5. check_validity on 1 valid and 1 expired URL returns correct results
            validity_call = await session.call_tool(
                "check_validity",
                arguments={
                    "urls": [
                        test_url,
                        "https://justjoin.it/job-offer/non-existent-expired-slug-12345",
                    ]
                },
            )
            assert validity_call is not None
            if len(validity_call.content) > 1:
                val_results = [json.loads(c.text) for c in validity_call.content]
            else:
                loaded = json.loads(validity_call.content[0].text)
                val_results = loaded if isinstance(loaded, list) else [loaded]
            assert len(val_results) == 2
            assert val_results[0]["is_valid"] is True
            assert val_results[1]["is_valid"] is False

            # 6. search_jobs(sources=["nonexistent"]) returns a tool error and server stays alive
            invalid_call = await session.call_tool(
                "search_jobs",
                arguments={"sources": ["nonexistent"]},
            )
            # FastMCP reports errors with isError=True
            assert invalid_call.isError is True
            assert "Unknown source ID: 'nonexistent'" in invalid_call.content[0].text

            # Follow-up call succeeds (server is alive)
            sources_call = await session.call_tool("list_sources", arguments={})
            assert sources_call is not None
            if len(sources_call.content) > 1:
                sources_list = [json.loads(c.text) for c in sources_call.content]
            else:
                loaded = json.loads(sources_call.content[0].text)
                sources_list = loaded if isinstance(loaded, list) else [loaded]
            assert len(sources_list) >= 11
            print(f"Server alive! list_sources returned {len(sources_list)} sources")

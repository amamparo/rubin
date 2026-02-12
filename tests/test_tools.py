import json

import pytest


@pytest.mark.anyio
async def test_list_style_profiles(mcp_server):
    content, _ = await mcp_server.call_tool("list_style_profiles", {})
    result = json.loads(content[0].text)
    assert "ambient" in result
    assert "synthpop" in result


@pytest.mark.anyio
async def test_evaluate_mix(fake_client, mcp_server):
    content, _ = await mcp_server.call_tool(
        "evaluate_mix", {"style": "ambient", "duration": 1.0}
    )
    result = json.loads(content[0].text)
    assert "cohesion_score" in result
    assert "issues" in result
    assert "band_scores" in result
    assert result["style"] == "ambient"
    assert fake_client.captures == [(1.0, 44100)]


@pytest.mark.anyio
async def test_get_spectral_data(fake_client, mcp_server):
    content, _ = await mcp_server.call_tool(
        "get_spectral_data", {"duration": 2.0, "sample_rate": 22050}
    )
    result = json.loads(content[0].text)
    assert "spectral" in result
    assert "timbre" in result
    assert "loudness" in result
    assert "frequency_bands" in result
    assert "stereo" in result
    assert fake_client.captures == [(2.0, 22050)]


@pytest.mark.anyio
async def test_capture_and_compare_snapshots(fake_client, mcp_server):
    # Capture two snapshots
    await mcp_server.call_tool("capture_snapshot", {"name": "snap_a", "duration": 1.0})
    await mcp_server.call_tool("capture_snapshot", {"name": "snap_b", "duration": 1.0})

    # List them
    content, _ = await mcp_server.call_tool("list_snapshots", {})
    names = json.loads(content[0].text)
    assert "snap_a" in names
    assert "snap_b" in names

    # Compare
    content, _ = await mcp_server.call_tool(
        "compare_snapshots", {"name_a": "snap_a", "name_b": "snap_b"}
    )
    result = json.loads(content[0].text)
    assert "spectral" in result


@pytest.mark.anyio
async def test_compare_snapshots_missing(mcp_server):
    content, _ = await mcp_server.call_tool(
        "compare_snapshots", {"name_a": "nope", "name_b": "also_nope"}
    )
    result = json.loads(content[0].text)
    assert "error" in result


@pytest.mark.anyio
async def test_suggest_adjustments(fake_client, mcp_server):
    content, _ = await mcp_server.call_tool(
        "suggest_adjustments", {"style": "synthpop", "duration": 1.0}
    )
    result = json.loads(content[0].text)
    assert "style" in result
    assert "cohesion_score" in result
    assert "suggestions" in result
    assert isinstance(result["suggestions"], list)

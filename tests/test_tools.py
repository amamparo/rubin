import json
from unittest.mock import patch

import pytest


@pytest.mark.anyio
async def test_list_style_profiles(mcp_server):
    content, _ = await mcp_server.call_tool("list_style_profiles", {})
    result = json.loads(content[0].text)
    names = [p["name"] for p in result]
    assert "ambient" in names
    assert "synthpop" in names
    # Verify structure
    entry = result[0]
    assert "name" in entry
    assert "description" in entry
    assert "source" in entry
    assert entry["source"] == "built-in"


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


@pytest.mark.anyio
async def test_create_style(mcp_server, tmp_path):
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        content, _ = await mcp_server.call_tool(
            "create_style",
            {
                "name": "dreampop",
                "description": "Ethereal dreampop",
                "frequency_balance": {
                    "bass": {"low": 0.01, "high": 0.08},
                    "mid": {"low": 0.003, "high": 0.05},
                },
                "brightness": {"low": 1500, "high": 4000},
            },
        )
        result = json.loads(content[0].text)
        assert result["status"] == "created"
        assert result["profile"] == "dreampop"
        assert (tmp_path / "dreampop.json").exists()


@pytest.mark.anyio
async def test_update_style(mcp_server, tmp_path):
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        # Create first
        await mcp_server.call_tool(
            "create_style",
            {"name": "test-update", "description": "Original"},
        )
        # Update
        content, _ = await mcp_server.call_tool(
            "update_style",
            {"name": "test-update", "description": "Updated description"},
        )
        result = json.loads(content[0].text)
        assert result["status"] == "updated"
        # Verify the update persisted
        data = json.loads((tmp_path / "test-update.json").read_text())
        assert data["description"] == "Updated description"


@pytest.mark.anyio
async def test_update_builtin_creates_override(mcp_server, tmp_path):
    """Updating a built-in style creates a user override."""
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        content, _ = await mcp_server.call_tool(
            "update_style",
            {"name": "ambient", "description": "My custom ambient"},
        )
        result = json.loads(content[0].text)
        assert result["status"] == "updated"
        assert (tmp_path / "ambient.json").exists()


@pytest.mark.anyio
async def test_delete_style(mcp_server, tmp_path):
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        # Create then delete
        await mcp_server.call_tool(
            "create_style",
            {"name": "temp-style", "description": "Temporary"},
        )
        content, _ = await mcp_server.call_tool("delete_style", {"name": "temp-style"})
        result = json.loads(content[0].text)
        assert result["status"] == "deleted"
        assert not (tmp_path / "temp-style.json").exists()


@pytest.mark.anyio
async def test_delete_builtin_refused(mcp_server, tmp_path):
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        content, _ = await mcp_server.call_tool("delete_style", {"name": "ambient"})
        result = json.loads(content[0].text)
        assert "error" in result


@pytest.mark.anyio
async def test_audition_track(fake_client, mcp_server):
    content, _ = await mcp_server.call_tool(
        "audition_track", {"style": "techno", "duration": 1.0}
    )
    result = json.loads(content[0].text)
    assert "role" in result
    assert "fit_score" in result
    assert "dominant_bands" in result
    assert "frequency_profile" in result
    assert "issues" in result
    assert result["style"] == "techno"
    assert 0 <= result["fit_score"] <= 100


@pytest.mark.anyio
async def test_audition_track_with_role(fake_client, mcp_server):
    content, _ = await mcp_server.call_tool(
        "audition_track", {"style": "ambient", "role": "pad", "duration": 1.0}
    )
    result = json.loads(content[0].text)
    assert result["role"] == "pad"


@pytest.mark.anyio
async def test_audition_track_invalid_role(mcp_server):
    content, _ = await mcp_server.call_tool(
        "audition_track", {"style": "ambient", "role": "invalid"}
    )
    result = json.loads(content[0].text)
    assert "error" in result

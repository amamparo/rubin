Rubin — Audio Evaluation MCP Server

An MCP server that listens to audio and provides structured feedback on mix quality, timbral compatibility, and stylistic coherence.

## Constraints

- Mirror the project structure of [amamparo/ableton-mcp](https://github.com/amamparo/ableton-mcp) (src layout, pyproject.toml shape, justfile, CLAUDE.md, Poetry, injector, pytest+anyio)
- Runs as a Docker service. The release GitHub Actions workflow should bump a version tag and push version-tagged builds to Docker Hub (`amamparo/rubin:$TAG` + `amamparo/rubin:latest`)
- CI workflow for lint + test on push/PR, same as ableton-mcp
- Python 3.12+, same tooling (Black, Ruff, Just)

## Audio Input

Rubin should be agnostic about how audio gets to it. Define an `AudioClient` ABC and implement multiple backends — e.g. system audio device capture (BlackHole/VB-Audio), TCP socket, stdin pipe. The user picks one via CLI arg or env var.

The README should include an "Audio Setup" section that makes connecting any sound source as simple as possible — DAWs, media players, browsers, games, whatever. Present the options as a short pick-one list with copy-pasteable commands for each. Include platform-specific guidance (macOS, Windows, Linux) where the setup differs. A user should be able to get audio flowing into Rubin in under 5 minutes regardless of where the audio is coming from.

## Analysis

Use `librosa` for feature extraction: spectral features, timbral features (MFCCs, chroma), frequency band energy, RMS loudness, dynamic range, stereo image. Return structured data, not prose.

## Evaluation

Define style profiles as JSON configs (e.g. `styles/ambient.json`, `styles/synthpop.json`). Each profile specifies target ranges for frequency balance, dynamics, brightness, etc. Score captured audio against a profile and return a cohesion score plus flagged issues (masking, mud, harshness, thin bass) and actionable suggestions.

## MCP Tools

Expose tools for: evaluating a mix against a style profile, capturing and comparing snapshots, getting raw spectral data, and suggesting mix adjustments. Keep the tool surface small and composable — Claude can chain them.

Progress
5 of 5

Working folder

TODO.md

Scratchpad

Context
Connectors
A

ableton-mcp
Web search
Skills
music-composer

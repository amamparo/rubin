# Rubin

An MCP server that listens to audio and provides structured feedback on mix quality, timbral compatibility, and stylistic coherence.

## Quick Start

```bash
# Install
poetry install

# Run the MCP server (default: system audio capture)
poetry run rubin

# Or via Docker
docker run --rm -it aaronmamparo/rubin:latest
```

## Audio Setup

Rubin needs audio routed to it. Pick the option that fits your setup:

### Option A: System Audio Capture (Recommended)

Route your system or DAW audio to a virtual loopback device, then point Rubin at it.

**macOS — [BlackHole](https://existential.audio/blackhole/)**

```bash
brew install blackhole-2ch
```

1. Open **Audio MIDI Setup** → create a **Multi-Output Device** combining your speakers + BlackHole 2ch
2. Set the Multi-Output as your system output (or your DAW's output)
3. Run Rubin targeting BlackHole:

```bash
RUBIN_AUDIO_DEVICE="BlackHole 2ch" poetry run rubin
```

**Windows — [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)**

1. Install VB-CABLE
2. Set your DAW or system output to **CABLE Input**
3. Run Rubin targeting the virtual cable:

```bash
set RUBIN_AUDIO_DEVICE=CABLE Output
poetry run rubin
```

**Linux — PulseAudio/PipeWire**

```bash
# Create a virtual sink and loopback
pactl load-module module-null-sink sink_name=rubin sink_properties=device.description=Rubin
pactl load-module module-loopback source=rubin.monitor

# Route your DAW output to the "Rubin" sink, then:
RUBIN_AUDIO_DEVICE="Rubin" poetry run rubin
```

### Option B: TCP Socket

Send raw PCM audio over TCP. Useful for remote sources or custom pipelines.

```bash
# Start Rubin in TCP mode
poetry run rubin --audio tcp --tcp-port 9878

# From another terminal, pipe audio via ffmpeg:
ffmpeg -i your_track.wav -f f32le -ac 2 -ar 44100 - | \
  nc localhost 9878
```

### Option C: Stdin Pipe

Pipe audio directly via stdin. Great for one-shot analysis.

```bash
ffmpeg -i your_track.wav -f f32le -ac 2 -ar 44100 - | \
  poetry run rubin --audio stdin
```

## Claude Desktop Setup

Add Rubin to your `claude_desktop_config.json`:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

### Option A: Run from GitHub (No Clone Required)

The simplest setup — runs Rubin directly from the repo using `uvx`:

```json
{
  "mcpServers": {
    "rubin": {
      "command": "/absolute/path/to/uvx",
      "args": ["--from", "git+https://github.com/aaronmamparo/rubin", "rubin"],
      "env": {
        "RUBIN_AUDIO_DEVICE": "BlackHole 2ch"
      }
    }
  }
}
```

Find your uvx path with `which uvx`. The path must be absolute — Claude Desktop does not inherit your shell's PATH.

### Option B: Local Clone (Poetry)

If you've cloned the repo locally:

```json
{
  "mcpServers": {
    "rubin": {
      "command": "/absolute/path/to/poetry",
      "args": ["--directory", "/absolute/path/to/rubin", "run", "rubin"],
      "env": {
        "RUBIN_AUDIO_DEVICE": "BlackHole 2ch"
      }
    }
  }
}
```

Find your Poetry path with `which poetry`. Both paths must be absolute.

### Option C: Docker (TCP/stdin only)

> **Note:** Docker containers cannot access host audio devices (BlackHole / VB-Audio). Use Option A or B for system audio capture.

```json
{
  "mcpServers": {
    "rubin": {
      "command": "/usr/local/bin/docker",
      "args": ["run", "--rm", "-i", "-e", "RUBIN_AUDIO_MODE=tcp", "aaronmamparo/rubin:latest"]
    }
  }
}
```

Restart Claude Desktop after saving. You should see the Rubin tools (hammer icon) in the input bar. Claude can then evaluate your mix, capture snapshots, and suggest adjustments — just ask it to listen.

## MCP Tools

| Tool | Description |
|---|---|
| `evaluate_mix` | Capture audio and score it against a style profile. Returns cohesion score, flagged issues, and per-band scores. |
| `capture_snapshot` | Capture audio and save the analysis as a named snapshot. |
| `compare_snapshots` | Compare two snapshots and see per-metric deltas. |
| `get_spectral_data` | Capture audio and return the full spectral/timbral/loudness analysis. |
| `suggest_adjustments` | Evaluate against a style and return only actionable suggestions, sorted by severity. |
| `list_style_profiles` | List available style profiles. |
| `list_snapshots` | List saved snapshots. |

## Style Profiles

Built-in profiles in `styles/`:

- **ambient** — lush, spacious, wide stereo, subdued dynamics
- **synthpop** — punchy, bright, tight low-end, forward mids
- **lo-fi** — warm, rolled-off highs, narrow dynamics
- **techno** — heavy sub-bass, aggressive upper-mids, tight compression
- **orchestral** — wide dynamic range, natural balance, spacious stereo

Create your own by adding a JSON file to `styles/`. See existing profiles for the schema.

## Development

```bash
just install    # install dependencies
just check      # lint + test
just fmt        # auto-format
just test       # run tests only
```

## Docker

```bash
docker build -t rubin .
docker run --rm -it rubin --audio tcp --tcp-port 9878
```

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
| `audition_track` | Analyze a soloed track — classifies its role (bass, lead, pad, percussion, texture) and scores how well it fits the style. |
| `list_style_profiles` | List available style profiles (built-in and user-created). |
| `list_snapshots` | List saved snapshots. |
| `create_style` | Create a new custom style profile via natural language. Saved to `~/.rubin/styles/`. |
| `update_style` | Update an existing style's target ranges. Creates a user override for built-in styles. |
| `delete_style` | Delete a user-created style. Built-in styles cannot be deleted. |

## Style Profiles

### Built-in Profiles

16 built-in profiles covering a wide range of genres:

| Profile | Character |
|---|---|
| ambient | Lush, spacious, wide stereo, subdued dynamics |
| downtempo | Warm sub-bass, mellow mids, soft highs, relaxed dynamics |
| drum-and-bass | Deep sub-bass reese, snappy breakbeats, aggressive upper-mids |
| edm | Massive sub-bass drops, bright leads, heavy sidechain compression |
| folk | Organic warmth, fingerpicked clarity, wide dynamics, minimal processing |
| hip-hop | Deep 808 sub-bass, punchy kick, vocal-forward mids |
| house | Warm four-on-the-floor kick, round bass, smooth vocals |
| industrial | Distorted textures, heavy compression, harsh upper-mids |
| jazz | Natural instrument clarity, wide dynamic range, gentle sparkle |
| lo-fi | Warm, rolled-off highs, narrow dynamics |
| orchestral | Wide dynamic range, natural balance, spacious stereo |
| rnb | Smooth, warm lows, silky vocal mids, restrained highs |
| rock | Full guitars, driving drums, present vocals |
| synthpop | Punchy, bright, tight low-end, forward mids |
| techno | Heavy sub-bass, aggressive upper-mids, tight compression |
| vaporwave | Pitched-down warmth, heavy reverb, rolled-off highs |

### Custom Styles

Create your own styles through natural conversation with Claude — just describe the sound you're going for:

> "Create a dreampop style with warm bass, shimmery highs, and wide stereo"

Custom styles are saved to `~/.rubin/styles/` and persist across sessions. You can also update or delete them the same way.

To manually create a style, add a JSON file to `~/.rubin/styles/`:

```json
{
  "name": "my-style",
  "description": "Description of the target sound",
  "frequency_balance": {
    "sub_bass": { "low": 0.001, "high": 0.05 },
    "bass": { "low": 0.005, "high": 0.08 },
    "low_mid": { "low": 0.003, "high": 0.06 },
    "mid": { "low": 0.002, "high": 0.04 },
    "upper_mid": { "low": 0.001, "high": 0.025 },
    "presence": { "low": 0.0005, "high": 0.02 },
    "brilliance": { "low": 0.0005, "high": 0.015 }
  },
  "dynamic_range_db": { "low": 10, "high": 30 },
  "brightness": { "low": 1000, "high": 3000 },
  "stereo_width": { "low": 0.15, "high": 0.5 },
  "rms_mean": { "low": 0.01, "high": 0.12 }
}
```

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

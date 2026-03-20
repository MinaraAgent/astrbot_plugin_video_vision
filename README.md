# AstrBot Video Vision Plugin

An AstrBot plugin that automatically analyzes video attachments from Discord messages using LLM vision capabilities.

## Features

- **Automatic Video Detection**: Detects video file attachments in Discord messages
- **Frame Extraction**: Extracts key frames from videos using ffmpeg
- **Flexible Timing Options**:
  - Skip first N seconds (skip intros)
  - Skip last N seconds (skip outros)
  - Extract frames by interval (e.g., 1 frame per second or per 10 seconds)
  - Or extract evenly distributed frames (max_frames mode)
- **LLM Analysis**: Sends extracted frames to the configured LLM for content analysis
- **Multiple Format Support**: Supports MP4, MOV, AVI, WebM, MKV, FLV, WMV, M4V
- **Configurable**: Customize max frames, output format, timing options, and more
- **Graceful Error Handling**: Handles missing ffmpeg, short videos, and other edge cases

## Requirements

- **ffmpeg**: Must be installed on the system running AstrBot
- **AstrBot**: Version 4.16 or higher
- **LLM Provider**: A vision-capable LLM provider must be configured in AstrBot

### Installing ffmpeg

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html

## Installation

1. Clone or download this plugin to your AstrBot plugins directory:
   ```bash
   cd AstrBot/data/plugins
   git clone https://github.com/minara-agent/astrbot_plugin_video_vision.git
   ```

2. Restart AstrBot or reload plugins via the WebUI

3. Configure your LLM provider with vision capabilities (e.g., GPT-4 Vision, Claude 3)

## Configuration

The plugin can be configured via `_conf_schema.json` in AstrBot's WebUI:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | bool | true | Enable/disable the plugin |
| `max_frames` | int | 5 | Maximum frames to extract (used when frame_interval=0) |
| `frame_format` | string | jpg | Output format for frames (jpg, png, webp) |
| `skip_first_seconds` | float | 0 | Skip the first N seconds of the video (skip intros) |
| `skip_last_seconds` | float | 0 | Skip the last N seconds of the video (skip outros) |
| `frame_interval` | float | 0 | Extract 1 frame every N seconds (0 = use max_frames mode) |
| `video_extensions` | list | [mp4, mov, avi, webm, ...] | Video file extensions to process |
| `platform_ids` | list | [] | Platform IDs to process (empty = all) |
| `analysis_prompt` | text | (see below) | Prompt sent to LLM for analysis |

### Frame Extraction Modes

**Mode 1: Evenly Distributed (default)**
- Set `frame_interval = 0`
- Set `max_frames` to desired number (e.g., 5)
- Frames will be evenly distributed across the video (after skip offsets)

**Mode 2: Interval-based**
- Set `frame_interval > 0` (e.g., 1 for every second, 10 for every 10 seconds)
- `max_frames` is ignored in this mode
- Useful for long videos where you want consistent sampling

### Example Configurations

**Analyze video intros (first 10 seconds):**
```json
{
  "skip_first_seconds": 0,
  "skip_last_seconds": 0,
  "max_frames": 5,
  "frame_interval": 0
}
```

**Analyze video content, skipping intro/outro:**
```json
{
  "skip_first_seconds": 5,
  "skip_last_seconds": 5,
  "max_frames": 10,
  "frame_interval": 0
}
```

**Extract 1 frame per second for detailed analysis:**
```json
{
  "skip_first_seconds": 0,
  "skip_last_seconds": 0,
  "frame_interval": 1
}
```

**Extract 1 frame every 10 seconds for long videos:**
```json
{
  "skip_first_seconds": 10,
  "skip_last_seconds": 5,
  "frame_interval": 10
}
```

Default analysis prompt:
```
Please analyze the content of this video based on the extracted frames.
Describe what you see, including any actions, objects, people, or text visible in the frames.
```

## Commands

| Command | Description |
|---------|-------------|
| `/video_vision_status` | Check plugin status and configuration |
| `/video_vision_enable` | Enable the plugin |
| `/video_vision_disable` | Disable the plugin |

## How It Works

1. When a Discord message contains a video attachment, the plugin detects it
2. The video is downloaded to a temporary directory
3. ffmpeg extracts frames from the video:
   - Skips the first N seconds if `skip_first_seconds` is set
   - Skips the last N seconds if `skip_last_seconds` is set
   - Either extracts evenly distributed frames (`max_frames` mode) or one frame every N seconds (`frame_interval` mode)
4. Frames are sent to the configured LLM with an analysis prompt
5. The LLM's analysis is sent back to the original channel
6. Temporary files are automatically cleaned up

## Example Usage

1. Upload a video file to a Discord channel where AstrBot is present
2. The plugin will automatically:
   - Download the video
   - Extract frames
   - Send a "Analyzing video..." notification
   - Return the LLM's analysis of the video content

## Troubleshooting

### Plugin not working

1. Check if ffmpeg is installed:
   ```bash
   ffmpeg -version
   ```

2. Check plugin status:
   ```
   /video_vision_status
   ```

3. Check AstrBot logs for error messages

### "Failed to extract frames" error

- The video may be too short (less than 1 second)
- The video format may not be supported by ffmpeg
- Try installing additional codec packages

### "No LLM provider configured" error

- Configure a vision-capable LLM provider in AstrBot settings
- Ensure the provider supports image inputs

## License

MIT License

## Author

Minara

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-03-20

### Added
- **Skip first N seconds**: New `skip_first_seconds` config to skip video intros
- **Skip last N seconds**: New `skip_last_seconds` config to skip video outros
- **Frame interval mode**: New `frame_interval` config to extract 1 frame every N seconds (alternative to max_frames)
- Two frame extraction modes:
  - **Evenly distributed mode** (default): Extract N frames evenly across the video
  - **Interval mode**: Extract 1 frame every N seconds for consistent sampling
- Updated `/video_vision_status` command to display new timing configuration options
- Enhanced logging to show effective time range and extraction mode

### Changed
- Improved frame extraction to respect skip offsets for both modes
- Updated configuration schema with new timing options

## [1.0.0] - 2026-03-20

### Added
- Initial release of Video Vision plugin
- Automatic detection of video file attachments in Discord messages
- Frame extraction from videos using ffmpeg
- Support for multiple video formats (MP4, MOV, AVI, WebM, MKV, FLV, WMV, M4V)
- LLM-based video content analysis
- Configurable frame extraction settings (max frames, format)
- Platform filtering support
- Status command to check plugin configuration
- Graceful error handling for missing ffmpeg or unsupported videos
- Automatic cleanup of temporary files

### Features
- `/video_vision_status` command to check plugin status
- Automatic video analysis when video files are attached
- Evenly distributed frame extraction for better coverage
- Progress notification during analysis

"""
AstrBot Video Vision Plugin

This plugin detects video file attachments in Discord messages,
extracts key frames using ffmpeg, and sends them to the LLM for analysis.
"""

import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import File


# Default configuration
DEFAULT_CONFIG = {
    "enabled": True,
    "max_frames": 5,
    "frame_format": "jpg",
    "video_extensions": ["mp4", "mov", "avi", "webm", "mkv", "flv", "wmv", "m4v"],
    "platform_ids": [],
    "channel_ids": [],  # List of Discord channel IDs to process. Empty = all channels
    "skip_first_seconds": 0,  # Skip the first N seconds of the video
    "skip_last_seconds": 0,   # Skip the last N seconds of the video
    "frame_interval": 0,      # Extract one frame every N seconds (0 = use max_frames instead)
    "analysis_prompt": "Please analyze the content of this video based on the extracted frames. Describe what you see, including any actions, objects, people, or text visible in the frames."
}


@register(
    "astrbot_plugin_video_vision",
    "Minara",
    "Analyze video attachments from Discord messages using LLM vision capabilities",
    "1.0.0"
)
class VideoVisionPlugin(Star):
    """Plugin that analyzes video attachments using LLM vision capabilities."""

    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self._ffmpeg_available: Optional[bool] = None
        logger.info(f"[VideoVision] Plugin instance created with config: enabled={self.config.get('enabled', True)}")

    async def initialize(self):
        """Called when plugin is activated."""
        logger.info("[VideoVision] Plugin initialized")

        # Check if ffmpeg is available
        self._ffmpeg_available = await self._check_ffmpeg()
        if not self._ffmpeg_available:
            logger.warning("[VideoVision] ffmpeg is not available. Video analysis will be disabled.")
        else:
            logger.info("[VideoVision] ffmpeg is available")

        logger.info(f"[VideoVision] Configuration: max_frames={self.config['max_frames']}, "
                   f"frame_format={self.config['frame_format']}, "
                   f"skip_first={self.config.get('skip_first_seconds', 0)}s, "
                   f"skip_last={self.config.get('skip_last_seconds', 0)}s, "
                   f"frame_interval={self.config.get('frame_interval', 0)}s")

    async def terminate(self):
        """Called when plugin is disabled/reloaded."""
        logger.info("[VideoVision] Plugin terminated")

    async def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available on the system."""
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            return process.returncode == 0
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.error(f"[VideoVision] Error checking ffmpeg: {e}")
            return False

    def _is_video_file(self, filename: str) -> bool:
        """Check if a file is a video based on its extension."""
        if not filename:
            return False
        ext = Path(filename).suffix.lower().lstrip(".")
        return ext in self.config["video_extensions"]

    def _should_process_platform(self, event: AstrMessageEvent) -> bool:
        """Check if the platform should be processed based on configuration."""
        platform_ids = self.config.get("platform_ids", [])
        if not platform_ids:
            return True

        platform_id = event.platform_meta.id if event.platform_meta else None
        return platform_id in platform_ids

    def _should_process_channel(self, event: AstrMessageEvent) -> bool:
        """Check if the channel should be processed based on configuration."""
        channel_ids = self.config.get("channel_ids", [])
        if not channel_ids:
            return True

        # Get channel ID from session_id or unified_msg_origin
        session_id = event.session_id or ""
        unified_origin = event.unified_msg_origin or ""

        # Convert configured channel IDs to strings for comparison
        channel_ids_str = [str(cid) for cid in channel_ids]

        # Check if any configured channel ID is in the session or unified origin
        for channel_id in channel_ids_str:
            if channel_id in session_id or channel_id in unified_origin or session_id == channel_id:
                return True

        return False

    async def _get_video_duration(self, video_path: str) -> Optional[float]:
        """Get video duration using ffprobe."""
        try:
            process = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return float(stdout.decode().strip())
            else:
                logger.error(f"[VideoVision] ffprobe error: {stderr.decode()}")
                return None
        except Exception as e:
            logger.error(f"[VideoVision] Error getting video duration: {e}")
            return None

    async def _download_file(self, url: str, dest_path: str) -> bool:
        """Download a file from URL to destination path."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(dest_path, "wb") as f:
                            f.write(await response.read())
                        return True
                    else:
                        logger.error(f"[VideoVision] Failed to download file: HTTP {response.status}")
                        return False
        except Exception as e:
            logger.error(f"[VideoVision] Error downloading file: {e}")
            return False

    async def _extract_frames(
        self,
        video_path: str,
        output_dir: str,
        max_frames: int,
        frame_format: str,
        skip_first_seconds: float = 0,
        skip_last_seconds: float = 0,
        frame_interval: float = 0
    ) -> List[str]:
        """
        Extract frames from a video with configurable timing options.

        Args:
            video_path: Path to the video file
            output_dir: Directory to save extracted frames
            max_frames: Maximum number of frames to extract (used if frame_interval=0)
            frame_format: Output format (jpg, png, etc.)
            skip_first_seconds: Skip the first N seconds of the video
            skip_last_seconds: Skip the last N seconds of the video
            frame_interval: Extract one frame every N seconds (0 = use max_frames)

        Returns:
            List of paths to extracted frame files
        """
        # Get video duration
        duration = await self._get_video_duration(video_path)
        if not duration or duration <= 0:
            logger.error("[VideoVision] Could not determine video duration")
            return []

        # Calculate effective time range after skipping
        start_time = skip_first_seconds
        end_time = duration - skip_last_seconds

        if end_time <= start_time:
            logger.error(
                f"[VideoVision] Invalid time range: start={start_time}s, end={end_time}s "
                f"(skip_first={skip_first_seconds}s, skip_last={skip_last_seconds}s, duration={duration}s)"
            )
            return []

        effective_duration = end_time - start_time
        logger.info(
            f"[VideoVision] Video duration: {duration}s, "
            f"effective range: {start_time:.1f}s - {end_time:.1f}s ({effective_duration:.1f}s)"
        )

        extracted_frames = []
        output_pattern = os.path.join(output_dir, f"frame_%03d.{frame_format}")

        try:
            if frame_interval > 0:
                # Use frame_interval mode: extract one frame every N seconds
                # Calculate how many frames we'll get
                num_frames = int(effective_duration / frame_interval)
                if num_frames < 1:
                    num_frames = 1

                logger.info(
                    f"[VideoVision] Interval mode: extracting 1 frame every {frame_interval}s "
                    f"(~{num_frames} frames from {effective_duration:.1f}s range)"
                )

                # Build ffmpeg command with select filter for interval extraction
                # Use -ss for start time and -t for duration
                cmd = [
                    "ffmpeg",
                    "-ss", str(start_time),  # Start time (fast seek)
                    "-i", video_path,
                    "-t", str(effective_duration),  # Duration to process
                    "-vf", f"fps=1/{frame_interval}",  # 1 frame every N seconds
                    "-y",  # Overwrite output files
                    output_pattern
                ]
            else:
                # Use max_frames mode: extract evenly distributed frames
                actual_frames = min(max_frames, max(1, int(effective_duration)))
                if actual_frames < max_frames:
                    logger.info(
                        f"[VideoVision] Video range is short ({effective_duration}s), "
                        f"extracting {actual_frames} frames"
                    )

                # Calculate fps for evenly distributed frames
                fps = actual_frames / effective_duration

                logger.info(
                    f"[VideoVision] Max frames mode: extracting {actual_frames} evenly "
                    f"distributed frames from {effective_duration:.1f}s range"
                )

                cmd = [
                    "ffmpeg",
                    "-ss", str(start_time),  # Start time (fast seek)
                    "-i", video_path,
                    "-t", str(effective_duration),  # Duration to process
                    "-vf", f"fps={fps:.6f}",
                    "-vframes", str(actual_frames),
                    "-y",  # Overwrite output files
                    output_pattern
                ]

            logger.debug(f"[VideoVision] Running ffmpeg: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"[VideoVision] ffmpeg error: {stderr.decode()}")

            # Find extracted frames (they're numbered sequentially by ffmpeg)
            for i in range(1, 1000):  # Reasonable upper limit
                frame_path = os.path.join(output_dir, f"frame_{i:03d}.{frame_format}")
                if os.path.exists(frame_path):
                    extracted_frames.append(frame_path)
                else:
                    break  # No more frames

            logger.info(f"[VideoVision] Extracted {len(extracted_frames)} frames")

        except Exception as e:
            logger.error(f"[VideoVision] Error extracting frames: {e}")

        return extracted_frames

    async def _analyze_frames_with_llm(
        self,
        event: AstrMessageEvent,
        frame_paths: List[str],
        prompt: str
    ) -> Optional[str]:
        """
        Send extracted frames to LLM for analysis.

        Args:
            event: The message event
            frame_paths: List of paths to frame images
            prompt: Analysis prompt

        Returns:
            LLM analysis response or None if failed
        """
        try:
            # Get the current chat provider
            provider_id = await self.context.get_current_chat_provider_id(
                event.unified_msg_origin
            )

            if not provider_id:
                logger.error("[VideoVision] No LLM provider configured")
                return None

            # Build image URLs from frame paths (use absolute paths)
            # Note: Pass absolute paths directly without file:// prefix
            # AstrBot's resolve_image_part() incorrectly strips leading / from file:/// URLs
            image_urls = []
            for frame_path in frame_paths:
                # Ensure absolute path
                abs_path = os.path.abspath(frame_path)
                image_urls.append(abs_path)

            # Call the LLM with prompt and image URLs
            response = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                image_urls=image_urls
            )

            if response and response.completion_text:
                return response.completion_text
            else:
                logger.error("[VideoVision] Empty LLM response")
                return None

        except Exception as e:
            logger.error(f"[VideoVision] Error analyzing frames with LLM: {e}")
            import traceback
            traceback.print_exc()
            return None

    @filter.platform_adapter_type(filter.PlatformAdapterType.DISCORD)
    async def on_discord_message(self, event: AstrMessageEvent):
        """
        Handle Discord messages and check for video attachments.
        """
        logger.debug(f"[VideoVision] Handler triggered for Discord message")

        # Check if plugin is enabled
        if not self.config.get("enabled", True):
            logger.debug("[VideoVision] Plugin is disabled, skipping")
            return

        # Check if ffmpeg is available
        if not self._ffmpeg_available:
            logger.debug("[VideoVision] ffmpeg not available, skipping")
            return

        # Check platform filter
        if not self._should_process_platform(event):
            logger.debug("[VideoVision] Platform not in filter list, skipping")
            return

        # Check channel filter
        if not self._should_process_channel(event):
            logger.debug("[VideoVision] Channel not in filter list, skipping")
            return

        # Get message components
        messages = event.get_messages()
        if not messages:
            logger.debug("[VideoVision] No message components found")
            return

        # Find video file attachments
        video_files = []
        for msg in messages:
            if isinstance(msg, File):
                logger.debug(f"[VideoVision] Found file attachment: {msg.name}")
                if self._is_video_file(msg.name):
                    video_files.append(msg)

        if not video_files:
            logger.debug("[VideoVision] No video file attachments found in message")
            return

        logger.info(f"[VideoVision] Found {len(video_files)} video attachment(s)")

        # Process each video
        for video_file in video_files:
            try:
                for result in await self._process_video(event, video_file):
                    yield result
            except Exception as e:
                logger.error(f"[VideoVision] Error processing video: {e}")
                import traceback
                traceback.print_exc()

    async def _process_video(self, event: AstrMessageEvent, video_file: File):
        """
        Process a single video file attachment.
        Returns a list of results to yield.
        """
        results = []

        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp(prefix="video_vision_")

        try:
            # Download the video file
            video_url = video_file.url
            if not video_url:
                logger.error("[VideoVision] Video file has no URL")
                return results

            video_filename = video_file.name or "video.mp4"
            video_path = os.path.join(temp_dir, video_filename)

            logger.info(f"[VideoVision] Downloading video: {video_filename}")

            if not await self._download_file(video_url, video_path):
                results.append(event.plain_result("Failed to download video file for analysis."))
                return results

            logger.info("[VideoVision] Video downloaded, extracting frames...")

            # Extract frames
            frames_dir = os.path.join(temp_dir, "frames")
            os.makedirs(frames_dir)

            frame_paths = await self._extract_frames(
                video_path,
                frames_dir,
                self.config["max_frames"],
                self.config["frame_format"],
                skip_first_seconds=self.config.get("skip_first_seconds", 0),
                skip_last_seconds=self.config.get("skip_last_seconds", 0),
                frame_interval=self.config.get("frame_interval", 0)
            )

            if not frame_paths:
                results.append(event.plain_result(
                    "Failed to extract frames from video. "
                    "The video may be too short or in an unsupported format."
                ))
                return results

            logger.info(f"[VideoVision] Extracted {len(frame_paths)} frames, analyzing with LLM...")

            # Send notification that analysis is in progress
            await event.send(event.plain_result(
                f"Analyzing video ({len(frame_paths)} frames extracted)..."
            ))

            # Analyze with LLM
            analysis = await self._analyze_frames_with_llm(
                event,
                frame_paths,
                self.config["analysis_prompt"]
            )

            if analysis:
                # Send the analysis result
                results.append(event.plain_result(f"Video Analysis:\n\n{analysis}"))
            else:
                results.append(event.plain_result("Failed to analyze video content."))

        finally:
            # Clean up temporary files
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"[VideoVision] Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"[VideoVision] Failed to clean up temp directory: {e}")

        return results

    @filter.command("video_vision_status")
    async def status_command(self, event: AstrMessageEvent):
        """Check video vision plugin status."""
        status_parts = [
            "**Video Vision Plugin Status**",
            f"- Enabled: {self.config.get('enabled', True)}",
            f"- FFmpeg Available: {self._ffmpeg_available}",
            f"- Max Frames: {self.config.get('max_frames', 5)}",
            f"- Frame Format: {self.config.get('frame_format', 'jpg')}",
            f"- Skip First Seconds: {self.config.get('skip_first_seconds', 0)}s",
            f"- Skip Last Seconds: {self.config.get('skip_last_seconds', 0)}s",
            f"- Frame Interval: {self.config.get('frame_interval', 0)}s (0 = use max_frames)",
            f"- Supported Extensions: {', '.join(self.config.get('video_extensions', []))}",
        ]

        platform_ids = self.config.get("platform_ids", [])
        if platform_ids:
            status_parts.append(f"- Platform Filter: {', '.join(platform_ids)}")
        else:
            status_parts.append("- Platform Filter: All platforms")

        channel_ids = self.config.get("channel_ids", [])
        if channel_ids:
            status_parts.append(f"- Channel Filter: {', '.join(str(cid) for cid in channel_ids)}")
        else:
            status_parts.append("- Channel Filter: All channels")

        yield event.plain_result("\n".join(status_parts))

    @filter.command("video_vision_enable")
    async def enable_command(self, event: AstrMessageEvent):
        """Enable video vision plugin."""
        self.config["enabled"] = True
        yield event.plain_result("Video Vision plugin enabled.")

    @filter.command("video_vision_disable")
    async def disable_command(self, event: AstrMessageEvent):
        """Disable video vision plugin."""
        self.config["enabled"] = False
        yield event.plain_result("Video Vision plugin disabled.")

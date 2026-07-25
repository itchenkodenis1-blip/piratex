import asyncio
from pathlib import Path

from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

from app.config import settings
from app.core.exceptions import SceneDetectionError


async def detect_scenes(
    video_path: Path,
    threshold: float | None = None,
    safety_interval: float | None = None,
) -> list[float]:
    """
    Hybrid scene detection:
    1. ContentDetector for real scene changes
    2. Safety frames every N seconds if gap is too large
    3. Always include first and last frame
    Returns sorted list of timestamps in seconds.
    """
    if threshold is None:
        threshold = settings.scene_detect_threshold
    if safety_interval is None:
        safety_interval = settings.safety_frame_interval

    def _detect():
        try:
            video = open_video(str(video_path))
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=threshold))
            scene_manager.detect_scenes(video)
            scene_list = scene_manager.get_scene_list()

            # Start timestamp of each scene
            timestamps = [scene[0].get_seconds() for scene in scene_list]

            # Video duration
            duration = video.duration.get_seconds()

            # Always include first frame
            if not timestamps or timestamps[0] > 0.5:
                timestamps.insert(0, 0.0)

            # Always include last frame
            if duration - timestamps[-1] > 1.0:
                timestamps.append(max(0, duration - 0.1))

            # Insert safety frames in large gaps
            filled = []
            for i in range(len(timestamps)):
                filled.append(timestamps[i])
                if i < len(timestamps) - 1:
                    gap = timestamps[i + 1] - timestamps[i]
                    if gap > safety_interval * 1.5:
                        t = timestamps[i] + safety_interval
                        while t < timestamps[i + 1] - 1.0:
                            filled.append(t)
                            t += safety_interval

            return sorted(set(filled))
        except Exception as e:
            raise SceneDetectionError(f"Scene detection failed: {e}") from e

    return await asyncio.get_event_loop().run_in_executor(None, _detect)

class PiratexError(Exception):
    pass


class DownloadError(PiratexError):
    pass


class TranscriptionError(PiratexError):
    pass


class SceneDetectionError(PiratexError):
    pass


class VisionAnalysisError(PiratexError):
    pass


class VideoTooLongError(PiratexError):
    pass


class NotYouTubeShortsError(PiratexError):
    """URL is a regular YouTube video, not a Short."""
    pass


class ApifyBudgetExhausted(DownloadError):
    """Apify daily run limit or balance threshold exceeded."""
    pass


class InsufficientDataError(PiratexError):
    """Not enough data (transcript + frames) to generate content."""
    pass


class InvalidURLError(PiratexError, ValueError):
    """URL failed validation (SSRF, unsupported platform, etc.)."""
    pass

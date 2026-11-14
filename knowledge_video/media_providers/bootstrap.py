from .fake import FakeImageProvider, FakeVideoProvider
from .local import LocalProceduralImageProvider
from .registry import register_image_provider, register_video_provider

register_image_provider("fake", FakeImageProvider(), {"fake"})
register_image_provider("local", LocalProceduralImageProvider(), {"procedural"})
register_video_provider("fake", FakeVideoProvider(), {"fake"})

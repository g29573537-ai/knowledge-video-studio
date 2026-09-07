"""Video languages with a known WhisperX forced-alignment backend."""

from typing import Literal

Language = Literal["zh", "en", "ja", "ko", "fr", "de", "es", "it", "pt", "ru"]
LANGUAGES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "ru": "Русский",
}
ASR_MODELS = {
    "small": "Whisper Small · 约 0.5 GB",
    "medium": "Whisper Medium · 约 1.5 GB",
    "large-v3": "Whisper Large v3 · 约 3 GB",
}


def language_instruction(code):
    name = LANGUAGES[code]
    if code == "zh":
        return "\n本次课程语言为中文。"
    return (
        f"\n本次课程的口播、标题、课件、简介必须使用 {name}（{code}），这项要求优先于前面的中文写作约定。"
        "保持自然、克制的讲课风格，数字写成目标语言适合朗读的形式。"
        "策划长度按目标语言的正常语速估算，欧洲语言约每分钟一百三十词，不按汉字计算。"
        "中英文术语仅在确有必要时并列；审稿意见可以用中文。"
    )

from typing import Literal

from pydantic import BaseModel, Field

from .languages import Language


class ProviderConfig(BaseModel):
    kind: Literal["codex", "external"] = "codex"
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    api_key_env: str = "KNOWLEDGE_VIDEO_API_KEY"
    json_mode: Literal["schema", "object", "prompt"] = "object"
    vision: bool = False
    timeout: int = Field(default=600, ge=30, le=3600)
    reasoning_effort: Literal["", "low", "high", "max"] = ""


class JobRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=500)
    audience: str = Field(default="没有相关背景的普通读者", max_length=300)
    minutes: float = Field(default=3, ge=0.3, le=20)
    playback_speed: float = Field(default=1.2, ge=0.5, le=2)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    language: Language = "zh"
    reference_language: Literal[
        "auto", "zh", "en", "ja", "ko", "fr", "de", "es", "it", "pt", "ru"
    ] = "auto"
    asr_model: Literal["small", "medium", "large-v3"] = "small"
    voice_path: str = ""
    voice_upload: str = ""
    reference_text: str = ""
    profile_id: str = ""
    voice_url: str = "http://127.0.0.1:3900"
    slides_mode: Literal["generate", "existing"] = "generate"
    slides_path: str = ""
    template_path: str = ""
    reference_urls: list[str] = Field(default_factory=list, max_length=8)
    source_notes: str = Field(default="", max_length=20000)
    chrome: str = ""
    subtitle_font: str = ""
    max_repairs: int = Field(default=2, ge=0, le=4)


class ResearchPlan(BaseModel):
    title: str
    learning_goal: str
    outline: list[str]
    candidate_urls: list[str]


class Block(BaseModel):
    id: str
    slide_id: str
    narration: str
    headline: str
    points: list[str]
    source_ids: list[str]
    visual_role: Literal[
        "hero", "explanatory_core", "secondary", "bridge", "background"
    ] = "hero"
    semantic_version: int = 1


class Lesson(BaseModel):
    title: str
    description: str
    blocks: list[Block]
    uncertainties: list[str]


class DeckOutput(BaseModel):
    html: str


class Review(BaseModel):
    approved: bool
    issues: list[str]
    lesson: Lesson


class VisualReview(BaseModel):
    approved: bool
    issues: list[str]


class SpeechReview(BaseModel):
    rerecord_ids: list[str]
    notes: list[str]

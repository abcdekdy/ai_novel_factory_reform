"""
Pydantic 数据模型 — 前后端通信契约
"""
from typing import Optional
from pydantic import BaseModel


class StartRequest(BaseModel):
    inspiration: str
    chapter_count: Optional[int] = None
    chapter_length: Optional[int] = None
    api_key: Optional[str] = None


class ResumeRequest(BaseModel):
    project_dir: str


class ContinueRequest(BaseModel):
    project_dir: str
    guidance: str = ""
    batch_chapter_count: int = 5


class ConfirmWorldViewRequest(BaseModel):
    world_view: dict


class ConfirmContinuationRequest(BaseModel):
    outline: dict


class ConfigUpdateRequest(BaseModel):
    api_key: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    concurrency: Optional[int] = None
    max_revision_rounds: Optional[int] = None
    quality_threshold: Optional[float] = None
    default_chapter_count: Optional[int] = None
    default_chapter_length: Optional[int] = None
    theme: Optional[str] = None

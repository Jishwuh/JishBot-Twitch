from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Channel:
    channel_id: str
    channel_name: str
    is_enabled: int
    created_at: int


@dataclass
class Command:
    id: int
    channel_id: str
    name: str
    response: str
    enabled: int
    permission: str
    cooldown_global: int
    cooldown_user: int
    created_at: int
    updated_at: int


@dataclass
class Timer:
    id: int
    channel_id: str
    name: str
    messages: List[str]
    interval_minutes: int
    require_chat_activity: int
    enabled: int


@dataclass
class Filter:
    id: int
    channel_id: str
    type: str
    pattern: str
    enabled: int


@dataclass
class LinkSettings:
    channel_id: str
    enabled: int
    allow_mod: int
    allow_sub: int
    allow_regular: int
    allowed_domains: List[str]


@dataclass
class Giveaway:
    channel_id: str
    is_active: int
    keyword: Optional[str]
    entries: List[dict]
    started_at: Optional[int]

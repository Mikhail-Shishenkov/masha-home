"""Application-owned Home timezone configuration and portable resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Callable, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HomeTimeZoneResolutionError(ValueError):
    """A configured timezone cannot be resolved without an explicit fallback."""


class HomeTimeZoneConfig(BaseModel):
    """Operating configuration; deliberately separate from Identity and Memory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timezone: str | None = Field(default="Europe/Saratov", min_length=1)
    fallback_utc_offset_minutes: int | None = Field(default=240, ge=-840, le=840)

    @model_validator(mode="after")
    def require_named_fallback_for_default_home(self):
        if self.timezone is None and self.fallback_utc_offset_minutes is not None:
            raise ValueError("system-local timezone must not declare a configured offset")
        return self


class HomeTimeZoneStore:
    """Small atomic JSON store for the Home's operating timezone."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(HomeTimeZoneConfig())

    def load(self) -> HomeTimeZoneConfig:
        return HomeTimeZoneConfig.model_validate(
            json.loads(self.path.read_text(encoding="utf-8"))
        )

    def save(self, config: HomeTimeZoneConfig) -> HomeTimeZoneConfig:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return config


@dataclass(frozen=True)
class HomeTimeZone:
    name: str
    tzinfo: tzinfo
    resolution: Literal["named_zone", "configured_offset_fallback", "system_local"]


class HomeTimeZoneProvider:
    """Resolve configured IANA zones with an explicit Windows-safe fallback."""

    def __init__(
        self,
        config: HomeTimeZoneConfig | None = None,
        *,
        zone_loader: Callable[[str], tzinfo] = ZoneInfo,
        system_local: Callable[[], datetime] | None = None,
    ):
        self.config = config or HomeTimeZoneConfig()
        self._zone_loader = zone_loader
        self._system_local = system_local or (lambda: datetime.now().astimezone())

    @classmethod
    def from_store(cls, store: HomeTimeZoneStore) -> "HomeTimeZoneProvider":
        return cls(store.load())

    def resolve(self) -> HomeTimeZone:
        configured = self.config.timezone
        if configured is None:
            local = self._system_local()
            if local.tzinfo is None:
                raise HomeTimeZoneResolutionError("system local timezone is unavailable")
            return HomeTimeZone(
                name=str(local.tzinfo) or "system-local",
                tzinfo=local.tzinfo,
                resolution="system_local",
            )
        try:
            return HomeTimeZone(
                name=configured,
                tzinfo=self._zone_loader(configured),
                resolution="named_zone",
            )
        except ZoneInfoNotFoundError as error:
            offset = self.config.fallback_utc_offset_minutes
            if offset is None:
                raise HomeTimeZoneResolutionError(
                    f"configured timezone is unavailable: {configured}"
                ) from error
            return HomeTimeZone(
                name=configured,
                tzinfo=timezone(timedelta(minutes=offset), name=configured),
                resolution="configured_offset_fallback",
            )

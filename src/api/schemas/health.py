from __future__ import annotations

from typing import Literal

from src.api.schemas.base import StrictApiModel


class HealthResponse(StrictApiModel):
    status: Literal["ok", "ready"]
    service: Literal["ecloe-engine"]

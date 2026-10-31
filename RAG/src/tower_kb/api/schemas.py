from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Upload(StrictModel):
    title: str = Field(min_length=1,max_length=200)
    source_id: str = Field(min_length=1,max_length=200)
    source_revision: int = Field(ge=1)
    source_kind: Literal["standard","case"] = "standard"
    content: str = Field(min_length=1,max_length=1_000_000)
    roles: list[str] = Field(default_factory=lambda:["engineer"],min_length=1,max_length=30)
    regions: list[str] = Field(default_factory=lambda:["demo-region"],min_length=1,max_length=100)
    effect_start: str | None = None
    effect_end: str | None = None

    @field_validator("content")
    @classmethod
    def valid_content(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Content must be nonblank UTF-8 text without NUL")
        return value

    @field_validator("effect_start","effect_end")
    @classmethod
    def timestamp(cls,value):
        if value is None: return value
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None: raise ValueError("Timezone required")
        return stamp.astimezone(timezone.utc).isoformat()

    @model_validator(mode="after")
    def interval(self):
        if self.effect_start and self.effect_end and self.effect_start >= self.effect_end:
            raise ValueError("effect_end must be later than effect_start")
        return self

class Filters(StrictModel):
    source_kind: Literal["standard","case"] | None = None

class Chat(StrictModel):
    query: str = Field(min_length=2,max_length=2000)
    session_id: str | None = Field(default=None,max_length=64)
    filters: Filters = Field(default_factory=Filters)

class Feedback(StrictModel):
    request_id: str = Field(min_length=1,max_length=64)
    comment: str = Field(min_length=1,max_length=4000)

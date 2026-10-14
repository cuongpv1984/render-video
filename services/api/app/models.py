from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Scene(StrictModel):
    client_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    script: str = Field(min_length=1, max_length=2000)
    duration: int = Field(ge=2, le=15, strict=True)
    motion: int = Field(ge=0, le=3, strict=True)
    route: Literal["auto", "motion", "standard", "hero"] = "auto"
    approved: bool = False
    art: Literal["dawn", "forest", "stars", "sunset"] = "dawn"

class ProjectInput(StrictModel):
    client_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    budget_micro_usd: int = Field(ge=0, le=100_000_000_000, strict=True)
    scenes: list[Scene] = Field(min_length=1, max_length=30)

class QuoteInput(StrictModel):
    project_id: str
    retry: bool = False

class RunInput(StrictModel):
    accepted_ceiling_micro_usd: int = Field(ge=0, strict=True)
    input_hash: str

class BudgetInput(StrictModel):
    limit_micro_usd: int = Field(ge=0, le=100_000_000_000, strict=True)

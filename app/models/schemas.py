from pydantic import BaseModel, Field
from typing import Optional


class HomePlannerInput(BaseModel):
    budget: float = Field(gt=0)
    room_type: str
    quantity: int = Field(default=1, ge=1, le=100)
    style: str
    needs: str = ""


class PartyPlannerInput(BaseModel):
    budget: float = Field(gt=0)
    guest_count: int = Field(ge=1, le=10000)
    event_type: str
    venue: str = ""
    preferences: str = ""


class JewelryPlannerInput(BaseModel):
    budget: float = Field(gt=0)
    occasion: str
    style: str
    outfit_notes: str = ""
    image_path: Optional[str] = None

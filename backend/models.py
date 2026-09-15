"""Pydantic request/response models.

WARNING: Passwords are intentionally accepted as visible plaintext for this
demo only. Production code must never expose or persist plaintext passwords.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    role: Literal["farmer", "buyer", "transporter"]
    location: str = ""
    phone: str = ""
    vehicle_type: str = ""
    vehicle_capacity: float | None = None

    @field_validator("vehicle_capacity", mode="before")
    @classmethod
    def empty_vehicle_capacity_is_none(cls, value):
        return None if value == "" else value
    lat: float | None = None
    lon: float | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    location: str = ""
    phone: str = ""
    vehicle_type: str = ""
    vehicle_capacity: float | None = None


class ListingCreate(BaseModel):
    farmer_id: int
    crop: str
    variety: str = ""
    quantity: float = Field(gt=0)
    unit: str = "quintal"
    price: float = Field(gt=0)
    location: str = ""
    harvest_date: str = ""
    quality: str = "standard"
    description: str = ""
    photo_url: str = Field(default="", max_length=2_000_000)


class ListingIngestRequest(BaseModel):
    farmer_id: int
    raw_text: str = Field(min_length=5)
    photo_url: str = Field(default="", max_length=2_000_000)


class ListingUpdate(BaseModel):
    farmer_id: int
    crop: str
    variety: str = ""
    quantity: float = Field(gt=0)
    unit: str = "quintal"
    price: float = Field(gt=0)
    location: str = ""
    harvest_date: str = ""
    quality: str = "standard"
    description: str = ""
    photo_url: str = Field(default="", max_length=2_000_000)


class DemandCreate(BaseModel):
    buyer_id: int
    crop: str
    quantity: float = Field(gt=0)
    unit: str = "quintal"
    target_price: float = 0
    location: str = ""
    needed_by: str = ""


class MatchRequest(BaseModel):
    crop: str
    quantity: Optional[float] = None
    location: str = ""
    buyer_id: Optional[int] = None


class OrderCreate(BaseModel):
    listing_id: int
    buyer_id: int
    quantity: float = Field(gt=0)
    agreed_price: Optional[float] = None
    delivery_deadline: str | None = None


class CounterRequest(BaseModel):
    counter_price: float = Field(gt=0)
    by: Literal["farmer", "buyer"] = "farmer"


class SuggestRequest(BaseModel):
    order_id: int


class AdvisoryRequest(BaseModel):
    farmer_id: int
    crop: str
    question: str


class PaymentRequest(BaseModel):
    method: str = "demo"


class QualityRequest(BaseModel):
    status: Literal["passed", "failed", "pending"]
    note: str = ""


class RouteClaimRequest(BaseModel):
    transporter_id: int


class TransportPhotoRequest(BaseModel):
    transporter_id: int
    photo_url: str = Field(min_length=1, max_length=2_000_000)

    @field_validator("photo_url")
    @classmethod
    def photo_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A pickup or delivery photo is required")
        return value

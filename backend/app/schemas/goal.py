import uuid
from datetime import date as _Date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GoalCreate(BaseModel):
    name: str
    target_amount: Decimal
    current_amount: Decimal = Decimal("0")
    currency: str = "USD"
    target_date: Optional[_Date] = None
    tracking_type: str = "manual"
    account_id: Optional[uuid.UUID] = None
    asset_id: Optional[uuid.UUID] = None
    asset_group_id: Optional[uuid.UUID] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    metadata_json: Optional[Any] = None

    @field_validator("tracking_type")
    @classmethod
    def validate_tracking_type(cls, v: str) -> str:
        if v not in ("manual", "account", "asset", "asset_group", "net_worth"):
            raise ValueError("tracking_type must be manual, account, asset, asset_group, or net_worth")
        return v


class GoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[Decimal] = None
    current_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    target_date: Optional[_Date] = None
    tracking_type: Optional[str] = None
    account_id: Optional[uuid.UUID] = None
    asset_id: Optional[uuid.UUID] = None
    asset_group_id: Optional[uuid.UUID] = None
    status: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None
    metadata_json: Optional[Any] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("active", "completed", "paused", "archived", "missed"):
            raise ValueError("status must be active, completed, paused, archived, or missed")
        return v

    @field_validator("tracking_type")
    @classmethod
    def validate_tracking_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("manual", "account", "asset", "asset_group", "net_worth"):
            raise ValueError("tracking_type must be manual, account, asset, asset_group, or net_worth")
        return v


class GoalRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    target_amount: Decimal
    current_amount: Decimal
    currency: str
    target_amount_primary: Optional[Decimal] = None
    current_amount_primary: Optional[Decimal] = None
    target_date: Optional[_Date] = None
    tracking_type: str
    account_id: Optional[uuid.UUID] = None
    asset_id: Optional[uuid.UUID] = None
    asset_group_id: Optional[uuid.UUID] = None
    status: str
    icon: Optional[str] = None
    color: Optional[str] = None
    position: int
    metadata_json: Optional[Any] = None
    # Set on instances of a recurring goal.
    recurring_goal_id: Optional[uuid.UUID] = None
    period_start: Optional[_Date] = None
    period_end: Optional[_Date] = None
    created_at: datetime
    updated_at: datetime

    # Computed fields
    percentage: float = 0
    monthly_contribution: Optional[float] = None
    on_track: Optional[str] = None  # ahead, on_track, behind, overdue, achieved

    # Linked account/asset info
    account_name: Optional[str] = None
    asset_name: Optional[str] = None
    asset_group_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GoalSummary(BaseModel):
    id: uuid.UUID
    name: str
    target_amount: Decimal
    current_amount: Decimal
    currency: str
    target_date: Optional[_Date] = None
    status: str
    icon: Optional[str] = None
    color: Optional[str] = None
    percentage: float = 0
    monthly_contribution: Optional[float] = None
    on_track: Optional[str] = None


class RecurringGoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target_amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    # Day of the month each period starts on.
    start_day: int = Field(ge=1, le=31)
    icon: Optional[str] = None
    color: Optional[str] = None


class RecurringGoalUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    target_amount: Optional[Decimal] = Field(default=None, gt=0)
    start_day: Optional[int] = Field(default=None, ge=1, le=31)
    icon: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


class RecurringGoalRead(BaseModel):
    id: uuid.UUID
    name: str
    target_amount: Decimal
    currency: str
    start_day: int
    icon: Optional[str] = None
    color: Optional[str] = None
    is_active: bool
    next_period_start: _Date
    created_at: datetime
    updated_at: datetime

    # Computed fields
    # The instance covering today, if there is one.
    current_goal_id: Optional[uuid.UUID] = None
    # Closed periods, and how many of them reached the target.
    periods_closed: int = 0
    periods_met: int = 0

    model_config = ConfigDict(from_attributes=True)

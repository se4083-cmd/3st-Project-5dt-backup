from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    login_name: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128, repr=False)


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class CurrentUser(BaseModel):
    user_id: UUID
    login_name: str
    role: Literal["CUSTOMER", "AGENT", "ADMIN"]


class OrderPublic(BaseModel):
    order_id: UUID
    product_id: UUID | None
    order_number: str
    quantity: int
    order_status: str
    payment_status: str
    amount: Decimal
    placed_at: datetime


class TicketCreate(Input):
    order_id: UUID | None = None
    message: str = Field(min_length=1, max_length=10000)

    @field_validator("message")
    @classmethod
    def meaningful_message(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Message must contain non-whitespace characters")
        return value


class TicketReceipt(BaseModel):
    ticket_id: UUID
    created_at: datetime


class ReopenRequest(Input):
    expected_revision: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=10000)
    _message = field_validator("message")(TicketCreate.meaningful_message.__func__)


class AgentRequest(ReopenRequest):
    reason_code: Literal["CUSTOMER_REQUEST", "DISSATISFIED", "COMPLEX_ISSUE", "OTHER"]


class TicketActionReceipt(BaseModel):
    ticket_id: UUID
    cycle_no: int
    revision: int
    stage: Literal["RECEIVED", "WAITING_FOR_SUPPORT"]
    handling_mode: Literal["AUTOMATED", "HUMAN"]
    requested_at: datetime


class MessagePublic(BaseModel):
    message_id: UUID
    cycle_no: int
    sender: Literal["CUSTOMER", "SUPPORT"]
    body: str
    created_at: datetime


class TicketPublic(BaseModel):
    ticket_id: UUID
    order_id: UUID | None
    product_id: UUID | None
    revision: int
    cycle_no: int
    stage: Literal[
        "RECEIVED",
        "PROCESSING",
        "NEEDS_INFORMATION",
        "WAITING_FOR_SUPPORT",
        "IN_SUPPORT",
        "FOLLOWUP",
        "COMPLETED",
        "CANCELLED",
    ]
    handling_mode: Literal["AUTOMATED", "HUMAN"]
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketPublic):
    messages: list[MessagePublic]
    messages_has_more: bool


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class ErrorBody(BaseModel):
    code: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody

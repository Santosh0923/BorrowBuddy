from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
import re


# =========================================================
# AUTH SCHEMAS
# =========================================================

class UserRegister(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=150)
    password: str = Field(min_length=8, max_length=128)

    @field_validator('name')
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError('Name is required')
        return value.strip()

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address')
        return value


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool = True
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    name: str
    user_id: int


# =========================================================
# RESOURCE SCHEMAS
# =========================================================

class ResourceCreate(BaseModel):
    """Admin uses this to add new resources or replenish stock.
    quantity = number of units to add.
    Backend handles total_quantity / available_quantity."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=150)
    quantity: int = Field(default=1, gt=0, le=100000)
    description: Optional[str] = None


class ResourceUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    custodian_id: Optional[int] = None
    status: Optional[Literal['Available', 'Out of Stock', 'Maintenance', 'Retired']] = None
    is_active: Optional[bool] = None


class ResourceResponse(BaseModel):
    id: int
    name: str
    category: str
    location: str
    description: Optional[str] = None
    total_quantity: int
    available_quantity: int
    reserved_quantity: int = 0
    issued_quantity: int = 0
    inspection_quantity: int = 0
    maintenance_quantity: int = 0
    unavailable_quantity: int = 0
    verification_status: str
    verification_reason: Optional[str] = None
    verified_by: Optional[int] = None
    verified_at: Optional[datetime] = None
    status: str
    custodian_id: Optional[int] = None
    custodian_name: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# BORROW REQUEST SCHEMAS
# =========================================================

class BorrowRequestCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    resource_id: int
    quantity: int = Field(default=1, gt=0, le=100000)
    purpose: str = Field(min_length=1, max_length=2000)
    return_date: date


class ApprovalAction(BaseModel):
    remarks: Optional[str] = None


class RejectionAction(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=2000)
    model_config = ConfigDict(str_strip_whitespace=True)


class InspectionAction(BaseModel):
    condition: str  # Good, Minor Damage, Major Damage, Missing Components
    notes: Optional[str] = None


class MaintenanceCompleteAction(BaseModel):
    notes: Optional[str] = None
    restore_quantity: bool = True


class BorrowRequestResponse(BaseModel):
    id: int
    student_id: int
    student_name: str
    student_email: str
    resource_id: int
    resource_name: Optional[str] = None
    quantity: int
    purpose: Optional[str] = None
    return_date: date
    status: str

    approved_by: Optional[int] = None
    approver_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    custodian_id: Optional[int] = None
    custodian_name: Optional[str] = None

    ready_at: Optional[datetime] = None
    collected_at: Optional[datetime] = None
    returned_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    inspection_condition: Optional[str] = None
    inspection_notes: Optional[str] = None
    inspected_by: Optional[int] = None
    inspector_name: Optional[str] = None
    inspection_date: Optional[datetime] = None

    is_due_soon: bool = False
    is_overdue: bool = False

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# REQUEST HISTORY SCHEMAS
# =========================================================

class RequestHistoryResponse(BaseModel):
    id: int
    request_id: int
    old_status: Optional[str] = None
    new_status: str
    action: str
    action_by_user_id: int
    action_by_name: str
    action_by_role: str
    remarks: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# ADMIN SCHEMAS
# =========================================================

class UserRoleUpdate(BaseModel):
    role: Literal['student', 'faculty', 'admin']


class InventoryAdjustment(BaseModel):
    """Admin can adjust inventory for corrections."""
    total_quantity: Optional[int] = None
    available_quantity: Optional[int] = None
    reason: str = Field(min_length=1, max_length=2000)
    model_config = ConfigDict(str_strip_whitespace=True)


class UserCreate(UserRegister):
    role: Literal['student', 'faculty', 'admin'] = 'student'


class ResourceVerification(BaseModel):
    decision: Literal['Verified', 'Rejected']
    reason: str = Field(default='', max_length=2000)
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class Replenishment(BaseModel):
    quantity: int = Field(gt=0, le=100000)
    model_config = ConfigDict(extra='forbid')


class CustodianAssignment(BaseModel):
    custodian_id: int
    reason: str = Field(min_length=1, max_length=2000)
    model_config = ConfigDict(str_strip_whitespace=True)


class MFAVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
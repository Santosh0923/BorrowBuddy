from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    mfa_secret = Column(String(64), nullable=True)
    mfa_enabled = Column(Boolean, nullable=False, default=False)

    name = Column(String(100), nullable=False)

    email = Column(
        String(150), unique=True,
        nullable=False, index=True,
    )

    password_hash = Column(String(255), nullable=False)

    role = Column(
        String(20), nullable=False,
        default="student",
    )

    is_active = Column(
        Boolean, nullable=False, default=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    custodian_resources = relationship(
        "Resource",
        back_populates="custodian",
        foreign_keys="Resource.custodian_id",
    )

    borrow_requests = relationship(
        "BorrowRequest",
        back_populates="student",
        foreign_keys="BorrowRequest.student_id",
    )


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)

    category = Column(String(100), nullable=False)

    location = Column(String(150), nullable=False)

    description = Column(Text, nullable=True)
    verification_status = Column(String(30), nullable=False, default='Pending Verification')
    verification_reason = Column(Text)
    verified_by = Column(Integer, ForeignKey('users.id'))
    verified_at = Column(DateTime(timezone=True))

    total_quantity = Column(
        Integer, nullable=False, default=1,
    )

    available_quantity = Column(
        Integer, nullable=False, default=1,
    )

    status = Column(
        String(50), nullable=False,
        default="Available",
    )

    custodian_id = Column(
        Integer, ForeignKey("users.id"),
        nullable=True,
    )

    is_active = Column(
        Boolean, nullable=False, default=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    custodian = relationship(
        "User",
        back_populates="custodian_resources",
        foreign_keys=[custodian_id],
    )

    requests = relationship(
        "BorrowRequest",
        back_populates="resource",
    )


class BorrowRequest(Base):
    __tablename__ = "borrow_requests"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(
        Integer, ForeignKey("users.id"),
        nullable=False,
    )

    # Keep denormalized for easy display / backward compat
    student_name = Column(String(100), nullable=False)
    student_email = Column(String(150), nullable=False)

    resource_id = Column(
        Integer, ForeignKey("resources.id"),
        nullable=False,
    )

    quantity = Column(
        Integer, nullable=False, default=1,
    )

    purpose = Column(Text, nullable=True)

    return_date = Column(Date, nullable=False)

    status = Column(
        String(50), nullable=False,
        default="Requested",
    )

    # Approval / rejection
    approved_by = Column(
        Integer, ForeignKey("users.id"),
        nullable=True,
    )
    approved_at = Column(
        DateTime(timezone=True), nullable=True,
    )
    rejection_reason = Column(Text, nullable=True)

    # Custodian assignment (copied from resource at creation)
    custodian_id = Column(
        Integer, ForeignKey("users.id"),
        nullable=True,
    )

    # Workflow timestamps
    ready_at = Column(
        DateTime(timezone=True), nullable=True,
    )
    collected_at = Column(
        DateTime(timezone=True), nullable=True,
    )
    returned_at = Column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at = Column(
        DateTime(timezone=True), nullable=True,
    )

    # Return inspection
    inspection_condition = Column(
        String(50), nullable=True,
    )
    inspection_notes = Column(Text, nullable=True)
    inspected_by = Column(
        Integer, ForeignKey("users.id"),
        nullable=True,
    )
    inspection_date = Column(
        DateTime(timezone=True), nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    student = relationship(
        "User",
        back_populates="borrow_requests",
        foreign_keys=[student_id],
    )

    resource = relationship(
        "Resource",
        back_populates="requests",
    )

    approver = relationship(
        "User",
        foreign_keys=[approved_by],
    )

    custodian = relationship(
        "User",
        foreign_keys=[custodian_id],
    )

    inspector = relationship(
        "User",
        foreign_keys=[inspected_by],
    )

    history = relationship(
        "RequestHistory",
        back_populates="request",
        order_by="RequestHistory.created_at",
    )


class RequestHistory(Base):
    __tablename__ = "request_history"

    id = Column(Integer, primary_key=True, index=True)

    request_id = Column(
        Integer, ForeignKey("borrow_requests.id"),
        nullable=False,
    )

    old_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)

    action = Column(String(200), nullable=False)

    action_by_user_id = Column(
        Integer, ForeignKey("users.id"),
        nullable=False,
    )

    action_by_name = Column(
        String(100), nullable=False,
    )

    action_by_role = Column(
        String(20), nullable=False,
    )

    remarks = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    request = relationship(
        "BorrowRequest",
        back_populates="history",
    )

    actor = relationship(
        "User",
        foreign_keys=[action_by_user_id],
    )


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer)
    action = Column(String(200), nullable=False)
    actor_id = Column(Integer, ForeignKey('users.id'))
    actor_name = Column(String(100), nullable=False)
    actor_role = Column(String(20), nullable=False)
    details = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

import os
from datetime import date, datetime, timezone, timedelta
import json
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from fastapi.security import OAuth2PasswordRequestForm

from auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    require_faculty,
    require_student,
    require_faculty_or_admin,
    verify_password,
)

import models
import schemas
from domain import (TERMINAL, COMMITTED, valid_custodian, ensure_custody,
                    ensure_lendable, committed_units, ensure_user_reassignable,
                    resource_snapshot, audit)
from database import engine, get_db, get_write_db


# Create tables if they do not already exist
# Schema changes are applied explicitly through migrate.py, never at startup.


app = FastAPI(
    title="BorrowBuddy API",
    description="Cloud-Based Campus Resource Lending and Custody Management Platform",
    version="1.0.0",
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request, exc):
    return JSONResponse(status_code=409, content={'detail': 'This change conflicts with an existing record or inventory constraint. Refresh and check the values.'})


@app.get('/health', tags=['Home'])
def health(db: Session = Depends(get_db)):
    db.execute(text('SELECT is_active FROM users LIMIT 1'))
    version = db.execute(text('SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1')).scalar()
    return {'status': 'ok', 'database': 'connected', 'schema_version': version}


# ---------------------------------------------------
# CORS
# ---------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://borrow-buddy-chi.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================================================
# HELPER FUNCTIONS
# ===================================================

# Valid workflow transitions
WORKFLOW_TRANSITIONS = {
    "Requested": ["Approved", "Rejected", "Cancelled"],
    "Approved": ["Ready for Pickup", "Cancelled"],
    "Ready for Pickup": ["Collected", "Cancelled"],
    "Collected": ["Returned Pending Inspection"],
    "Returned Pending Inspection": [
        "Completed", "Maintenance Required",
    ],
    "Maintenance Required": ["Completed"],
    # Terminal states
    "Rejected": [],
    "Cancelled": [],
    "Completed": [],
}


def is_valid_transition(old_status, new_status):
    return new_status in WORKFLOW_TRANSITIONS.get(
        old_status, [],
    )


def update_resource_status(resource):
    if not resource.is_active:
        resource.status = 'Retired'
    elif resource.status != 'Maintenance':
        resource.status = 'Available' if resource.available_quantity > 0 else 'Out of Stock'


def create_history_record(
    db, request_id, old_status, new_status,
    action, user, remarks=None,
):
    """Create an audit trail entry for a request."""
    history = models.RequestHistory(
        request_id=request_id,
        old_status=old_status,
        new_status=new_status,
        action=action,
        action_by_user_id=user.id,
        action_by_name=user.name,
        action_by_role=user.role,
        remarks=remarks,
    )
    db.add(history)
    audit(db, user, 'request', request_id, action,
          {'old_status': old_status, 'new_status': new_status, 'remarks': remarks})
    return history


def enrich_request_response(req, db):
    """Build a BorrowRequestResponse with derived fields."""
    resource = (
        db.query(models.Resource)
        .filter(models.Resource.id == req.resource_id)
        .first()
    )

    approver = None
    if req.approved_by:
        approver = db.query(models.User).filter(
            models.User.id == req.approved_by,
        ).first()

    custodian = None
    if req.custodian_id:
        custodian = db.query(models.User).filter(
            models.User.id == req.custodian_id,
        ).first()

    inspector = None
    if req.inspected_by:
        inspector = db.query(models.User).filter(
            models.User.id == req.inspected_by,
        ).first()

    today = date.today()
    active_statuses = {
        "Collected",
    }
    is_overdue = (
        req.return_date < today
        and req.status in active_statuses
    )
    is_due_soon = (
        not is_overdue
        and req.status in active_statuses
        and req.return_date <= today + timedelta(days=2)
    )

    return schemas.BorrowRequestResponse(
        id=req.id,
        student_id=req.student_id,
        student_name=req.student_name,
        student_email=req.student_email,
        resource_id=req.resource_id,
        resource_name=resource.name if resource else None,
        quantity=req.quantity,
        purpose=req.purpose,
        return_date=req.return_date,
        status=req.status,
        approved_by=req.approved_by,
        approver_name=(
            approver.name if approver else None
        ),
        approved_at=req.approved_at,
        rejection_reason=req.rejection_reason,
        custodian_id=req.custodian_id,
        custodian_name=(
            custodian.name if custodian else None
        ),
        ready_at=req.ready_at,
        collected_at=req.collected_at,
        returned_at=req.returned_at,
        completed_at=req.completed_at,
        inspection_condition=req.inspection_condition,
        inspection_notes=req.inspection_notes,
        inspected_by=req.inspected_by,
        inspector_name=(
            inspector.name if inspector else None
        ),
        inspection_date=req.inspection_date,
        is_due_soon=is_due_soon,
        is_overdue=is_overdue,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


def enrich_resource_response(resource):
    """Build a ResourceResponse with custodian name."""
    counts = {status: sum(r.quantity for r in resource.requests if r.status == status) for status in COMMITTED}
    committed = sum(counts.values())
    return schemas.ResourceResponse(
        id=resource.id,
        name=resource.name,
        category=resource.category,
        location=resource.location,
        description=resource.description,
        total_quantity=resource.total_quantity,
        available_quantity=resource.available_quantity,
        verification_status=resource.verification_status,
        verification_reason=resource.verification_reason,
        verified_by=resource.verified_by,
        verified_at=resource.verified_at,
        reserved_quantity=counts['Approved'] + counts['Ready for Pickup'],
        issued_quantity=counts['Collected'],
        inspection_quantity=counts['Returned Pending Inspection'],
        maintenance_quantity=counts['Maintenance Required'],
        unavailable_quantity=max(0, resource.total_quantity-resource.available_quantity-committed),
        status=resource.status,
        custodian_id=resource.custodian_id,
        custodian_name=(
            resource.custodian.name
            if resource.custodian else None
        ),
        is_active=resource.is_active,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


# ===================================================
# HOME
# ===================================================

@app.get("/", tags=["Home"])
def home():
    return {
        "application": "BorrowBuddy",
        "message": "BorrowBuddy API is running",
        "documentation": "/docs",
    }


# ===================================================
# AUTHENTICATION APIs
# ===================================================

@app.post(
    "/auth/register",
    response_model=schemas.UserResponse,
    tags=["Authentication"],
)
def register(
    user: schemas.UserRegister,
    db: Session = Depends(get_write_db),
):
    existing_user = (
        db.query(models.User)
        .filter(
            models.User.email
            == user.email.strip().lower(),
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email is already registered",
        )

    new_user = models.User(
        name=user.name.strip(),
        email=user.email.strip().lower(),
        password_hash=hash_password(user.password),
        role="student",
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user



@app.post(
    "/auth/login",
    response_model=schemas.TokenResponse,
    tags=["Authentication"],
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_write_db),
):
    email = form_data.username.strip().lower()

    user = (
        db.query(models.User)
        .filter(models.User.email == email)
        .first()
    )

    if (
        user is None
        or not verify_password(
            form_data.password, user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is deactivated",
        )

    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "name": user.name,
        "user_id": user.id,
    }



@app.get(
    "/auth/me",
    response_model=schemas.UserResponse,
    tags=["Authentication"],
)
def get_me(
    current_user: models.User = Depends(
        get_current_user,
    ),
):
    return current_user


# ===================================================
# RESOURCE APIs
# ===================================================

@app.post(
    "/resources",
    response_model=schemas.ResourceResponse,
    tags=["Resources"],
)
def create_resource(resource: schemas.ResourceCreate, db: Session = Depends(get_write_db),
                    current_user: models.User = Depends(require_faculty)):
    created = models.Resource(name=resource.name, category=resource.category,
        location=resource.location, description=resource.description,
        total_quantity=resource.quantity, available_quantity=resource.quantity,
        custodian_id=current_user.id, status='Available', verification_status='Pending Verification')
    db.add(created)
    db.flush()
    audit(db, current_user, 'resource', created.id, 'Faculty submitted resource', resource_snapshot(created))
    db.commit()
    db.refresh(created)
    return enrich_resource_response(created)



@app.get(
    "/resources",
    response_model=list[schemas.ResourceResponse],
    tags=["Resources"],
)
def get_resources(
    current_user: models.User = Depends(get_current_user),
    include_retired: bool = Query(False),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    custodian_id: Optional[int] = Query(None),
    verification_status: Optional[str] = Query(None),
    available_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    query = db.query(models.Resource).options(
        joinedload(models.Resource.custodian),
    )

    # By default, show only active resources
    if current_user.role == 'student':
        query = query.filter(models.Resource.verification_status == 'Verified')
    elif current_user.role == 'faculty':
        query = query.filter(models.Resource.custodian_id == current_user.id)
    if not include_retired or current_user.role == 'student':
        query = query.filter(models.Resource.is_active == True)

    if search:
        query = query.filter(
            or_(
                models.Resource.name.ilike(f"%{search}%"),
                models.Resource.category.ilike(f"%{search}%"),
                models.Resource.location.ilike(f"%{search}%"),
                models.Resource.description.ilike(f"%{search}%"),
            )
        )

    if category:
        query = query.filter(
            func.lower(models.Resource.category)
            == category.strip().lower(),
        )

    if location:
        query = query.filter(
            func.lower(models.Resource.location)
            == location.strip().lower(),
        )

    if status:
        query = query.filter(
            models.Resource.status == status,
        )

    if custodian_id:
        query = query.filter(
            models.Resource.custodian_id == custodian_id,
        )

    if verification_status:
        query = query.filter(models.Resource.verification_status == verification_status)

    if available_only:
        query = query.filter(
            models.Resource.available_quantity > 0,
            models.Resource.status == 'Available',
        )

    resources = query.all()
    return [enrich_resource_response(r) for r in resources]


@app.get(
    "/resources/{resource_id}",
    response_model=schemas.ResourceResponse,
    tags=["Resources"],
)
def get_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resource = (
        db.query(models.Resource)
        .options(joinedload(models.Resource.custodian))
        .filter(models.Resource.id == resource_id)
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    if current_user.role == 'student' and (not resource.is_active or resource.verification_status != 'Verified'):
        raise HTTPException(403, 'Only verified, active resources are available to students')
    if current_user.role == 'faculty' and resource.custodian_id != current_user.id:
        raise HTTPException(403, 'You can only view your own resources')
    return enrich_resource_response(resource)



@app.patch(
    "/resources/{resource_id}",
    response_model=schemas.ResourceResponse,
    tags=["Resources"],
)
def update_resource(resource_id: int, resource_update: schemas.ResourceUpdate,
                    db: Session = Depends(get_write_db), current_user: models.User = Depends(require_faculty_or_admin)):
    resource = db.get(models.Resource, resource_id)
    if resource is None:
        raise HTTPException(404, 'Resource not found')
    if current_user.role == 'faculty' and resource.custodian_id != current_user.id:
        raise HTTPException(403, 'You can only manage your own resources')
    before = resource_snapshot(resource)
    changes = resource_update.model_dump(exclude_unset=True)
    if current_user.role == 'faculty' and any(k not in ('name','category','location','description') for k in changes):
        raise HTTPException(403, 'Faculty may edit listing details; governance fields are Admin only')
    for key in ('name', 'category', 'location'):
        if key in changes:
            if not changes[key] or not changes[key].strip() or len(changes[key].strip()) > (150 if key == 'location' else 100):
                raise HTTPException(422, f'Valid {key} is required')
            changes[key] = changes[key].strip()
    # Form controls submit an empty string for a legacy NULL description.
    # Compare meaningful listing values before invalidating a review, and
    # preserve the original values when an unchanged form is submitted.
    listing_fields = ('name', 'category', 'location', 'description')
    for key in listing_fields:
        if key in changes and (changes[key] or '').strip() == (getattr(resource, key) or '').strip():
            changes.pop(key)
    if any(key in changes for key in listing_fields):
        resource.verification_status = 'Pending Verification'
        resource.verification_reason = None
        resource.verified_by = None
        resource.verified_at = None
    if any(key in changes and changes[key] is None for key in ('status', 'is_active')):
        raise HTTPException(422, 'Status and active flag cannot be null')
    if changes.get('custodian_id') is not None:
        valid_custodian(db, changes['custodian_id'])
    if 'custodian_id' in changes and changes['custodian_id'] != resource.custodian_id:
        pending = db.query(models.BorrowRequest).filter(models.BorrowRequest.resource_id == resource_id,
                    models.BorrowRequest.status.notin_(TERMINAL)).all()
        if pending and changes['custodian_id'] is None:
            raise HTTPException(409, 'Assign an active Faculty owner while requests remain open')
        for request in pending:
            request.custodian_id = changes['custodian_id']
            create_history_record(db, request.id, request.status, request.status,
                'Faculty ownership transferred', current_user,
                remarks=f"Faculty owner changed to user #{changes['custodian_id']}")
    if changes.get('status') == 'Retired':
        changes['is_active'] = False
    if changes.get('is_active') is False:
        if db.query(models.BorrowRequest).filter(models.BorrowRequest.resource_id == resource_id,
                  models.BorrowRequest.status.notin_(TERMINAL)).first():
            raise HTTPException(409, 'Finish or cancel open requests before retiring this resource')
    for key, value in changes.items():
        setattr(resource, key, value)
    update_resource_status(resource)
    audit(db, current_user, 'resource', resource.id, 'Resource updated', {'before':before,'after':resource_snapshot(resource)})
    db.commit()
    db.refresh(resource)
    return enrich_resource_response(resource)




@app.patch(
    "/resources/{resource_id}/adjust",
    response_model=schemas.ResourceResponse,
    tags=["Resources"],
)
def adjust_inventory(resource_id: int, adjustment: schemas.InventoryAdjustment,
                     db: Session = Depends(get_write_db), current_user: models.User = Depends(require_admin)):
    resource = db.get(models.Resource, resource_id)
    if resource is None:
        raise HTTPException(404, 'Resource not found')
    before = resource_snapshot(resource)
    total = adjustment.total_quantity if adjustment.total_quantity is not None else resource.total_quantity
    available = adjustment.available_quantity if adjustment.available_quantity is not None else resource.available_quantity
    committed = committed_units(db, resource_id)
    if total < 0 or available < 0 or available + committed > total:
        raise HTTPException(409, f'Available units plus {committed} reserved/issued/inspection/maintenance units must not exceed total')
    resource.total_quantity, resource.available_quantity = total, available
    update_resource_status(resource)
    audit(db, current_user, 'resource', resource.id, 'Inventory adjusted',
          {'before':before,'after':resource_snapshot(resource),'reason':adjustment.reason})
    db.commit()
    db.refresh(resource)
    return enrich_resource_response(resource)



@app.delete(
    "/resources/{resource_id}",
    tags=["Resources"],
)
def delete_resource(resource_id: int, db: Session = Depends(get_write_db),
                    current_user: models.User = Depends(require_admin)):
    update_resource(resource_id, schemas.ResourceUpdate(is_active=False), db, current_user)
    return {'message':'Resource retired. Inventory and request history have been preserved.'}



# ===================================================
# BORROW REQUEST APIs
# ===================================================

@app.post(
    "/requests",
    response_model=schemas.BorrowRequestResponse,
    tags=["Borrow Requests"],
)
def create_request(
    request: schemas.BorrowRequestCreate,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "student":
        raise HTTPException(
            status_code=403,
            detail="Only students can create borrow requests",
        )

    resource = (
        db.query(models.Resource)
        .filter(models.Resource.id == request.resource_id)
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    ensure_lendable(db, resource)

    if not resource.is_active:
        raise HTTPException(
            status_code=400,
            detail="Resource is no longer active",
        )

    if request.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than zero",
        )

    if request.quantity > resource.available_quantity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Only {resource.available_quantity} "
                f"item(s) are available"
            ),
        )

    if request.return_date < date.today():
        raise HTTPException(
            status_code=400,
            detail="Return date cannot be in the past",
        )

    new_request = models.BorrowRequest(
        student_id=current_user.id,
        student_name=current_user.name,
        student_email=current_user.email,
        resource_id=request.resource_id,
        quantity=request.quantity,
        purpose=request.purpose,
        return_date=request.return_date,
        status="Requested",
        custodian_id=resource.custodian_id,
    )

    db.add(new_request)
    db.flush()

    create_history_record(
        db, new_request.id,
        None, "Requested",
        "Student submitted borrow request",
        current_user,
        remarks=request.purpose,
    )

    db.commit()
    db.refresh(new_request)

    return enrich_request_response(new_request, db)



@app.get(
    "/requests",
    response_model=list[schemas.BorrowRequestResponse],
    tags=["Borrow Requests"],
)
def get_requests(
    status: Optional[str] = Query(None),
    resource_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        get_current_user,
    ),
):
    query = db.query(models.BorrowRequest)

    # Role-based filtering
    if current_user.role == "student":
        query = query.filter(
            models.BorrowRequest.student_id
            == current_user.id,
        )
    elif current_user.role == "faculty":
        query = query.filter(
            models.BorrowRequest.custodian_id
            == current_user.id,
        )
    # admin sees all

    if status:
        query = query.filter(
            models.BorrowRequest.status == status,
        )

    if resource_id:
        query = query.filter(
            models.BorrowRequest.resource_id == resource_id,
        )

    if search:
        query = query.filter(
            or_(
                models.BorrowRequest.student_name.ilike(
                    f"%{search}%",
                ),
                models.BorrowRequest.student_email.ilike(
                    f"%{search}%",
                ),
            ),
        )

    query = query.order_by(
        models.BorrowRequest.created_at.desc(),
    )

    requests = query.all()
    return [
        enrich_request_response(r, db)
        for r in requests
    ]


@app.get(
    "/requests/{request_id}",
    response_model=schemas.BorrowRequestResponse,
    tags=["Borrow Requests"],
)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    # Access control
    if current_user.role == "student":
        if borrow_request.student_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Access denied",
            )
    elif current_user.role == "faculty":
        if borrow_request.custodian_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Access denied",
            )

    return enrich_request_response(borrow_request, db)


# ---------------------------------------------------
# WORKFLOW ACTION ENDPOINTS
# ---------------------------------------------------

@app.post(
    "/requests/{request_id}/approve",
    response_model=schemas.BorrowRequestResponse,
    tags=["Workflow"],
)
def approve_request(
    request_id: int,
    action: schemas.ApprovalAction = None,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(
        require_faculty_or_admin,
    ),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    ensure_custody(current_user, borrow_request)

    # Faculty can only approve requests for their resources
    if (
        current_user.role == "faculty"
        and borrow_request.custodian_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only manage requests for your assigned resources",
        )

    if not is_valid_transition(
        borrow_request.status, "Approved",
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot approve from status: "
                f"{borrow_request.status}"
            ),
        )

    resource = (
        db.query(models.Resource)
        .filter(
            models.Resource.id
            == borrow_request.resource_id,
        )
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Associated resource not found",
        )

    ensure_lendable(db, resource)
    if borrow_request.return_date < date.today():
        raise HTTPException(409, 'Return date has passed; ask the student to submit a new request')

    if borrow_request.quantity > resource.available_quantity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Only {resource.available_quantity} "
                f"item(s) are currently available"
            ),
        )

    # Reserve inventory
    resource.available_quantity -= borrow_request.quantity
    update_resource_status(resource)

    old_status = borrow_request.status
    now = datetime.now(timezone.utc)
    borrow_request.status = "Approved"
    borrow_request.approved_by = current_user.id
    borrow_request.approved_at = now

    remarks = action.remarks if action else None
    create_history_record(
        db, request_id, old_status, "Approved",
        f"{current_user.name} approved request",
        current_user, remarks=remarks,
    )

    db.commit()
    db.refresh(borrow_request)

    return enrich_request_response(borrow_request, db)



@app.post(
    "/requests/{request_id}/reject",
    response_model=schemas.BorrowRequestResponse,
    tags=["Workflow"],
)
def reject_request(
    request_id: int,
    action: schemas.RejectionAction,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(
        require_faculty_or_admin,
    ),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    ensure_custody(current_user, borrow_request)

    if (
        current_user.role == "faculty"
        and borrow_request.custodian_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only manage requests for your assigned resources",
        )

    if not is_valid_transition(
        borrow_request.status, "Rejected",
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot reject from status: "
                f"{borrow_request.status}"
            ),
        )

    old_status = borrow_request.status
    borrow_request.status = "Rejected"
    reason = action.rejection_reason if action else None
    borrow_request.rejection_reason = reason

    create_history_record(
        db, request_id, old_status, "Rejected",
        f"{current_user.name} rejected request",
        current_user, remarks=reason,
    )

    db.commit()
    db.refresh(borrow_request)

    return enrich_request_response(borrow_request, db)



@app.post(
    "/requests/{request_id}/ready",
    response_model=schemas.BorrowRequestResponse,
    tags=["Workflow"],
)
def mark_ready_for_pickup(
    request_id: int,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(
        require_faculty_or_admin,
    ),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    ensure_custody(current_user, borrow_request)

    if (
        current_user.role == "faculty"
        and borrow_request.custodian_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only manage requests for your assigned resources",
        )

    if not is_valid_transition(
        borrow_request.status, "Ready for Pickup",
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot mark ready from status: "
                f"{borrow_request.status}"
            ),
        )

    old_status = borrow_request.status
    borrow_request.status = "Ready for Pickup"
    borrow_request.ready_at = datetime.now(timezone.utc)

    create_history_record(
        db, request_id, old_status, "Ready for Pickup",
        f"{current_user.name} marked item ready for pickup",
        current_user,
    )

    db.commit()
    db.refresh(borrow_request)

    return enrich_request_response(borrow_request, db)



@app.post(
    "/requests/{request_id}/collect",
    response_model=schemas.BorrowRequestResponse,
    tags=["Workflow"],
)
def confirm_collection(
    request_id: int,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(
        require_faculty_or_admin,
    ),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    ensure_custody(current_user, borrow_request)

    if (
        current_user.role == "faculty"
        and borrow_request.custodian_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only manage requests for your assigned resources",
        )

    if not is_valid_transition(
        borrow_request.status, "Collected",
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot mark collected from status: "
                f"{borrow_request.status}"
            ),
        )

    old_status = borrow_request.status
    borrow_request.status = "Collected"
    borrow_request.collected_at = datetime.now(timezone.utc)

    create_history_record(
        db, request_id, old_status, "Collected",
        f"{current_user.name} confirmed handover",
        current_user,
    )

    db.commit()
    db.refresh(borrow_request)

    return enrich_request_response(borrow_request, db)



@app.post(
    "/requests/{request_id}/return",
    response_model=schemas.BorrowRequestResponse,
    tags=["Workflow"],
)
def receive_return(
    request_id: int,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(
        require_faculty_or_admin,
    ),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    ensure_custody(current_user, borrow_request)

    if (
        current_user.role == "faculty"
        and borrow_request.custodian_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only manage requests for your assigned resources",
        )

    new_status = "Returned Pending Inspection"
    if not is_valid_transition(
        borrow_request.status, new_status,
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot receive return from status: "
                f"{borrow_request.status}"
            ),
        )

    old_status = borrow_request.status
    borrow_request.status = new_status
    borrow_request.returned_at = datetime.now(timezone.utc)

    create_history_record(
        db, request_id, old_status, new_status,
        f"{current_user.name} received returned item",
        current_user,
    )

    db.commit()
    db.refresh(borrow_request)

    return enrich_request_response(borrow_request, db)



@app.post(
    "/requests/{request_id}/inspect",
    response_model=schemas.BorrowRequestResponse,
    tags=["Workflow"],
)
def inspect_return(
    request_id: int,
    action: schemas.InspectionAction,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(
        require_faculty_or_admin,
    ),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    ensure_custody(current_user, borrow_request)

    if (
        current_user.role == "faculty"
        and borrow_request.custodian_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only manage requests for your assigned resources",
        )

    if borrow_request.status != 'Returned Pending Inspection':
        raise HTTPException(409, 'Receive the physical return before inspection')

    valid_conditions = {
        "Good", "Minor Damage",
        "Major Damage", "Missing Components",
    }
    if action.condition not in valid_conditions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid condition. Must be one of: "
                f"{', '.join(valid_conditions)}"
            ),
        )

    old_status = borrow_request.status

    # Determine new status based on condition
    if action.condition == "Good":
        new_status = "Completed"
    else:
        new_status = "Maintenance Required"

    if not is_valid_transition(old_status, new_status):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot inspect from status: "
                f"{old_status}"
            ),
        )

    now = datetime.now(timezone.utc)
    borrow_request.status = new_status
    borrow_request.inspection_condition = action.condition
    borrow_request.inspection_notes = action.notes
    borrow_request.inspected_by = current_user.id
    borrow_request.inspection_date = now

    resource = (
        db.query(models.Resource)
        .filter(
            models.Resource.id
            == borrow_request.resource_id,
        )
        .first()
    )

    if new_status == "Completed":
        borrow_request.completed_at = now
        # Restore inventory for good condition
        if resource:
            resource.available_quantity += borrow_request.quantity
            update_resource_status(resource)
    else:
        # Maintenance Required — do NOT restore inventory
        pass

    create_history_record(
        db, request_id, old_status, new_status,
        (
            f"{current_user.name} inspected return — "
            f"Condition: {action.condition}"
        ),
        current_user,
        remarks=action.notes,
    )

    db.commit()
    db.refresh(borrow_request)

    return enrich_request_response(borrow_request, db)



@app.post(
    "/requests/{request_id}/complete-maintenance",
    response_model=schemas.BorrowRequestResponse,
    tags=["Workflow"],
)
def complete_maintenance(
    request_id: int,
    action: schemas.MaintenanceCompleteAction = None,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(
        require_faculty_or_admin,
    ),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    ensure_custody(current_user, borrow_request)

    if borrow_request.status != 'Maintenance Required':
        raise HTTPException(409, 'Only maintenance requests can complete maintenance')

    if not is_valid_transition(
        borrow_request.status, "Completed",
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot complete from status: "
                f"{borrow_request.status}"
            ),
        )

    old_status = borrow_request.status
    now = datetime.now(timezone.utc)
    borrow_request.status = "Completed"
    borrow_request.completed_at = now

    resource = (
        db.query(models.Resource)
        .filter(
            models.Resource.id
            == borrow_request.resource_id,
        )
        .first()
    )

    restore = True
    if action and not action.restore_quantity:
        restore = False

    if restore and resource:
        resource.available_quantity += borrow_request.quantity
        update_resource_status(resource)

    if not restore and resource:
        resource.total_quantity -= borrow_request.quantity
        update_resource_status(resource)
    notes = action.notes if action else None
    create_history_record(
        db, request_id, old_status, "Completed",
        (
            f"{current_user.name} completed maintenance"
            + (
                " — inventory restored"
                if restore else " — inventory NOT restored"
            )
        ),
        current_user, remarks=notes,
    )

    db.commit()
    db.refresh(borrow_request)

    return enrich_request_response(borrow_request, db)



@app.patch(
    "/requests/{request_id}/cancel",
    response_model=schemas.BorrowRequestResponse,
    tags=["Workflow"],
)
def cancel_request(
    request_id: int,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(
        get_current_user,
    ),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    if current_user.role == 'faculty':
        ensure_custody(current_user, borrow_request)

    # Students can only cancel their own Requested requests
    if current_user.role == "student":
        if borrow_request.student_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You cannot cancel another student's request",
            )
        if borrow_request.status != "Requested":
            raise HTTPException(
                status_code=400,
                detail="You can only cancel requests in 'Requested' status",
            )

    # Faculty/admin can cancel broader range
    if not is_valid_transition(
        borrow_request.status, "Cancelled",
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot cancel from status: "
                f"{borrow_request.status}"
            ),
        )

    old_status = borrow_request.status

    # Restore inventory if it was already reserved
    if old_status in ("Approved", "Ready for Pickup"):
        resource = (
            db.query(models.Resource)
            .filter(
                models.Resource.id
                == borrow_request.resource_id,
            )
            .first()
        )
        if resource:
            resource.available_quantity += borrow_request.quantity
            update_resource_status(resource)

    borrow_request.status = "Cancelled"

    create_history_record(
        db, request_id, old_status, "Cancelled",
        f"{current_user.name} cancelled request",
        current_user,
    )

    db.commit()
    db.refresh(borrow_request)

    return enrich_request_response(borrow_request, db)



@app.get(
    "/requests/{request_id}/history",
    response_model=list[schemas.RequestHistoryResponse],
    tags=["Audit Trail"],
)
def get_request_history(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        get_current_user,
    ),
):
    borrow_request = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.id == request_id)
        .first()
    )

    if borrow_request is None:
        raise HTTPException(
            status_code=404,
            detail="Borrow request not found",
        )

    # Access control
    if current_user.role == "student":
        if borrow_request.student_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Access denied",
            )
    elif current_user.role == "faculty":
        if borrow_request.custodian_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Access denied",
            )

    history = (
        db.query(models.RequestHistory)
        .filter(
            models.RequestHistory.request_id == request_id,
        )
        .order_by(models.RequestHistory.created_at.asc())
        .all()
    )

    return history


@app.delete(
    "/requests/{request_id}",
    tags=["Borrow Requests"],
)
def delete_request(request_id: int, db: Session = Depends(get_write_db),
                   current_user: models.User = Depends(require_admin)):
    raise HTTPException(409, 'Requests and audit history cannot be deleted. Cancel an eligible request instead.')



# ===================================================
# DASHBOARD APIs
# ===================================================

@app.get(
    "/dashboard/admin",
    tags=["Dashboard"],
)
def get_admin_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    today = date.today()

    total_resource_types = (
        db.query(models.Resource)
        .filter(models.Resource.is_active == True)
        .count()
    )

    total_inventory = (
        db.query(func.coalesce(
            func.sum(models.Resource.total_quantity), 0,
        ))
        .filter(models.Resource.is_active == True)
        .scalar()
    )

    available_units = (
        db.query(func.coalesce(
            func.sum(models.Resource.available_quantity), 0,
        ))
        .filter(models.Resource.is_active == True)
        .scalar()
    )

    in_use = db.query(func.coalesce(func.sum(models.BorrowRequest.quantity), 0)).filter(
        models.BorrowRequest.status == 'Collected').scalar()

    out_of_stock = (
        db.query(models.Resource)
        .filter(
            models.Resource.is_active == True,
            models.Resource.available_quantity == 0,
        )
        .count()
    )

    maintenance_resources = (
        db.query(models.Resource)
        .filter(models.Resource.status == "Maintenance")
        .count()
    )

    pending_requests = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.status == "Requested")
        .count()
    )

    approved_requests = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.status == "Approved")
        .count()
    )

    collected = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.status == "Collected")
        .count()
    )

    overdue = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.status.in_(
                ["Collected"],
            ),
            models.BorrowRequest.return_date < today,
        )
        .count()
    )

    maintenance_requests = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.status == "Maintenance Required",
        )
        .count()
    )

    completed = (
        db.query(models.BorrowRequest)
        .filter(models.BorrowRequest.status == "Completed")
        .count()
    )

    return {
        "total_resource_types": total_resource_types,
        "total_inventory": total_inventory,
        "available_units": available_units,
        "in_use": in_use,
        "out_of_stock": out_of_stock,
        "maintenance_resources": maintenance_resources,
        "pending_requests": pending_requests,
        "approved_requests": approved_requests,
        "collected": collected,
        "overdue": overdue,
        "maintenance_requests": maintenance_requests,
        "completed": completed,
    }


@app.get(
    "/dashboard/faculty",
    tags=["Dashboard"],
)
def get_faculty_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_faculty,
    ),
):
    today = date.today()
    cid = current_user.id

    pending_approval = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.custodian_id == cid,
            models.BorrowRequest.status == "Requested",
        )
        .count()
    )

    ready_for_pickup = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.custodian_id == cid,
            models.BorrowRequest.status == "Ready for Pickup",
        )
        .count()
    )

    currently_issued = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.custodian_id == cid,
            models.BorrowRequest.status == "Collected",
        )
        .count()
    )

    pending_inspection = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.custodian_id == cid,
            models.BorrowRequest.status
            == "Returned Pending Inspection",
        )
        .count()
    )

    maintenance = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.custodian_id == cid,
            models.BorrowRequest.status
            == "Maintenance Required",
        )
        .count()
    )

    overdue = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.custodian_id == cid,
            models.BorrowRequest.status.in_(
                ["Collected"],
            ),
            models.BorrowRequest.return_date < today,
        )
        .count()
    )

    return {
        "pending_approval": pending_approval,
        "ready_for_pickup": ready_for_pickup,
        "currently_issued": currently_issued,
        "pending_inspection": pending_inspection,
        "maintenance": maintenance,
        "overdue": overdue,
    }



@app.get(
    "/dashboard/student",
    tags=["Dashboard"],
)
def get_student_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_student,
    ),
):
    today = date.today()
    sid = current_user.id

    active = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.student_id == sid,
            models.BorrowRequest.status.in_(
                [
                    "Requested", "Approved",
                    "Ready for Pickup", "Collected",
                    "Returned Pending Inspection", "Maintenance Required",
                ],
            ),
        )
        .count()
    )

    approved_ready = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.student_id == sid,
            models.BorrowRequest.status.in_(
                ["Approved", "Ready for Pickup"],
            ),
        )
        .count()
    )

    currently_borrowed = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.student_id == sid,
            models.BorrowRequest.status == "Collected",
        )
        .count()
    )

    due_soon = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.student_id == sid,
            models.BorrowRequest.status.in_(
                ["Collected"],
            ),
            models.BorrowRequest.return_date >= today,
            models.BorrowRequest.return_date
            <= today + timedelta(days=2),
        )
        .count()
    )

    overdue = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.student_id == sid,
            models.BorrowRequest.status.in_(
                ["Collected"],
            ),
            models.BorrowRequest.return_date < today,
        )
        .count()
    )

    completed = (
        db.query(models.BorrowRequest)
        .filter(
            models.BorrowRequest.student_id == sid,
            models.BorrowRequest.status == "Completed",
        )
        .count()
    )

    return {
        "active_requests": active,
        "approved_ready": approved_ready,
        "currently_borrowed": currently_borrowed,
        "due_soon": due_soon,
        "overdue": overdue,
        "completed": completed,
    }



# ===================================================
# ADMIN USER MANAGEMENT APIs
# ===================================================

@app.get(
    "/admin/users",
    response_model=list[schemas.UserResponse],
    tags=["Admin"],
)
def get_all_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    return db.query(models.User).order_by(
        models.User.created_at.desc(),
    ).all()


@app.get(
    "/admin/users/faculty",
    response_model=list[schemas.UserResponse],
    tags=["Admin"],
)
def get_faculty_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Get all faculty users — accessible by any authenticated user
    (needed for custodian dropdowns)."""
    return (
        db.query(models.User)
        .filter(
            models.User.role.in_(["faculty"]),
            models.User.is_active == True,
        )
        .order_by(models.User.name)
        .all()
    )



@app.patch(
    "/admin/users/{user_id}/role",
    response_model=schemas.UserResponse,
    tags=["Admin"],
)
def update_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(require_admin),
):
    if role_update.role not in ("student", "faculty", "admin"):
        raise HTTPException(
            status_code=400,
            detail="Invalid role. Must be student, faculty, or admin",
        )

    user = (
        db.query(models.User)
        .filter(models.User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot change your own role",
        )

    ensure_user_reassignable(db, user)
    before = {"role":user.role,"is_active":user.is_active}
    user.role = role_update.role
    audit(db, current_user, 'user', user.id, 'User updated', {'before':before,'after':{'role':user.role,'is_active':user.is_active}})
    db.commit()
    db.refresh(user)

    return user



@app.patch(
    "/admin/users/{user_id}/toggle-active",
    response_model=schemas.UserResponse,
    tags=["Admin"],
)
def toggle_user_active(
    user_id: int,
    db: Session = Depends(get_write_db),
    current_user: models.User = Depends(require_admin),
):
    user = (
        db.query(models.User)
        .filter(models.User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate your own account",
        )

    if user.is_active:
        ensure_user_reassignable(db, user)
    before = {"role":user.role,"is_active":user.is_active}
    user.is_active = not user.is_active
    audit(db, current_user, 'user', user.id, 'User updated', {'before':before,'after':{'role':user.role,'is_active':user.is_active}})
    db.commit()
    db.refresh(user)

    return user


@app.post('/admin/users', response_model=schemas.UserResponse, tags=['Admin'])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_write_db),
                current_user: models.User = Depends(require_admin)):
    if db.query(models.User).filter(func.lower(models.User.email) == user.email).first():
        raise HTTPException(409, 'Email is already registered')
    created = models.User(name=user.name, email=user.email, role=user.role,
                          password_hash=hash_password(user.password))
    db.add(created)
    db.flush()
    audit(db, current_user, 'user', created.id, 'User created', {'name':user.name,'role':user.role})
    db.commit()
    db.refresh(created)
    return created


@app.patch('/requests/{request_id}/custodian', response_model=schemas.BorrowRequestResponse, tags=['Admin'])
def assign_request_custodian(request_id: int, assignment: schemas.CustodianAssignment,
                             db: Session = Depends(get_write_db), current_user: models.User = Depends(require_admin)):
    request = db.get(models.BorrowRequest, request_id)
    if request is None:
        raise HTTPException(404, 'Request not found')
    if request.status in TERMINAL:
        raise HTTPException(409, 'Completed, rejected and cancelled requests retain their historical custodian')
    resource = db.get(models.Resource, request.resource_id)
    if assignment.custodian_id != resource.custodian_id:
        raise HTTPException(409, 'Change Faculty ownership on the resource to transfer all open requests')
    custodian = valid_custodian(db, assignment.custodian_id)
    old = request.custodian_id
    request.custodian_id = custodian.id
    create_history_record(db, request.id, request.status, request.status, 'Request Faculty owner synchronized', current_user,
                          remarks=f'{old or "Unassigned"} → {custodian.name}. {assignment.reason}')
    db.commit()
    db.refresh(request)
    return enrich_request_response(request, db)


@app.get('/admin/audit', tags=['Audit Trail'])
def get_audit(entity_type: Optional[str] = None, offset: int = Query(0, ge=0),
               limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db),
               current_user: models.User = Depends(require_admin)):
    query = db.query(models.AuditEvent)
    if entity_type:
        query = query.filter(models.AuditEvent.entity_type == entity_type)
    total = query.count()
    rows = query.order_by(models.AuditEvent.id.desc()).offset(offset).limit(limit).all()
    return {'total':total, 'items':[{'id':r.id,'entity_type':r.entity_type,'entity_id':r.entity_id,
        'action':r.action,'actor_id':r.actor_id,'actor_name':r.actor_name,'actor_role':r.actor_role,
        'details':json.loads(r.details),'created_at':r.created_at} for r in rows]}


@app.post('/resources/{resource_id}/verify', response_model=schemas.ResourceResponse, tags=['Resource Verification'])
def verify_resource(resource_id: int, action: schemas.ResourceVerification,
                    db: Session = Depends(get_write_db), current_user: models.User = Depends(require_admin)):
    resource = db.get(models.Resource, resource_id)
    if resource is None:
        raise HTTPException(404, 'Resource not found')
    if resource.verification_status != 'Pending Verification':
        raise HTTPException(409, 'Only pending listings can be reviewed')
    if not resource.is_active:
        raise HTTPException(409, 'Reactivate this listing before verification')
    if action.decision == 'Rejected' and not action.reason:
        raise HTTPException(422, 'A rejection reason is required')
    if action.decision == 'Verified':
        valid_custodian(db, resource.custodian_id)
    before = resource_snapshot(resource)
    resource.verification_status = action.decision
    resource.verification_reason = action.reason or None
    resource.verified_by = current_user.id
    resource.verified_at = datetime.now(timezone.utc)
    audit(db, current_user, 'resource', resource.id, 'Resource listing '+action.decision.lower(),
          {'before':before, 'after':resource_snapshot(resource),'reason':action.reason})
    db.commit()
    db.refresh(resource)
    return enrich_resource_response(resource)


@app.post('/resources/{resource_id}/replenish', response_model=schemas.ResourceResponse, tags=['Resources'])
def replenish_resource(resource_id: int, action: schemas.Replenishment,
                       db: Session = Depends(get_write_db), current_user: models.User = Depends(require_faculty)):
    resource = db.get(models.Resource, resource_id)
    if resource is None:
        raise HTTPException(404, 'Resource not found')
    if resource.custodian_id != current_user.id:
        raise HTTPException(403, 'You can only replenish your own resources')
    if not resource.is_active:
        raise HTTPException(409, 'Ask an Admin to reactivate this resource first')
    before = resource_snapshot(resource)
    resource.total_quantity += action.quantity
    resource.available_quantity += action.quantity
    update_resource_status(resource)
    audit(db, current_user, 'resource', resource.id, 'Faculty replenished stock',
          {'before':before,'after':resource_snapshot(resource)})
    db.commit()
    db.refresh(resource)
    return enrich_resource_response(resource)


@app.post('/resources/{resource_id}/resubmit', response_model=schemas.ResourceResponse, tags=['Resources'])
def resubmit_resource(resource_id: int, db: Session = Depends(get_write_db),
                      current_user: models.User = Depends(require_faculty)):
    resource = db.get(models.Resource, resource_id)
    if resource is None:
        raise HTTPException(404, 'Resource not found')
    if resource.custodian_id != current_user.id:
        raise HTTPException(403, 'You can only resubmit your own resources')
    if resource.verification_status != 'Rejected' or not resource.is_active:
        raise HTTPException(409, 'Only active rejected listings can be resubmitted')
    resource.verification_status = 'Pending Verification'
    resource.verification_reason = None
    resource.verified_by = None
    resource.verified_at = None
    audit(db, current_user, 'resource', resource.id, 'Faculty resubmitted listing', resource_snapshot(resource))
    db.commit()
    db.refresh(resource)
    return enrich_resource_response(resource)

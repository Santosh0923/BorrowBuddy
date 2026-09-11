"""Shared custody, inventory and audit rules for existing routes."""
import json
from fastapi import HTTPException
from sqlalchemy import func
import models

TERMINAL = ('Completed', 'Rejected', 'Cancelled')
COMMITTED = ('Approved', 'Ready for Pickup', 'Collected', 'Returned Pending Inspection', 'Maintenance Required')


def valid_custodian(db, user_id):
    user = db.get(models.User, user_id)
    if not user or not user.is_active or user.role != 'faculty':
        raise HTTPException(422, 'Assign an active Faculty owner')
    return user


def ensure_custody(user, request):
    if user.role != 'faculty' or request.custodian_id != user.id:
        raise HTTPException(403, 'Only the Faculty owner can perform this action')


def ensure_lendable(db, resource):
    if resource.verification_status != 'Verified':
        raise HTTPException(403, 'Only verified resources can be requested or approved for borrowing')
    if not resource.is_active or resource.status in ('Maintenance', 'Retired'):
        raise HTTPException(409, 'This resource is not currently available for lending')
    if resource.custodian_id is None:
        raise HTTPException(409, 'An Admin must assign a Faculty owner before this resource can be borrowed')
    valid_custodian(db, resource.custodian_id)


def committed_units(db, resource_id):
    return db.query(func.coalesce(func.sum(models.BorrowRequest.quantity), 0)).filter(
        models.BorrowRequest.resource_id == resource_id,
        models.BorrowRequest.status.in_(COMMITTED)).scalar()


def ensure_user_reassignable(db, user):
    resources = db.query(models.Resource).filter(models.Resource.custodian_id == user.id, models.Resource.is_active == True).first()
    requests = db.query(models.BorrowRequest).filter(models.BorrowRequest.custodian_id == user.id, models.BorrowRequest.status.notin_(TERMINAL)).first()
    loans = db.query(models.BorrowRequest).filter(models.BorrowRequest.student_id == user.id, models.BorrowRequest.status.notin_(TERMINAL)).first()
    if resources or requests or loans:
        raise HTTPException(409, 'Reassign owned resources and resolve open requests first')


def resource_snapshot(r):
    return {key:getattr(r,key) for key in ('name','category','location','description','total_quantity','available_quantity','custodian_id','status','is_active','verification_status','verification_reason')}


def audit(db, user, entity_type, entity_id, action, details):
    db.add(models.AuditEvent(entity_type=entity_type, entity_id=entity_id,
        action=action, actor_id=user.id, actor_name=user.name, actor_role=user.role,
        details=json.dumps(details, default=str)))

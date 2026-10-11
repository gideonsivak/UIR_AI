from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserResponse, UserUpdate


router = APIRouter(prefix="/api/users", tags=["Users"])


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_response(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def storage_failure(db: Session, error: SQLAlchemyError):
    db.rollback()
    raise HTTPException(500, "User storage is unavailable. Please try again later.") from error


def get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    return user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    try:
        if db.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(409, "An account with this email already exists.")
        timestamp = now()
        user = User(id=str(uuid4()), name=payload.name, email=email, created_at=timestamp, updated_at=timestamp)
        db.add(user)
        db.commit()
        db.refresh(user)
        return as_response(user)
    except HTTPException:
        raise
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists.") from error
    except SQLAlchemyError as error:
        storage_failure(db, error)


@router.get("", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)):
    try:
        return [as_response(user) for user in db.scalars(select(User).order_by(User.created_at)).all()]
    except SQLAlchemyError as error:
        storage_failure(db, error)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db)):
    try:
        return as_response(get_user_or_404(db, user_id))
    except SQLAlchemyError as error:
        storage_failure(db, error)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    try:
        user = get_user_or_404(db, user_id)
        duplicate = db.scalar(select(User.id).where(User.email == email, User.id != user_id))
        if duplicate:
            raise HTTPException(409, "An account with this email already exists.")
        user.name = payload.name
        user.email = email
        user.updated_at = now()
        db.commit()
        db.refresh(user)
        return as_response(user)
    except HTTPException:
        raise
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists.") from error
    except SQLAlchemyError as error:
        storage_failure(db, error)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: Session = Depends(get_db)):
    try:
        db.delete(get_user_or_404(db, user_id))
        db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as error:
        storage_failure(db, error)

from fastapi import Depends, Request, HTTPException
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import User

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise PermissionError("login_required")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise PermissionError("login_required")
    return user

def require_role(role: str):
    def dependency(request: Request, db: Session = Depends(get_db)):
        user_id = request.session.get("user_id")
        if not user_id:
            raise HTTPException(status_code=303, detail="Login required", headers={"Location": "/login"})
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        if not user:
            request.session.clear()
            raise HTTPException(status_code=303, detail="Login required", headers={"Location": "/login"})
        if user.role != role:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return dependency

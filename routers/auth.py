from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import User
from auth.hashing import hash_password, verify_password
from auth.rate_limit import login_limiter
from auth.csrf import ensure_csrf

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/login")
async def login(request: Request, role: str = "teacher"):
    if request.session.get("user_id"):
        user_role = request.session.get("role")
        return RedirectResponse(f"/{user_role}/dashboard", status_code=302)
    return templates.TemplateResponse(request=request, name="auth/login.html", context={"role": role if role in ("teacher","student") else "teacher", "csrf_token": ensure_csrf(request)})

@router.get("/teacher/login")
async def teacher_login(request: Request):
    return RedirectResponse("/login?role=teacher", status_code=302)

@router.get("/student/login")
async def student_login(request: Request):
    return RedirectResponse("/login?role=student", status_code=302)

@router.get("/register")
async def register(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={"csrf_token": ensure_csrf(request)},
    )

@router.post("/register")
async def register_student(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    if str(form.get("csrf_token", "")) != str(request.session.get("csrf", "")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    name = str(form.get("name", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    if not name or not email or len(password) < 10:
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"csrf_token": ensure_csrf(request),
                     "error": "Enter your name and email and use a password with at least 10 characters."},
            status_code=400,
        )
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"csrf_token": ensure_csrf(request), "error": "An account with that email already exists."},
            status_code=409,
        )
    user = User(name=name, email=email, password_hash=hash_password(password), role="student")
    db.add(user)
    db.commit()
    request.session.clear()
    return RedirectResponse("/login?role=student&registered=1", status_code=303)

async def login_post(request: Request, role: str, db: Session):
    form = await request.form()
    if str(form.get("csrf_token","")) != str(request.session.get("csrf","")):
        return templates.TemplateResponse(request=request, name="auth/login.html", context={"role": role, "csrf_token": ensure_csrf(request), "error": "Invalid credentials"}, status_code=403)
    email = str(form.get("email","")).strip().lower()
    password = str(form.get("password",""))
    ip = request.client.host if request.client else "unknown"
    if not login_limiter.allowed(ip) or not login_limiter.allowed(email):
        return templates.TemplateResponse(request=request, name="auth/login.html", context={"role": role, "csrf_token": ensure_csrf(request), "error": "Too many login attempts. Try again later."}, status_code=429)
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if not user or user.role != role or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="auth/login.html", context={"role": role, "csrf_token": ensure_csrf(request), "error": "Invalid credentials"}, status_code=401)
    request.session["user_id"] = user.id
    request.session["role"] = user.role
    ensure_csrf(request)
    return RedirectResponse(f"/{role}/dashboard", status_code=302)

@router.post("/teacher/login")
async def teacher_login_post(request: Request, db: Session = Depends(get_db)):
    return await login_post(request, "teacher", db)

@router.post("/student/login")
async def student_login_post(request: Request, db: Session = Depends(get_db)):
    return await login_post(request, "student", db)

@router.post("/logout")
async def logout(request: Request):
    form = await request.form()
    if str(form.get("csrf_token", "")) != str(request.session.get("csrf", "")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

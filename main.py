from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from sqlalchemy import inspect
from sqlalchemy import text
from database.connection import engine
from database.models import Base
from config.settings import settings
from routers import auth, teacher, student

Base.metadata.create_all(bind=engine)
if "relevance" not in {column["name"] for column in inspect(engine).get_columns("evaluations")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE evaluations ADD COLUMN relevance VARCHAR NOT NULL DEFAULT 'UNCLEAR'"))
app = FastAPI(title="EduCite")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, https_only=False, max_age=settings.session_timeout_minutes * 60)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth.router)
app.include_router(teacher.router)
app.include_router(student.router)

templates = Jinja2Templates(directory="templates")

@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(url="/login", status_code=302)

@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if exc.status_code == 403:
        return templates.TemplateResponse(request=request, name="errors/403.html", context={}, status_code=403)
    if exc.status_code == 404:
        return templates.TemplateResponse(request=request, name="errors/404.html", context={}, status_code=404)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

@app.exception_handler(403)
async def forbidden(request: Request, exc):
    return templates.TemplateResponse(request=request, name="errors/403.html", context={}, status_code=403)

@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(request=request, name="errors/404.html", context={}, status_code=404)

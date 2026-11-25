import secrets
from fastapi import HTTPException, Request

def ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token

def validate_csrf(request: Request):
    async def dependency():
        form = await request.form()
        if not secrets.compare_digest(str(form.get("csrf_token", "")), str(request.session.get("csrf", ""))):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
        return form
    return dependency

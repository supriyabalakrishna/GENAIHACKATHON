from itsdangerous import URLSafeTimedSerializer
from config.settings import settings

serializer = URLSafeTimedSerializer(settings.secret_key, salt="educite-session")

def encode_session(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})

def decode_session(token: str) -> dict | None:
    try:
        return serializer.loads(token, max_age=settings.session_timeout_minutes * 60)
    except Exception:
        return None

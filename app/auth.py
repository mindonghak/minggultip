import os
from itsdangerous import URLSafeTimedSerializer, BadSignature
from passlib.hash import bcrypt, pbkdf2_sha256
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="session")

def hash_password(password: str) -> str:
    return pbkdf2_sha256.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$2"):
        return bcrypt.verify(password, password_hash)
    return pbkdf2_sha256.verify(password, password_hash)

def create_session(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})

def read_session(token: str, max_age_seconds: int = 60 * 60 * 24 * 30):
    try:
        return serializer.loads(token, max_age=max_age_seconds)
    except BadSignature:
        return None

def create_csrf_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id, "purpose": "csrf"})

def verify_csrf_token(token: str, user_id: int, max_age_seconds: int = 60 * 60 * 4) -> bool:
    try:
        data = serializer.loads(token, max_age=max_age_seconds)
    except BadSignature:
        return False
    return data.get("purpose") == "csrf" and data.get("user_id") == user_id

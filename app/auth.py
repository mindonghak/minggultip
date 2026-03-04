import os
from itsdangerous import URLSafeTimedSerializer, BadSignature
from passlib.hash import bcrypt
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="session")

def hash_password(password: str) -> str:
    return bcrypt.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.verify(password, password_hash)

def create_session(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})

def read_session(token: str, max_age_seconds: int = 60 * 60 * 24 * 30):
    try:
        return serializer.loads(token, max_age=max_age_seconds)
    except BadSignature:
        return None
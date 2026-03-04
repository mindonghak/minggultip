from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from .db import get_db
from .models import User, Post, Category
from .auth import hash_password, verify_password, create_session, read_session

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get("session")
    if not token:
        return None
    data = read_session(token)
    if not data:
        return None
    user = db.get(User, data["user_id"])
    return user

@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    posts = db.execute(
        select(Post).order_by(desc(Post.created_at)).limit(30)
    ).scalars().all()
    categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "posts": posts,
        "categories": categories
    })

@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    print("DEBUG password repr:", repr(password))
    print("DEBUG password bytes:", len(password.encode("utf-8")))
    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists:
        return templates.TemplateResponse("register.html", {"request": request, "error": "이미 사용 중인 이메일입니다."})

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("session", create_session(user.id), httponly=True, samesite="lax")
    return resp

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "이메일/비밀번호가 올바르지 않습니다."})

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("session", create_session(user.id), httponly=True, samesite="lax")
    return resp

@router.post("/logout")
def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("session")
    return resp

@router.get("/posts/new")
def new_post_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
    return templates.TemplateResponse("post_new.html", {"request": request, "user": user, "categories": categories, "error": None})

@router.post("/posts/new")
def new_post(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    category_name: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    cat = db.execute(select(Category).where(Category.name == category_name)).scalar_one_or_none()
    if not cat:
        cat = Category(name=category_name)
        db.add(cat)
        db.commit()
        db.refresh(cat)

    post = Post(title=title, content=content, author_id=user.id, category_id=cat.id)
    db.add(post)
    db.commit()
    db.refresh(post)
    return RedirectResponse(f"/posts/{post.id}", status_code=303)

@router.get("/posts/{post_id}")
def post_detail(request: Request, post_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not post:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("post_detail.html", {"request": request, "user": user, "post": post})
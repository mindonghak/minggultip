from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func, or_

from .db import get_db
from .models import User, Post, Category, Comment, Like
from .auth import (
    create_csrf_token,
    create_session,
    hash_password,
    read_session,
    verify_csrf_token,
    verify_password,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get("session")
    if not token:
        return None
    data = read_session(token)
    if not data:
        return None
    return db.get(User, data["user_id"])


def render(request: Request, template_name: str, context: dict):
    user = context.get("user")
    if user and "csrf_token" not in context:
        context["csrf_token"] = create_csrf_token(user.id)
    context["request"] = request
    return templates.TemplateResponse(template_name, context)


def require_valid_csrf(user: User, csrf_token: str) -> bool:
    return bool(csrf_token and verify_csrf_token(csrf_token, user.id))


@router.get("/")
def index(
    request: Request,
    q: str = "",
    sort: str = "recent",
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    categories = db.execute(select(Category).order_by(Category.name)).scalars().all()

    like_counts = (
        select(Like.post_id, func.count(Like.id).label("like_count"))
        .group_by(Like.post_id)
        .subquery()
    )
    recent_stmt = select(Post)
    popular_stmt = select(Post).outerjoin(like_counts, Post.id == like_counts.c.post_id)

    query = q.strip()
    if query:
        term = f"%{query}%"
        search_filter = or_(
            Post.title.ilike(term),
            Post.content.ilike(term),
            Category.name.ilike(term),
        )
        recent_stmt = recent_stmt.join(Category).where(search_filter)
        popular_stmt = popular_stmt.join(Category).where(
            or_(
                Post.title.ilike(term),
                Post.content.ilike(term),
                Category.name.ilike(term),
            )
        )

    recent_posts = db.execute(
        recent_stmt.order_by(desc(Post.created_at)).limit(8)
    ).scalars().all()
    popular_posts = db.execute(
        popular_stmt
        .order_by(desc(func.coalesce(like_counts.c.like_count, 0)), desc(Post.created_at))
        .limit(8)
    ).scalars().all()

    return render(request, "index.html", {
        "user": user,
        "recent_posts": recent_posts,
        "popular_posts": popular_posts,
        "categories": categories,
        "q": query,
    })


@router.get("/register")
def register_page(request: Request):
    return render(request, "register.html", {"user": None, "error": None})


@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    nickname: str = Form(""),
    db: Session = Depends(get_db),
):
    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists:
        return render(request, "register.html", {"user": None, "error": "이미 사용 중인 이메일입니다."})

    display_name = nickname.strip() or email.split("@")[0]
    user = User(email=email, nickname=display_name, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("session", create_session(user.id), httponly=True, samesite="lax")
    return resp


@router.get("/login")
def login_page(request: Request):
    return render(request, "login.html", {"user": None, "error": None})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return render(request, "login.html", {"user": None, "error": "이메일 또는 비밀번호가 올바르지 않습니다."})

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("session", create_session(user.id), httponly=True, samesite="lax")
    return resp


@router.post("/logout")
def logout(
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user and not require_valid_csrf(user, csrf_token):
        return RedirectResponse(url="/", status_code=303)

    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("session")
    return resp


@router.get("/posts/new")
def new_post_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
    return render(request, "post_new.html", {
        "user": user,
        "categories": categories,
        "error": None,
    })


@router.post("/posts/new")
def new_post(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    category_name: str = Form(...),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not require_valid_csrf(user, csrf_token):
        return RedirectResponse("/posts/new", status_code=303)

    cleaned_category = category_name.strip()
    cat = db.execute(select(Category).where(Category.name == cleaned_category)).scalar_one_or_none()
    if not cat:
        cat = Category(name=cleaned_category)
        db.add(cat)
        db.commit()
        db.refresh(cat)

    post = Post(title=title.strip(), content=content.strip(), author_id=user.id, category_id=cat.id)
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

    categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
    comments = db.execute(
        select(Comment)
        .where(Comment.post_id == post.id)
        .order_by(Comment.created_at)
    ).scalars().all()
    user_liked = False
    if user:
        user_liked = db.execute(
            select(Like).where(Like.post_id == post.id, Like.user_id == user.id)
        ).scalar_one_or_none() is not None

    return render(request, "post_detail.html", {
        "user": user,
        "post": post,
        "comments": comments,
        "categories": categories,
        "q": "",
        "user_liked": user_liked,
    })


@router.post("/posts/{post_id}/comments")
def add_comment(
    request: Request,
    post_id: int,
    content: str = Form(...),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not post:
        return RedirectResponse("/", status_code=303)
    if not require_valid_csrf(user, csrf_token):
        return RedirectResponse(f"/posts/{post_id}", status_code=303)

    cleaned_content = content.strip()
    if cleaned_content:
        db.add(Comment(content=cleaned_content, user_id=user.id, post_id=post.id))
        db.commit()
    return RedirectResponse(f"/posts/{post_id}", status_code=303)


@router.post("/posts/{post_id}/like")
def toggle_like(
    request: Request,
    post_id: int,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not post:
        return RedirectResponse("/", status_code=303)
    if not require_valid_csrf(user, csrf_token):
        return RedirectResponse(f"/posts/{post_id}", status_code=303)

    existing = db.execute(
        select(Like).where(Like.post_id == post.id, Like.user_id == user.id)
    ).scalar_one_or_none()
    if existing:
        db.delete(existing)
    else:
        db.add(Like(post_id=post.id, user_id=user.id))
    db.commit()
    return RedirectResponse(f"/posts/{post_id}", status_code=303)


@router.post("/admin/posts/{post_id}/delete")
def admin_delete_post(
    request: Request,
    post_id: int,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not user or not user.is_admin or not require_valid_csrf(user, csrf_token):
        return RedirectResponse("/", status_code=303)
    if post:
        db.delete(post)
        db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/admin/comments/{comment_id}/delete")
def admin_delete_comment(
    request: Request,
    comment_id: int,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    comment = db.get(Comment, comment_id)
    if not user or not user.is_admin or not require_valid_csrf(user, csrf_token):
        return RedirectResponse("/", status_code=303)
    post_id = comment.post_id if comment else None
    if comment:
        db.delete(comment)
        db.commit()
    return RedirectResponse(f"/posts/{post_id}" if post_id else "/", status_code=303)

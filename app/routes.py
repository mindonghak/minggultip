import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func, or_

from .db import get_db
from .models import (
    AnonymousDislike,
    AnonymousLike,
    Bookmark,
    Category,
    Comment,
    DeletedPost,
    Dislike,
    Inquiry,
    Like,
    Post,
    PostTag,
    Report,
    Tag,
    User,
)
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
PER_PAGE = 5
TEMP_POST_LIKE_THRESHOLD = 5
TEMP_POST_DISLIKE_THRESHOLD = 5
EDITORIAL_POST_DISLIKE_THRESHOLD = 3
TEMP_POST_REVIEW_DAYS = 7
DEFAULT_CATEGORY_NAME = "일반"
ANONYMOUS_WRITER_EMAIL = "anonymous@minggultip.local"
LOCAL_EMAIL_DOMAIN = "local.minggultip.invalid"
ANONYMOUS_NICKNAMES = [
    "생활꿀벌",
    "익명살림왕",
    "조용한고수",
    "오늘의팁러",
    "동네해결사",
    "작은발견가",
    "알뜰탐험가",
    "정리연구원",
]


def format_datetime(value):
    if not value:
        return ""
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except AttributeError:
        return str(value)[:16]


templates.env.filters["datetime"] = format_datetime


def total_likes(post: Post) -> int:
    return len(post.likes) + len(post.anonymous_likes)


templates.env.filters["total_likes"] = total_likes


def total_dislikes(post: Post) -> int:
    return len(post.dislikes) + len(post.anonymous_dislikes)


templates.env.filters["total_dislikes"] = total_dislikes


def display_author(post: Post) -> str:
    if post.anonymous_author_name:
        return post.anonymous_author_name
    return post.author.nickname or post.author.username or post.author.email


templates.env.filters["display_author"] = display_author


def reaction_grade(post: Post) -> dict[str, str]:
    likes = total_likes(post)
    dislikes = total_dislikes(post)
    total = likes + dislikes
    if total == 0:
        return {"label": "신규", "class": "grade-new"}
    if dislikes >= 3 and dislikes > likes:
        return {"label": "주의", "class": "grade-risk"}
    if likes >= 3 and dislikes >= 3:
        return {"label": "호불호", "class": "grade-mixed"}
    if likes >= 3 and likes > dislikes:
        return {"label": "추천", "class": "grade-good"}
    return {"label": "신규", "class": "grade-new"}


templates.env.filters["reaction_grade"] = reaction_grade


def is_temporary_post(post: Post) -> bool:
    return post.status == "temporary"


templates.env.tests["temporary_post"] = is_temporary_post


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
    context.setdefault("canonical_url", str(request.url).split("?")[0])
    context.setdefault("page_title", "민꿀팁")
    context.setdefault("page_description", "오늘 바로 써먹을 수 있는 생활 꿀팁과 정보를 나누는 커뮤니티입니다.")
    return templates.TemplateResponse(template_name, context)


def require_valid_csrf(user: User, csrf_token: str) -> bool:
    return bool(csrf_token and verify_csrf_token(csrf_token, user.id))


def clean_username(value: str) -> str:
    return value.strip().lower()


def internal_email_for_username(username: str) -> str:
    return f"{username}@{LOCAL_EMAIL_DOMAIN}"


def clean_image_url(value: str) -> str | None:
    url = value.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        return None
    return url[:1000]


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def temporary_deadline() -> datetime:
    return utc_now() + timedelta(days=TEMP_POST_REVIEW_DAYS)


def random_anonymous_name() -> str:
    return f"{secrets.choice(ANONYMOUS_NICKNAMES)}{secrets.randbelow(900) + 100}"


def get_anonymous_writer(db: Session) -> User:
    user = db.execute(select(User).where(User.email == ANONYMOUS_WRITER_EMAIL)).scalar_one_or_none()
    if user:
        return user
    user = User(
        email=ANONYMOUS_WRITER_EMAIL,
        nickname="익명 작성자",
        password_hash=hash_password(secrets.token_urlsafe(24)),
    )
    db.add(user)
    db.flush()
    return user


def get_default_category(db: Session) -> Category:
    category = db.execute(select(Category).where(Category.name == DEFAULT_CATEGORY_NAME)).scalar_one_or_none()
    if category:
        return category
    category = Category(name=DEFAULT_CATEGORY_NAME)
    db.add(category)
    db.flush()
    return category


def post_like_count(db: Session, post_id: int) -> int:
    user_likes = db.execute(select(func.count(Like.id)).where(Like.post_id == post_id)).scalar_one()
    anon_likes = db.execute(select(func.count(AnonymousLike.id)).where(AnonymousLike.post_id == post_id)).scalar_one()
    return int(user_likes or 0) + int(anon_likes or 0)


def post_dislike_count(db: Session, post_id: int) -> int:
    user_dislikes = db.execute(select(func.count(Dislike.id)).where(Dislike.post_id == post_id)).scalar_one()
    anon_dislikes = db.execute(select(func.count(AnonymousDislike.id)).where(AnonymousDislike.post_id == post_id)).scalar_one()
    return int(user_dislikes or 0) + int(anon_dislikes or 0)


def archive_post_before_delete(db: Session, post: Post, reason: str) -> DeletedPost:
    archived = DeletedPost(
        original_post_id=post.id,
        title=post.title,
        content=post.content,
        image_url=post.image_url,
        source=post.source,
        status=post.status,
        author_label=display_author(post),
        category_name=post.category.name if post.category else None,
        tag_text=post_tag_text(post),
        like_count=post_like_count(db, post.id),
        dislike_count=post_dislike_count(db, post.id),
        delete_reason=reason[:255],
    )
    db.add(archived)
    db.flush()
    return archived


def delete_post_with_archive(db: Session, post: Post, reason: str):
    archive_post_before_delete(db, post, reason)
    db.delete(post)


def moderate_post(db: Session, post: Post) -> bool:
    likes = post_like_count(db, post.id)
    dislikes = post_dislike_count(db, post.id)
    if post.source == "editorial" and dislikes >= EDITORIAL_POST_DISLIKE_THRESHOLD:
        delete_post_with_archive(db, post, "editorial_dislike_threshold")
        db.commit()
        return False
    if post.status != "temporary":
        return True
    if dislikes >= TEMP_POST_DISLIKE_THRESHOLD:
        delete_post_with_archive(db, post, "temporary_dislike_threshold")
        db.commit()
        return False
    if likes >= TEMP_POST_LIKE_THRESHOLD:
        post.status = "published"
        post.promotion_deadline = None
        db.commit()
        return True
    if post.promotion_deadline and post.promotion_deadline <= utc_now():
        delete_post_with_archive(db, post, "temporary_deadline_expired")
        db.commit()
        return False
    return True


def moderate_posts(db: Session):
    posts = db.execute(select(Post).where(or_(Post.status == "temporary", Post.source == "editorial"))).scalars().all()
    changed = False
    for post in posts:
        likes = post_like_count(db, post.id)
        dislikes = post_dislike_count(db, post.id)
        if post.source == "editorial" and dislikes >= EDITORIAL_POST_DISLIKE_THRESHOLD:
            delete_post_with_archive(db, post, "editorial_dislike_threshold")
            changed = True
        elif post.status == "temporary" and dislikes >= TEMP_POST_DISLIKE_THRESHOLD:
            delete_post_with_archive(db, post, "temporary_dislike_threshold")
            changed = True
        elif post.status == "temporary" and likes >= TEMP_POST_LIKE_THRESHOLD:
            post.status = "published"
            post.promotion_deadline = None
            changed = True
        elif post.status == "temporary" and post.promotion_deadline and post.promotion_deadline <= utc_now():
            delete_post_with_archive(db, post, "temporary_deadline_expired")
            changed = True
    if changed:
        db.commit()


def categories_and_tags(db: Session):
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    tag_counts = (
        select(Tag, func.count(PostTag.id).label("post_count"))
        .join(PostTag)
        .join(Post)
        .where(Post.created_at >= today_start)
        .group_by(Tag.id)
        .order_by(desc(func.count(PostTag.id)), Tag.name)
        .limit(5)
    )
    tags = [row[0] for row in db.execute(tag_counts).all()]
    if not tags:
        fallback_tag_counts = (
            select(Tag, func.count(PostTag.id).label("post_count"))
            .join(PostTag)
            .group_by(Tag.id)
            .order_by(desc(func.count(PostTag.id)), Tag.name)
            .limit(5)
        )
        tags = [row[0] for row in db.execute(fallback_tag_counts).all()]
    return {
        "categories": db.execute(select(Category).order_by(Category.name)).scalars().all(),
        "tags": tags,
    }


def parse_tag_names(raw_tags: str) -> list[str]:
    names: list[str] = []
    for raw in raw_tags.replace("#", " ").replace(",", " ").split():
        name = raw.strip().lower()
        if name and name not in names:
            names.append(name[:50])
    return names[:8]


def sync_post_tags(db: Session, post: Post, raw_tags: str):
    db.execute(PostTag.__table__.delete().where(PostTag.post_id == post.id))
    for name in parse_tag_names(raw_tags):
        tag = db.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        db.add(PostTag(post_id=post.id, tag_id=tag.id))


def post_tag_text(post: Post) -> str:
    return " ".join(tag.name for tag in post.tags)


def can_manage_post(user: User | None, post: Post) -> bool:
    return bool(user and (user.is_admin or post.author_id == user.id))


def can_manage_comment(user: User | None, comment: Comment) -> bool:
    return bool(user and (user.is_admin or comment.user_id == user.id))


def search_filter(query: str):
    if not query:
        return None
    term = f"%{query}%"
    return or_(
        Post.title.ilike(term),
        Post.content.ilike(term),
        Post.category.has(Category.name.ilike(term)),
        Post.tags.any(Tag.name.ilike(term)),
    )


def popular_query(db: Session, query: str):
    like_counts = select(Like.post_id, func.count(Like.id).label("like_count")).group_by(Like.post_id).subquery()
    anonymous_like_counts = select(AnonymousLike.post_id, func.count(AnonymousLike.id).label("anonymous_like_count")).group_by(AnonymousLike.post_id).subquery()
    total_like_count = func.coalesce(like_counts.c.like_count, 0) + func.coalesce(anonymous_like_counts.c.anonymous_like_count, 0)
    stmt = (
        select(Post)
        .outerjoin(like_counts, Post.id == like_counts.c.post_id)
        .outerjoin(anonymous_like_counts, Post.id == anonymous_like_counts.c.post_id)
    )
    condition = search_filter(query)
    if condition is not None:
        stmt = stmt.where(condition)
    return stmt.order_by(desc(total_like_count), desc(Post.created_at))


def paginated_posts(db: Session, stmt, page: int, per_page: int = PER_PAGE):
    page = max(page, 1)
    items = db.execute(stmt.offset((page - 1) * per_page).limit(per_page + 1)).scalars().all()
    return items[:per_page], len(items) > per_page, page


def post_count(db: Session, query: str) -> int:
    stmt = select(func.count(Post.id))
    condition = search_filter(query)
    if condition is not None:
        stmt = stmt.where(condition)
    return int(db.execute(stmt).scalar_one() or 0)


@router.get("/")
def index(
    request: Request,
    q: str = "",
    tab: str = "recent",
    recent_page: int = 1,
    popular_page: int = 1,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    moderate_posts(db)
    query = q.strip()
    active_tab = tab if tab in {"recent", "popular"} else "recent"
    recent_stmt = select(Post).order_by(desc(Post.created_at))
    condition = search_filter(query)
    if condition is not None:
        recent_stmt = recent_stmt.where(condition)

    recent_posts, recent_has_next, recent_page = paginated_posts(db, recent_stmt, recent_page)
    popular_posts, popular_has_next, popular_page = paginated_posts(db, popular_query(db, query), popular_page)
    total_posts = post_count(db, query)
    total_pages = max((total_posts + PER_PAGE - 1) // PER_PAGE, 1)

    return render(request, "index.html", {
        "user": user,
        "recent_posts": recent_posts,
        "popular_posts": popular_posts,
        "recent_page": recent_page,
        "popular_page": popular_page,
        "recent_has_next": recent_has_next,
        "popular_has_next": popular_has_next,
        "q": query,
        "active_tab": active_tab,
        "total_posts": total_posts,
        "total_pages": total_pages,
        "page_title": "민꿀팁 - 생활 꿀팁 공유 커뮤니티",
        "page_description": "절약, 정리, 교통, 생활 정보까지 오늘 바로 써먹을 수 있는 꿀팁을 모아보세요.",
        **categories_and_tags(db),
    })


@router.get("/register")
def register_page(request: Request):
    return render(request, "register.html", {"user": None, "error": None})


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    nickname: str = Form(...),
    recovery_email: str = Form(""),
    db: Session = Depends(get_db),
):
    cleaned_username = clean_username(username)
    display_name = nickname.strip()
    cleaned_recovery_email = recovery_email.strip().lower() or None
    if len(cleaned_username) < 3 or not cleaned_username.replace("_", "").replace("-", "").isalnum():
        return render(request, "register.html", {"user": None, "error": "아이디는 영문, 숫자, -, _ 조합으로 3자 이상 입력해 주세요."})
    if len(password) < 4:
        return render(request, "register.html", {"user": None, "error": "비밀번호는 4자 이상 입력해 주세요."})

    username_exists = db.execute(select(User).where(User.username == cleaned_username)).scalar_one_or_none()
    legacy_email_exists = db.execute(select(User).where(User.email == cleaned_username)).scalar_one_or_none()
    if username_exists or legacy_email_exists:
        return render(request, "register.html", {"user": None, "error": "이미 사용 중인 아이디입니다."})

    if cleaned_recovery_email:
        email_exists = db.execute(
            select(User).where(or_(User.recovery_email == cleaned_recovery_email, User.email == cleaned_recovery_email))
        ).scalar_one_or_none()
        if email_exists:
            return render(request, "register.html", {"user": None, "error": "이미 등록된 복구용 이메일입니다."})

    user = User(
        email=cleaned_recovery_email or internal_email_for_username(cleaned_username),
        username=cleaned_username,
        nickname=display_name,
        recovery_email=cleaned_recovery_email,
        email_verified=False,
        password_hash=hash_password(password),
    )
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
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    identifier = clean_username(username)
    user = db.execute(select(User).where(or_(User.username == identifier, User.email == identifier))).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return render(request, "login.html", {"user": None, "error": "아이디 또는 비밀번호가 올바르지 않습니다."})
    if user.is_suspended:
        return render(request, "login.html", {"user": None, "error": "정지된 계정입니다."})

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("session", create_session(user.id), httponly=True, samesite="lax")
    return resp


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user and not require_valid_csrf(user, csrf_token):
        return RedirectResponse(url="/", status_code=303)
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("session")
    return resp


@router.get("/me")
def my_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    posts = db.execute(select(Post).where(Post.author_id == user.id).order_by(desc(Post.created_at)).limit(20)).scalars().all()
    comments = db.execute(select(Comment).where(Comment.user_id == user.id).order_by(desc(Comment.created_at)).limit(20)).scalars().all()
    bookmarks = db.execute(select(Bookmark).where(Bookmark.user_id == user.id).order_by(desc(Bookmark.created_at)).limit(20)).scalars().all()
    likes = db.execute(select(Like).where(Like.user_id == user.id).order_by(desc(Like.created_at)).limit(20)).scalars().all()
    inquiries = db.execute(select(Inquiry).where(Inquiry.user_id == user.id).order_by(desc(Inquiry.created_at)).limit(20)).scalars().all()
    return render(request, "me.html", {
        "user": user,
        "posts": posts,
        "comments": comments,
        "bookmarks": bookmarks,
        "likes": likes,
        "inquiries": inquiries,
        "q": "",
        **categories_and_tags(db),
    })


@router.get("/inquiries/new")
def new_inquiry_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return render(request, "inquiry_form.html", {
        "user": user,
        "error": None,
        "q": "",
        **categories_and_tags(db),
    })


@router.post("/inquiries/new")
def new_inquiry(
    request: Request,
    subject: str = Form(...),
    message: str = Form(...),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    subject = subject.strip()
    message = message.strip()
    if not require_valid_csrf(user, csrf_token):
        return RedirectResponse("/inquiries/new", status_code=303)
    if not subject or not message:
        return render(request, "inquiry_form.html", {
            "user": user,
            "error": "제목과 내용을 모두 입력해 주세요.",
            "q": "",
            **categories_and_tags(db),
        })
    db.add(Inquiry(subject=subject[:200], message=message, user_id=user.id))
    db.commit()
    return RedirectResponse("/me#inquiries", status_code=303)


@router.get("/posts/new")
def new_post_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return render(request, "post_form.html", {
        "user": user,
        "post": None,
        "tag_text": "",
        "action": "/posts/new",
        "submit_label": "등록",
        "error": None,
        "is_anonymous_post": user is None,
        "temporary_like_threshold": TEMP_POST_LIKE_THRESHOLD,
        "temporary_dislike_threshold": TEMP_POST_DISLIKE_THRESHOLD,
        "temporary_review_days": TEMP_POST_REVIEW_DAYS,
        **categories_and_tags(db),
    })


@router.post("/posts/new")
def new_post(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    image_url: str = Form(""),
    tags: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user and not require_valid_csrf(user, csrf_token):
        return RedirectResponse("/posts/new", status_code=303)

    cat = get_default_category(db)

    if user:
        author_id = user.id
        anonymous_author_name = None
        status = "published"
        source = "user"
        promotion_deadline = None
    else:
        anonymous_writer = get_anonymous_writer(db)
        author_id = anonymous_writer.id
        anonymous_author_name = random_anonymous_name()
        status = "temporary"
        source = "anonymous"
        promotion_deadline = temporary_deadline()

    post = Post(
        title=title.strip(),
        content=content.strip(),
        image_url=clean_image_url(image_url),
        author_id=author_id,
        category_id=cat.id,
        anonymous_author_name=anonymous_author_name,
        status=status,
        source=source,
        promotion_deadline=promotion_deadline,
    )
    db.add(post)
    db.flush()
    sync_post_tags(db, post, tags)
    db.commit()
    return RedirectResponse(f"/posts/{post.id}", status_code=303)


@router.get("/posts/{post_id}/edit")
def edit_post_page(request: Request, post_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not post:
        return RedirectResponse("/", status_code=303)
    if not moderate_post(db, post):
        return RedirectResponse("/", status_code=303)
    if not can_manage_post(user, post):
        return RedirectResponse(f"/posts/{post.id}", status_code=303)
    return render(request, "post_form.html", {
        "user": user,
        "post": post,
        "tag_text": post_tag_text(post),
        "action": f"/posts/{post.id}/edit",
        "submit_label": "수정",
        "error": None,
        **categories_and_tags(db),
    })


@router.post("/posts/{post_id}/edit")
def edit_post(
    request: Request,
    post_id: int,
    title: str = Form(...),
    content: str = Form(...),
    image_url: str = Form(""),
    tags: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not post:
        return RedirectResponse("/", status_code=303)
    if not can_manage_post(user, post) or not require_valid_csrf(user, csrf_token):
        return RedirectResponse(f"/posts/{post.id}", status_code=303)

    post.title = title.strip()
    post.content = content.strip()
    post.image_url = clean_image_url(image_url)
    sync_post_tags(db, post, tags)
    db.commit()
    return RedirectResponse(f"/posts/{post.id}", status_code=303)


@router.post("/posts/{post_id}/delete")
def delete_post(request: Request, post_id: int, csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not post:
        return RedirectResponse("/", status_code=303)
    if can_manage_post(user, post) and require_valid_csrf(user, csrf_token):
        reason = "admin_deleted" if user and user.is_admin and user.id != post.author_id else "author_deleted"
        delete_post_with_archive(db, post, reason)
        db.commit()
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(f"/posts/{post.id}", status_code=303)


@router.get("/posts/{post_id}")
def post_detail(request: Request, post_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not post:
        return RedirectResponse("/", status_code=303)
    if not moderate_post(db, post):
        return RedirectResponse("/", status_code=303)

    post.view_count += 1
    db.commit()
    db.refresh(post)

    comments = db.execute(select(Comment).where(Comment.post_id == post.id).order_by(Comment.created_at)).scalars().all()
    user_liked = user_disliked = user_bookmarked = False
    anon_key = request.cookies.get("anon_like_id")
    if user:
        user_liked = db.execute(select(Like).where(Like.post_id == post.id, Like.user_id == user.id)).scalar_one_or_none() is not None
        user_disliked = db.execute(select(Dislike).where(Dislike.post_id == post.id, Dislike.user_id == user.id)).scalar_one_or_none() is not None
        user_bookmarked = db.execute(select(Bookmark).where(Bookmark.post_id == post.id, Bookmark.user_id == user.id)).scalar_one_or_none() is not None
    elif anon_key:
        user_liked = db.execute(select(AnonymousLike).where(AnonymousLike.post_id == post.id, AnonymousLike.anon_key == anon_key)).scalar_one_or_none() is not None
        user_disliked = db.execute(select(AnonymousDislike).where(AnonymousDislike.post_id == post.id, AnonymousDislike.anon_key == anon_key)).scalar_one_or_none() is not None

    tag_ids = [tag.id for tag in post.tags]
    related_stmt = select(Post).where(Post.id != post.id)
    if tag_ids:
        related_stmt = related_stmt.where(or_(Post.category_id == post.category_id, Post.tags.any(Tag.id.in_(tag_ids))))
    else:
        related_stmt = related_stmt.where(Post.category_id == post.category_id)
    related_posts = db.execute(related_stmt.order_by(desc(Post.created_at)).limit(4)).scalars().all()

    return render(request, "post_detail.html", {
        "user": user,
        "post": post,
        "comments": comments,
        "related_posts": related_posts,
        "q": "",
        "user_liked": user_liked,
        "user_disliked": user_disliked,
        "user_bookmarked": user_bookmarked,
        "can_manage": can_manage_post(user, post),
        "temporary_like_threshold": TEMP_POST_LIKE_THRESHOLD,
        "temporary_dislike_threshold": TEMP_POST_DISLIKE_THRESHOLD,
        "page_title": f"{post.title} - 민꿀팁",
        "page_description": post.content.replace("\n", " ")[:140],
        "page_image_url": post.image_url,
        **categories_and_tags(db),
    })


@router.post("/posts/{post_id}/comments")
def add_comment(request: Request, post_id: int, content: str = Form(...), csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not post:
        return RedirectResponse("/", status_code=303)
    if require_valid_csrf(user, csrf_token) and content.strip():
        db.add(Comment(content=content.strip(), user_id=user.id, post_id=post.id))
        db.commit()
    return RedirectResponse(f"/posts/{post_id}", status_code=303)


@router.post("/comments/{comment_id}/edit")
def edit_comment(request: Request, comment_id: int, content: str = Form(...), csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    comment = db.get(Comment, comment_id)
    if not comment:
        return RedirectResponse("/", status_code=303)
    if can_manage_comment(user, comment) and require_valid_csrf(user, csrf_token) and content.strip():
        comment.content = content.strip()
        db.commit()
    return RedirectResponse(f"/posts/{comment.post_id}", status_code=303)


@router.post("/comments/{comment_id}/delete")
def delete_comment(request: Request, comment_id: int, csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    comment = db.get(Comment, comment_id)
    if not comment:
        return RedirectResponse("/", status_code=303)
    post_id = comment.post_id
    if can_manage_comment(user, comment) and require_valid_csrf(user, csrf_token):
        db.delete(comment)
        db.commit()
    return RedirectResponse(f"/posts/{post_id}", status_code=303)


@router.post("/posts/{post_id}/like")
def toggle_like(request: Request, post_id: int, csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not post:
        return RedirectResponse("/", status_code=303)

    resp = RedirectResponse(f"/posts/{post_id}", status_code=303)
    if user:
        if not require_valid_csrf(user, csrf_token):
            return resp
        existing = db.execute(select(Like).where(Like.post_id == post.id, Like.user_id == user.id)).scalar_one_or_none()
        if existing:
            db.delete(existing)
        else:
            opposite = db.execute(select(Dislike).where(Dislike.post_id == post.id, Dislike.user_id == user.id)).scalar_one_or_none()
            if opposite:
                db.delete(opposite)
            db.add(Like(post_id=post.id, user_id=user.id))
    else:
        anon_key = request.cookies.get("anon_like_id") or secrets.token_urlsafe(24)
        existing = db.execute(select(AnonymousLike).where(AnonymousLike.post_id == post.id, AnonymousLike.anon_key == anon_key)).scalar_one_or_none()
        if existing:
            db.delete(existing)
        else:
            opposite = db.execute(select(AnonymousDislike).where(AnonymousDislike.post_id == post.id, AnonymousDislike.anon_key == anon_key)).scalar_one_or_none()
            if opposite:
                db.delete(opposite)
            db.add(AnonymousLike(post_id=post.id, anon_key=anon_key))
        resp.set_cookie("anon_like_id", anon_key, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 365)
    db.commit()
    if not moderate_post(db, post):
        return RedirectResponse("/", status_code=303)
    return resp


@router.post("/posts/{post_id}/dislike")
def toggle_dislike(request: Request, post_id: int, csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not post:
        return RedirectResponse("/", status_code=303)

    resp = RedirectResponse(f"/posts/{post_id}", status_code=303)
    if user:
        if not require_valid_csrf(user, csrf_token):
            return resp
        existing = db.execute(select(Dislike).where(Dislike.post_id == post.id, Dislike.user_id == user.id)).scalar_one_or_none()
        if existing:
            db.delete(existing)
        else:
            opposite = db.execute(select(Like).where(Like.post_id == post.id, Like.user_id == user.id)).scalar_one_or_none()
            if opposite:
                db.delete(opposite)
            db.add(Dislike(post_id=post.id, user_id=user.id))
    else:
        anon_key = request.cookies.get("anon_like_id") or secrets.token_urlsafe(24)
        existing = db.execute(select(AnonymousDislike).where(AnonymousDislike.post_id == post.id, AnonymousDislike.anon_key == anon_key)).scalar_one_or_none()
        if existing:
            db.delete(existing)
        else:
            opposite = db.execute(select(AnonymousLike).where(AnonymousLike.post_id == post.id, AnonymousLike.anon_key == anon_key)).scalar_one_or_none()
            if opposite:
                db.delete(opposite)
            db.add(AnonymousDislike(post_id=post.id, anon_key=anon_key))
        resp.set_cookie("anon_like_id", anon_key, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 365)
    db.commit()
    if not moderate_post(db, post):
        return RedirectResponse("/", status_code=303)
    return resp


@router.post("/posts/{post_id}/bookmark")
def toggle_bookmark(request: Request, post_id: int, csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not post or not require_valid_csrf(user, csrf_token):
        return RedirectResponse("/", status_code=303)
    existing = db.execute(select(Bookmark).where(Bookmark.post_id == post.id, Bookmark.user_id == user.id)).scalar_one_or_none()
    if existing:
        db.delete(existing)
    else:
        db.add(Bookmark(post_id=post.id, user_id=user.id))
    db.commit()
    return RedirectResponse(f"/posts/{post_id}", status_code=303)


@router.post("/posts/{post_id}/report")
def report_post(request: Request, post_id: int, reason: str = Form(...), csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = db.get(Post, post_id)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if post and require_valid_csrf(user, csrf_token) and reason.strip():
        db.add(Report(reason=reason.strip(), user_id=user.id, post_id=post.id))
        db.commit()
    return RedirectResponse(f"/posts/{post_id}", status_code=303)


@router.post("/comments/{comment_id}/report")
def report_comment(request: Request, comment_id: int, reason: str = Form(...), csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    comment = db.get(Comment, comment_id)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if comment and require_valid_csrf(user, csrf_token) and reason.strip():
        db.add(Report(reason=reason.strip(), user_id=user.id, comment_id=comment.id, post_id=comment.post_id))
        db.commit()
        return RedirectResponse(f"/posts/{comment.post_id}", status_code=303)
    return RedirectResponse("/", status_code=303)


@router.get("/admin/reports")
def admin_reports(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse("/", status_code=303)
    reports = db.execute(select(Report).order_by(desc(Report.created_at)).limit(100)).scalars().all()
    return render(request, "admin_reports.html", {"user": user, "reports": reports, "q": "", **categories_and_tags(db)})


@router.get("/admin/inquiries")
def admin_inquiries(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse("/", status_code=303)
    inquiries = db.execute(select(Inquiry).order_by(desc(Inquiry.created_at)).limit(100)).scalars().all()
    return render(request, "admin_inquiries.html", {
        "user": user,
        "inquiries": inquiries,
        "q": "",
        **categories_and_tags(db),
    })


@router.get("/admin/deleted-posts")
def admin_deleted_posts(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse("/", status_code=303)
    deleted_posts = db.execute(select(DeletedPost).order_by(desc(DeletedPost.deleted_at)).limit(100)).scalars().all()
    return render(request, "admin_deleted_posts.html", {
        "user": user,
        "deleted_posts": deleted_posts,
        "q": "",
        **categories_and_tags(db),
    })


@router.post("/admin/deleted-posts/{deleted_post_id}/restore")
def restore_deleted_post(request: Request, deleted_post_id: int, csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    deleted_post = db.get(DeletedPost, deleted_post_id)
    if not user or not user.is_admin or not deleted_post or not require_valid_csrf(user, csrf_token):
        return RedirectResponse("/admin/deleted-posts", status_code=303)
    if deleted_post.restored_post_id:
        return RedirectResponse(f"/posts/{deleted_post.restored_post_id}", status_code=303)

    category = db.execute(select(Category).where(Category.name == (deleted_post.category_name or DEFAULT_CATEGORY_NAME))).scalar_one_or_none()
    if not category:
        category = Category(name=deleted_post.category_name or DEFAULT_CATEGORY_NAME)
        db.add(category)
        db.flush()

    author = get_anonymous_writer(db)
    post = Post(
        title=deleted_post.title,
        content=deleted_post.content,
        image_url=deleted_post.image_url,
        source=deleted_post.source,
        status="published",
        author_id=author.id,
        category_id=category.id,
    )
    db.add(post)
    db.flush()
    sync_post_tags(db, post, deleted_post.tag_text or "")
    deleted_post.restored_post_id = post.id
    deleted_post.restored_at = utc_now()
    db.commit()
    return RedirectResponse(f"/posts/{post.id}", status_code=303)


@router.post("/admin/inquiries/{inquiry_id}/update")
def update_inquiry(
    request: Request,
    inquiry_id: int,
    status: str = Form("open"),
    admin_note: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    inquiry = db.get(Inquiry, inquiry_id)
    allowed_statuses = {"open", "answered", "closed"}
    if user and user.is_admin and inquiry and require_valid_csrf(user, csrf_token):
        inquiry.status = status if status in allowed_statuses else "open"
        inquiry.admin_note = admin_note.strip() or None
        db.commit()
    return RedirectResponse("/admin/inquiries", status_code=303)


@router.post("/admin/reports/{report_id}/resolve")
def resolve_report(request: Request, report_id: int, csrf_token: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    report = db.get(Report, report_id)
    if user and user.is_admin and report and require_valid_csrf(user, csrf_token):
        report.status = "resolved"
        db.commit()
    return RedirectResponse("/admin/reports", status_code=303)

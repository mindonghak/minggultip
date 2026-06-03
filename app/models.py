from sqlalchemy import Boolean, String, Integer, Text, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    profile_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    posts = relationship("Post", back_populates="author")
    comments = relationship("Comment", back_populates="user")
    likes = relationship("Like", back_populates="user")
    dislikes = relationship("Dislike", back_populates="user")
    bookmarks = relationship("Bookmark", back_populates="user")
    reports = relationship("Report", back_populates="user")
    inquiries = relationship("Inquiry", back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    posts = relationship("Post", back_populates="category")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(20), default="published", server_default="published")
    anonymous_author_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    promotion_deadline: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    author = relationship("User", back_populates="posts")
    category = relationship("Category", back_populates="posts")

    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("Like", back_populates="post", cascade="all, delete-orphan")
    anonymous_likes = relationship("AnonymousLike", back_populates="post", cascade="all, delete-orphan")
    dislikes = relationship("Dislike", back_populates="post", cascade="all, delete-orphan")
    anonymous_dislikes = relationship("AnonymousDislike", back_populates="post", cascade="all, delete-orphan")
    bookmarks = relationship("Bookmark", back_populates="post", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="post", cascade="all, delete-orphan")
    post_tags = relationship("PostTag", back_populates="post", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary="post_tags", back_populates="posts", viewonly=True)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))

    user = relationship("User", back_populates="comments")
    post = relationship("Post", back_populates="comments")
    reports = relationship("Report", back_populates="comment", cascade="all, delete-orphan")


class Like(Base):
    __tablename__ = "likes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="likes")
    post = relationship("Post", back_populates="likes")

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_user_post_like"),
    )


class AnonymousLike(Base):
    __tablename__ = "anonymous_likes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anon_key: Mapped[str] = mapped_column(String(100), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    post = relationship("Post", back_populates="anonymous_likes")

    __table_args__ = (
        UniqueConstraint("anon_key", "post_id", name="uq_anon_post_like"),
    )


class Dislike(Base):
    __tablename__ = "dislikes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="dislikes")
    post = relationship("Post", back_populates="dislikes")

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_user_post_dislike"),
    )


class AnonymousDislike(Base):
    __tablename__ = "anonymous_dislikes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anon_key: Mapped[str] = mapped_column(String(100), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    post = relationship("Post", back_populates="anonymous_dislikes")

    __table_args__ = (
        UniqueConstraint("anon_key", "post_id", name="uq_anon_post_dislike"),
    )


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="bookmarks")
    post = relationship("Post", back_populates="bookmarks")

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_user_post_bookmark"),
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    post_tags = relationship("PostTag", back_populates="tag", cascade="all, delete-orphan")
    posts = relationship("Post", secondary="post_tags", back_populates="tags", viewonly=True)


class PostTag(Base):
    __tablename__ = "post_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"))

    post = relationship("Post", back_populates="post_tags")
    tag = relationship("Tag", back_populates="post_tags")

    __table_args__ = (
        UniqueConstraint("post_id", "tag_id", name="uq_post_tag"),
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), nullable=True)
    comment_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id"), nullable=True)

    user = relationship("User", back_populates="reports")
    post = relationship("Post", back_populates="reports")
    comment = relationship("Comment", back_populates="reports")


class Inquiry(Base):
    __tablename__ = "inquiries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user = relationship("User", back_populates="inquiries")

import os
from datetime import timezone

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .db import SessionLocal, init_db
from .models import Post
from .routes import router

app = FastAPI(title="Minggultip")
SITE_URL = os.getenv("SITE_URL", "https://minggultip.onrender.com").rstrip("/")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": "minggultip"}


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    body = "\n".join([
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {SITE_URL}/sitemap.xml",
        "",
    ])
    return Response(content=body, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    urls = [f"""
  <url>
    <loc>{SITE_URL}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>"""]
    with SessionLocal() as db:
        posts = db.execute(select(Post).where(Post.status == "published").order_by(Post.id)).scalars().all()
        for post in posts:
            lastmod = ""
            if post.created_at:
                created_at = post.created_at
                if getattr(created_at, "tzinfo", None):
                    created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
                lastmod = f"\n    <lastmod>{created_at.date().isoformat()}</lastmod>"
            urls.append(f"""
  <url>
    <loc>{SITE_URL}/posts/{post.id}</loc>{lastmod}
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{''.join(urls)}
</urlset>
"""
    return Response(content=body, media_type="application/xml")


@app.on_event("startup")
def on_startup():
    init_db()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(router)

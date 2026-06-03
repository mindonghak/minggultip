import os
from datetime import timezone
from xml.sax.saxutils import escape as escape_xml

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


@app.get("/naverba4b1be3b5ac79d896842060a6b17504.html", include_in_schema=False)
def naver_site_verification():
    return Response(
        content="naver-site-verification: naverba4b1be3b5ac79d896842060a6b17504.html",
        media_type="text/html",
    )


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


@app.get("/rss.xml", include_in_schema=False)
def rss_xml():
    with SessionLocal() as db:
        posts = db.execute(
            select(Post).where(Post.status == "published").order_by(Post.created_at.desc()).limit(30)
        ).scalars().all()

    items = []
    for post in posts:
        pub_date = ""
        if post.created_at:
            created_at = post.created_at
            if getattr(created_at, "tzinfo", None):
                created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
            pub_date = created_at.strftime("%a, %d %b %Y %H:%M:%S +0000")
        description = post.content.replace("\n", " ")[:300]
        items.append(f"""
    <item>
      <title>{escape_xml(post.title)}</title>
      <link>{SITE_URL}/posts/{post.id}</link>
      <guid>{SITE_URL}/posts/{post.id}</guid>
      <description>{escape_xml(description)}</description>
      <pubDate>{pub_date}</pubDate>
    </item>""")

    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>민꿀팁</title>
    <link>{SITE_URL}/</link>
    <description>오늘 바로 써먹을 수 있는 생활 꿀팁과 정보를 나누는 커뮤니티입니다.</description>
    <language>ko</language>{''.join(items)}
  </channel>
</rss>
"""
    return Response(content=body, media_type="application/rss+xml")


@app.on_event("startup")
def on_startup():
    init_db()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(router)

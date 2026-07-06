"""
Backend da Biblioteca (Macro Desk Análises).

Antes, posts/comentários/curtidas/mídias ficavam só no localStorage/IndexedDB do
navegador — cada navegador via um conjunto de dados diferente. Este módulo dá
persistência real (SQLite + arquivos em disco) para que qualquer navegador ou
dispositivo que acesse o mesmo servidor veja o mesmo conteúdo.

Montado em unified_server.py via app.include_router(router).
"""
from __future__ import annotations

import mimetypes
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
MEDIA_DIR = DATA_DIR / "media"
DB_PATH = DATA_DIR / "biblioteca.db"
API_KEY_PATH = DATA_DIR / "api_key.txt"
DATA_DIR.mkdir(exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)


def _load_or_create_api_key() -> str:
    # Fica em biblioteca/data/ (no .gitignore — nunca é commitada, nunca aparece em
    # nenhuma resposta HTTP nem é embutida em nenhum HTML servido). O usuário digita
    # esse valor manualmente, uma vez por sessão de navegador, num prompt() para
    # "desbloquear" ações de escrita (publicar, curtir, comentar, editar, apagar);
    # o navegador guarda em sessionStorage só depois de digitado. Ler o valor: abrir
    # este arquivo diretamente no servidor.
    if API_KEY_PATH.exists():
        return API_KEY_PATH.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(12)
    API_KEY_PATH.write_text(key, encoding="utf-8")
    return key


API_KEY = _load_or_create_api_key()


def require_api_key(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(401, "Chave de API inválida ou ausente")


router = APIRouter(prefix="/api/biblioteca")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT NOT NULL,
            subcat TEXT DEFAULT '',
            title TEXT NOT NULL,
            text TEXT DEFAULT '',
            author TEXT DEFAULT 'Guilherme',
            ts INTEGER NOT NULL,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            pinned INTEGER DEFAULT 0,
            thumb_media_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            name TEXT,
            filename TEXT NOT NULL,
            thumb_src TEXT,
            order_idx INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            author TEXT,
            text TEXT,
            ts INTEGER
        );
        CREATE TABLE IF NOT EXISTS chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT,
            author TEXT,
            text TEXT,
            ts INTEGER
        );
        """
    )
    conn.commit()
    conn.close()


init_db()


def _media_dict(m: sqlite3.Row) -> dict:
    return {
        "id": m["id"],
        "type": m["type"],
        "name": m["name"],
        "url": f"/api/biblioteca/media/{m['filename']}",
        "thumbSrc": m["thumb_src"],
    }


def _post_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    media_rows = conn.execute(
        "SELECT * FROM media WHERE post_id=? ORDER BY order_idx, id", (row["id"],)
    ).fetchall()
    media = [_media_dict(m) for m in media_rows]
    comments_count = conn.execute(
        "SELECT COUNT(*) c FROM comments WHERE post_id=?", (row["id"],)
    ).fetchone()["c"]

    thumb_url = None
    thumb_is_video = False
    thumb_row = None
    if row["thumb_media_id"]:
        thumb_row = next((m for m in media_rows if m["id"] == row["thumb_media_id"]), None)
    if not thumb_row and media_rows:
        thumb_row = media_rows[0]
    if thumb_row:
        thumb_is_video = thumb_row["type"] == "video"
        thumb_url = thumb_row["thumb_src"] if thumb_is_video else f"/api/biblioteca/media/{thumb_row['filename']}"

    return {
        "id": row["id"],
        "section": row["section"],
        "subcat": row["subcat"],
        "title": row["title"],
        "text": row["text"],
        "author": row["author"],
        "ts": row["ts"],
        "views": row["views"],
        "likes": row["likes"],
        "comments": comments_count,
        "pinned": bool(row["pinned"]),
        "media": media,
        "thumbUrl": thumb_url,
        "thumbIsVideo": thumb_is_video,
    }


def _save_upload(file: UploadFile, data: bytes) -> str:
    ext = Path(file.filename or "").suffix or mimetypes.guess_extension(file.content_type or "") or ""
    filename = f"{uuid.uuid4().hex}{ext}"
    (MEDIA_DIR / filename).write_bytes(data)
    return filename


@router.get("/posts")
async def list_posts():
    conn = get_db()
    rows = conn.execute("SELECT * FROM posts ORDER BY ts DESC").fetchall()
    out = [_post_dict(conn, r) for r in rows]
    conn.close()
    return out


@router.get("/posts/{post_id}")
async def get_post(post_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Post não encontrado")
    out = _post_dict(conn, row)
    conn.close()
    return out


@router.post("/posts", dependencies=[Depends(require_api_key)])
async def create_post(
    section: str = Form(...),
    subcat: str = Form(""),
    title: str = Form(...),
    text: str = Form(""),
    author: str = Form("Guilherme"),
    pinned: bool = Form(False),
):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO posts (section, subcat, title, text, author, ts, pinned) VALUES (?,?,?,?,?,?,?)",
        (section, subcat, title, text, author, int(time.time() * 1000), int(pinned)),
    )
    conn.commit()
    post_id = cur.lastrowid
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    out = _post_dict(conn, row)
    conn.close()
    return out


@router.patch("/posts/{post_id}/text", dependencies=[Depends(require_api_key)])
async def update_post_text(post_id: int, text: str = Form(...)):
    conn = get_db()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Post não encontrado")
    conn.execute("UPDATE posts SET text=? WHERE id=?", (text, post_id))
    conn.commit()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    out = _post_dict(conn, row)
    conn.close()
    return out


@router.delete("/posts/{post_id}", dependencies=[Depends(require_api_key)])
async def delete_post(post_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Post não encontrado")
    media_rows = conn.execute("SELECT filename FROM media WHERE post_id=?", (post_id,)).fetchall()
    conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.commit()
    conn.close()
    for m in media_rows:
        f = MEDIA_DIR / m["filename"]
        if f.exists():
            f.unlink(missing_ok=True)
    return {"ok": True}


@router.post("/posts/{post_id}/media", dependencies=[Depends(require_api_key)])
async def add_media(post_id: int, file: UploadFile, thumb_src: Optional[str] = Form(None)):
    conn = get_db()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Post não encontrado")
    data = await file.read()
    filename = _save_upload(file, data)
    is_video = (file.content_type or "").startswith("video/")
    max_idx = conn.execute(
        "SELECT COALESCE(MAX(order_idx),-1) m FROM media WHERE post_id=?", (post_id,)
    ).fetchone()["m"]
    cur = conn.execute(
        "INSERT INTO media (post_id, type, name, filename, thumb_src, order_idx) VALUES (?,?,?,?,?,?)",
        (post_id, "video" if is_video else "image", file.filename, filename, thumb_src, max_idx + 1),
    )
    conn.commit()
    media_id = cur.lastrowid
    if row["thumb_media_id"] is None:
        conn.execute("UPDATE posts SET thumb_media_id=? WHERE id=?", (media_id, post_id))
        conn.commit()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    out = _post_dict(conn, row)
    conn.close()
    return out


@router.delete("/posts/{post_id}/media/{media_id}", dependencies=[Depends(require_api_key)])
async def remove_media(post_id: int, media_id: int):
    conn = get_db()
    m = conn.execute("SELECT * FROM media WHERE id=? AND post_id=?", (media_id, post_id)).fetchone()
    if not m:
        conn.close()
        raise HTTPException(404, "Mídia não encontrada")
    conn.execute("DELETE FROM media WHERE id=?", (media_id,))
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if row["thumb_media_id"] == media_id:
        nxt = conn.execute(
            "SELECT id FROM media WHERE post_id=? ORDER BY order_idx, id LIMIT 1", (post_id,)
        ).fetchone()
        conn.execute(
            "UPDATE posts SET thumb_media_id=? WHERE id=?", (nxt["id"] if nxt else None, post_id)
        )
    conn.commit()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    out = _post_dict(conn, row)
    conn.close()
    f = MEDIA_DIR / m["filename"]
    if f.exists():
        f.unlink(missing_ok=True)
    return out


@router.post("/posts/{post_id}/like", dependencies=[Depends(require_api_key)])
async def like_post(post_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Post não encontrado")
    conn.execute("UPDATE posts SET likes = likes + 1 WHERE id=?", (post_id,))
    conn.commit()
    likes = conn.execute("SELECT likes FROM posts WHERE id=?", (post_id,)).fetchone()["likes"]
    conn.close()
    return {"likes": likes}


@router.post("/posts/{post_id}/view")
async def view_post(post_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Post não encontrado")
    conn.execute("UPDATE posts SET views = views + 1 WHERE id=?", (post_id,))
    conn.commit()
    views = conn.execute("SELECT views FROM posts WHERE id=?", (post_id,)).fetchone()["views"]
    conn.close()
    return {"views": views}


@router.get("/posts/{post_id}/comments")
async def list_comments(post_id: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM comments WHERE post_id=? ORDER BY ts", (post_id,)
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "author": r["author"], "text": r["text"], "ts": r["ts"]} for r in rows]


@router.post("/posts/{post_id}/comments", dependencies=[Depends(require_api_key)])
async def add_comment(post_id: int, author: str = Form(...), text: str = Form(...)):
    conn = get_db()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Post não encontrado")
    ts = int(time.time() * 1000)
    cur = conn.execute(
        "INSERT INTO comments (post_id, author, text, ts) VALUES (?,?,?,?)",
        (post_id, author, text, ts),
    )
    conn.commit()
    comment_id = cur.lastrowid
    conn.close()
    return {"id": comment_id, "author": author, "text": text, "ts": ts}


@router.get("/chat")
async def list_chat(section: Optional[str] = None):
    conn = get_db()
    if section:
        rows = conn.execute(
            "SELECT * FROM chat WHERE section=? ORDER BY ts", (section,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM chat ORDER BY ts").fetchall()
    conn.close()
    return [
        {"id": r["id"], "section": r["section"], "author": r["author"], "text": r["text"], "ts": r["ts"]}
        for r in rows
    ]


@router.post("/chat", dependencies=[Depends(require_api_key)])
async def add_chat(section: str = Form(...), author: str = Form(...), text: str = Form(...)):
    conn = get_db()
    ts = int(time.time() * 1000)
    cur = conn.execute(
        "INSERT INTO chat (section, author, text, ts) VALUES (?,?,?,?)",
        (section, author, text, ts),
    )
    conn.commit()
    chat_id = cur.lastrowid
    conn.close()
    return {"id": chat_id, "section": section, "author": author, "text": text, "ts": ts}


@router.get("/media/{filename}")
async def get_media(filename: str):
    f = MEDIA_DIR / filename
    if not f.exists() or not f.is_file():
        raise HTTPException(404, "Arquivo não encontrado")
    mime, _ = mimetypes.guess_type(filename)
    return FileResponse(f, media_type=mime or "application/octet-stream")


@router.post("/import", dependencies=[Depends(require_api_key)])
async def import_bundle(payload: dict):
    """
    Importação única de um bundle exportado pela versão antiga (localStorage/IndexedDB).
    Espera o formato produzido por exportAllData() no frontend:
    { posts: [{..., media:[{type,name,thumbSrc,dataUrl}]}], comments: {postId: [...]}, chat: [...] }
    """
    import base64

    conn = get_db()
    imported = 0
    id_map = {}
    for p in payload.get("posts", []):
        cur = conn.execute(
            "INSERT INTO posts (section, subcat, title, text, author, ts, views, likes, pinned) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                p.get("section", "Geral"),
                p.get("subcat", ""),
                p.get("title", "Sem título"),
                p.get("text", ""),
                p.get("author", "Guilherme"),
                p.get("ts", int(time.time() * 1000)),
                p.get("views", 0),
                p.get("likes", 0),
                int(bool(p.get("pinned"))),
            ),
        )
        new_id = cur.lastrowid
        id_map[p.get("id")] = new_id
        thumb_media_id = None
        for idx, m in enumerate(p.get("media", [])):
            filename = None
            if m.get("dataUrl"):
                try:
                    header, b64 = m["dataUrl"].split(",", 1)
                    ext = mimetypes.guess_extension(header.split(";")[0].split(":")[1]) or ""
                    filename = f"{uuid.uuid4().hex}{ext}"
                    (MEDIA_DIR / filename).write_bytes(base64.b64decode(b64))
                except Exception:
                    filename = None
            if not filename:
                continue
            mcur = conn.execute(
                "INSERT INTO media (post_id, type, name, filename, thumb_src, order_idx) VALUES (?,?,?,?,?,?)",
                (new_id, m.get("type", "image"), m.get("name", ""), filename, m.get("thumbSrc"), idx),
            )
            if idx == 0:
                thumb_media_id = mcur.lastrowid
        if thumb_media_id:
            conn.execute("UPDATE posts SET thumb_media_id=? WHERE id=?", (thumb_media_id, new_id))
        imported += 1
    conn.commit()

    comments_in = payload.get("comments", {})
    comments_count = 0
    for old_pid, clist in comments_in.items():
        new_pid = id_map.get(int(old_pid)) if str(old_pid).lstrip("-").isdigit() else id_map.get(old_pid)
        if not new_pid:
            continue
        for c in clist:
            conn.execute(
                "INSERT INTO comments (post_id, author, text, ts) VALUES (?,?,?,?)",
                (new_pid, c.get("author", "Anônimo"), c.get("text", ""), c.get("ts", int(time.time() * 1000))),
            )
            comments_count += 1
    conn.commit()

    chat_in = payload.get("chat", [])
    chat_count = 0
    for c in chat_in:
        conn.execute(
            "INSERT INTO chat (section, author, text, ts) VALUES (?,?,?,?)",
            (c.get("section", "Geral"), c.get("author", "Anônimo"), c.get("text", ""), c.get("ts", int(time.time() * 1000))),
        )
        chat_count += 1
    conn.commit()
    conn.close()

    return JSONResponse(
        {"ok": True, "posts_imported": imported, "comments_imported": comments_count, "chat_imported": chat_count}
    )

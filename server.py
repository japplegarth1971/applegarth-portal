#!/usr/bin/env python3
"""Applegarth Health and Safety — Client Portal"""

import json
import os
import pathlib
import uuid
import mimetypes
from datetime import date, datetime

import bcrypt
import tornado.ioloop
import tornado.web

import db

BASE_DIR = pathlib.Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
PUBLIC_DIR = BASE_DIR / "public"

PORT = int(os.environ.get("PORT", 8080))


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def get_secret():
    secret_file = BASE_DIR / ".secret"
    if secret_file.exists():
        return secret_file.read_text().strip()
    secret = str(uuid.uuid4())
    secret_file.write_text(secret)
    return secret


def assessment_status(review_date_str):
    if not review_date_str:
        return "current"
    try:
        rd = date.fromisoformat(review_date_str)
        days = (rd - date.today()).days
        if days < 0:
            return "overdue"
        if days <= 90:
            return "due_soon"
        return "current"
    except Exception:
        return "current"


def calc_score(assessments, open_action_count):
    if not assessments:
        return 0
    pts = {"current": 100, "due_soon": 60, "overdue": 0}
    avg = sum(pts.get(a["status"], 0) for a in assessments) / len(assessments)
    penalty = min(open_action_count * 5, 25)
    return max(0, round(avg - penalty))


# ──────────────────────────────────────────────────────────────
# Base handler
# ──────────────────────────────────────────────────────────────

class BaseHandler(tornado.web.RequestHandler):

    def get_current_user(self):
        uid_bytes = self.get_secure_cookie("uid")
        if not uid_bytes:
            return None
        try:
            uid = int(uid_bytes.decode())
        except Exception:
            return None
        conn = db.get_db()
        row = conn.execute("SELECT * FROM users WHERE id = ?", [uid]).fetchone()
        conn.close()
        if row and row["approved"] == 1:
            return dict(row)
        return None

    def json_ok(self, data):
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(data, default=str))

    def json_error(self, msg, code=400):
        self.set_status(code)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"error": msg}))

    def auth_user(self):
        u = self.current_user
        if not u:
            self.json_error("Unauthorised", 401)
        return u

    def auth_admin(self):
        u = self.auth_user()
        if u and not u["is_admin"]:
            self.json_error("Forbidden", 403)
            return None
        return u


# ──────────────────────────────────────────────────────────────
# Static page handler (serves HTML, no redirect logic needed —
# each page checks /api/auth/me itself)
# ──────────────────────────────────────────────────────────────

class PageHandler(BaseHandler):
    def initialize(self, page):
        self.page = page

    def get(self):
        path = PUBLIC_DIR / self.page
        if not path.exists():
            self.send_error(404)
            return
        ext = path.suffix.lower()
        ct = {
            ".html": "text/html; charset=utf-8",
            ".json": "application/json",
            ".js":   "application/javascript",
        }.get(ext, "text/plain")
        self.set_header("Content-Type", ct)
        self.write(path.read_bytes())


# ──────────────────────────────────────────────────────────────
# Auth API
# ──────────────────────────────────────────────────────────────

class RegisterHandler(BaseHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
        except Exception:
            return self.json_error("Invalid JSON")

        required = ["email", "password", "name", "organisation", "org_type"]
        for f in required:
            if not data.get(f, "").strip():
                return self.json_error(f"'{f}' is required")

        email = data["email"].strip().lower()
        password = data["password"]

        if len(password) < 8:
            return self.json_error("Password must be at least 8 characters")

        conn = db.get_db()
        existing = conn.execute("SELECT id FROM users WHERE email = ?", [email]).fetchone()
        if existing:
            conn.close()
            return self.json_error("An account with that email already exists")

        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            conn.execute("""
                INSERT INTO users (email, password_hash, name, organisation, org_type, phone)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                email,
                pw_hash,
                data["name"].strip(),
                data["organisation"].strip(),
                data["org_type"].strip(),
                data.get("phone", "").strip(),
            ])
            conn.commit()
        except Exception as e:
            conn.close()
            return self.json_error("Registration failed")
        conn.close()
        self.json_ok({"message": "Registration submitted. You will receive access once approved."})


class LoginHandler(BaseHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
        except Exception:
            return self.json_error("Invalid JSON")

        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email or not password:
            return self.json_error("Email and password are required")

        conn = db.get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", [email]).fetchone()
        conn.close()

        if not user:
            return self.json_error("Invalid email or password", 401)

        if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return self.json_error("Invalid email or password", 401)

        if user["approved"] == 0:
            return self.json_error(
                "Your account is pending approval. Jeremy will be in touch soon.", 403
            )
        if user["approved"] == 2:
            return self.json_error(
                "Your registration was not approved. Please contact Jeremy directly.", 403
            )

        self.set_secure_cookie("uid", str(user["id"]), httponly=True, samesite="Strict")
        self.json_ok({
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "organisation": user["organisation"],
            "is_admin": bool(user["is_admin"]),
        })


class LogoutHandler(BaseHandler):
    def post(self):
        self.clear_cookie("uid")
        self.json_ok({"message": "Logged out"})


class MeHandler(BaseHandler):
    def get(self):
        u = self.current_user
        if not u:
            return self.json_error("Unauthorised", 401)
        self.json_ok({
            "id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "organisation": u["organisation"],
            "org_type": u["org_type"],
            "is_admin": bool(u["is_admin"]),
        })


# ──────────────────────────────────────────────────────────────
# Client API
# ──────────────────────────────────────────────────────────────

class ClientDashboardHandler(BaseHandler):
    def get(self):
        u = self.auth_user()
        if not u:
            return

        conn = db.get_db()

        raw = conn.execute(
            "SELECT * FROM assessments WHERE client_id = ? ORDER BY created_at DESC",
            [u["id"]]
        ).fetchall()

        assessments = []
        for a in raw:
            row = dict(a)
            row["status"] = assessment_status(row["review_date"])
            assessments.append(row)

        docs = conn.execute(
            "SELECT * FROM documents WHERE client_id = ? ORDER BY uploaded_at DESC LIMIT 5",
            [u["id"]]
        ).fetchall()

        open_actions = conn.execute(
            "SELECT COUNT(*) as n FROM action_items WHERE client_id = ? AND status = 'open'",
            [u["id"]]
        ).fetchone()["n"]

        due_count = sum(1 for a in assessments if a["status"] in ("due_soon", "overdue"))

        conn.close()

        self.json_ok({
            "score": calc_score(assessments, open_actions),
            "assessments": assessments,
            "recent_documents": [dict(d) for d in docs],
            "open_actions": open_actions,
            "due_count": due_count,
        })


class ClientDocumentsHandler(BaseHandler):
    def get(self):
        u = self.auth_user()
        if not u:
            return
        conn = db.get_db()
        docs = conn.execute(
            "SELECT * FROM documents WHERE client_id = ? ORDER BY uploaded_at DESC",
            [u["id"]]
        ).fetchall()
        conn.close()
        self.json_ok([dict(d) for d in docs])


class DocumentDownloadHandler(BaseHandler):
    def get(self, doc_id):
        u = self.auth_user()
        if not u:
            return

        conn = db.get_db()
        # clients can only download their own docs; admins can download any
        if u["is_admin"]:
            doc = conn.execute("SELECT * FROM documents WHERE id = ?", [doc_id]).fetchone()
        else:
            doc = conn.execute(
                "SELECT * FROM documents WHERE id = ? AND client_id = ?",
                [doc_id, u["id"]]
            ).fetchone()
        conn.close()

        if not doc:
            return self.json_error("Document not found", 404)

        fpath = UPLOAD_DIR / doc["filename"]
        if not fpath.exists():
            return self.json_error("File not found on server", 404)

        mime = mimetypes.guess_type(doc["original_name"])[0] or "application/octet-stream"
        self.set_header("Content-Type", mime)
        self.set_header(
            "Content-Disposition",
            f'attachment; filename="{doc["original_name"]}"'
        )
        self.write(fpath.read_bytes())


# ──────────────────────────────────────────────────────────────
# Admin API
# ──────────────────────────────────────────────────────────────

class AdminClientsHandler(BaseHandler):
    def get(self):
        u = self.auth_admin()
        if not u:
            return
        conn = db.get_db()
        clients = conn.execute(
            "SELECT * FROM users WHERE is_admin = 0 AND approved = 1 ORDER BY organisation"
        ).fetchall()
        result = []
        for c in clients:
            c = dict(c)
            assessments = conn.execute(
                "SELECT * FROM assessments WHERE client_id = ?", [c["id"]]
            ).fetchall()
            assessed = [dict(a) for a in assessments]
            for a in assessed:
                a["status"] = assessment_status(a["review_date"])
            open_actions = conn.execute(
                "SELECT COUNT(*) as n FROM action_items WHERE client_id = ? AND status='open'",
                [c["id"]]
            ).fetchone()["n"]
            c["score"] = calc_score(assessed, open_actions)
            c["assessment_count"] = len(assessed)
            c["due_count"] = sum(1 for a in assessed if a["status"] in ("due_soon", "overdue"))
            del c["password_hash"]
            result.append(c)
        conn.close()
        self.json_ok(result)


class AdminPendingHandler(BaseHandler):
    def get(self):
        u = self.auth_admin()
        if not u:
            return
        conn = db.get_db()
        rows = conn.execute(
            "SELECT id, email, name, organisation, org_type, phone, created_at "
            "FROM users WHERE is_admin = 0 AND approved = 0 ORDER BY created_at"
        ).fetchall()
        conn.close()
        self.json_ok([dict(r) for r in rows])


class AdminApproveHandler(BaseHandler):
    def post(self, client_id):
        u = self.auth_admin()
        if not u:
            return
        action = self.get_argument("action", "approve")
        approved_val = 1 if action == "approve" else 2
        conn = db.get_db()
        conn.execute(
            "UPDATE users SET approved = ? WHERE id = ? AND is_admin = 0",
            [approved_val, client_id]
        )
        conn.commit()
        conn.close()
        self.json_ok({"message": "Done"})


class AdminClientDetailHandler(BaseHandler):
    def get(self, client_id):
        u = self.auth_admin()
        if not u:
            return
        conn = db.get_db()
        client = conn.execute(
            "SELECT id, email, name, organisation, org_type, phone, created_at "
            "FROM users WHERE id = ? AND is_admin = 0 AND approved = 1",
            [client_id]
        ).fetchone()
        if not client:
            conn.close()
            return self.json_error("Client not found", 404)

        assessments = conn.execute(
            "SELECT * FROM assessments WHERE client_id = ? ORDER BY created_at DESC",
            [client_id]
        ).fetchall()
        assessed = [dict(a) for a in assessments]
        for a in assessed:
            a["status"] = assessment_status(a["review_date"])

        docs = conn.execute(
            "SELECT * FROM documents WHERE client_id = ? ORDER BY uploaded_at DESC",
            [client_id]
        ).fetchall()

        actions = conn.execute(
            "SELECT ai.*, a.title as assessment_title "
            "FROM action_items ai "
            "JOIN assessments a ON ai.assessment_id = a.id "
            "WHERE ai.client_id = ? ORDER BY ai.created_at DESC",
            [client_id]
        ).fetchall()

        open_actions = sum(1 for a in actions if a["status"] == "open")
        score = calc_score(assessed, open_actions)

        conn.close()
        self.json_ok({
            "client": dict(client),
            "assessments": assessed,
            "documents": [dict(d) for d in docs],
            "action_items": [dict(a) for a in actions],
            "score": score,
        })


class AdminAssessmentHandler(BaseHandler):
    def post(self):
        u = self.auth_admin()
        if not u:
            return
        try:
            data = json.loads(self.request.body)
        except Exception:
            return self.json_error("Invalid JSON")

        required = ["client_id", "title", "type"]
        for f in required:
            if not data.get(f):
                return self.json_error(f"'{f}' is required")

        conn = db.get_db()
        cur = conn.execute("""
            INSERT INTO assessments (client_id, title, type, completed_date, review_date, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            data["client_id"],
            data["title"],
            data["type"],
            data.get("completed_date") or None,
            data.get("review_date") or None,
            data.get("notes", ""),
        ])
        conn.commit()
        row = conn.execute(
            "SELECT * FROM assessments WHERE id = ?", [cur.lastrowid]
        ).fetchone()
        conn.close()
        row = dict(row)
        row["status"] = assessment_status(row["review_date"])
        self.json_ok(row)

    def put(self, assessment_id):
        u = self.auth_admin()
        if not u:
            return
        try:
            data = json.loads(self.request.body)
        except Exception:
            return self.json_error("Invalid JSON")

        conn = db.get_db()
        conn.execute("""
            UPDATE assessments
            SET title = ?, type = ?, completed_date = ?, review_date = ?, notes = ?
            WHERE id = ?
        """, [
            data.get("title"),
            data.get("type"),
            data.get("completed_date") or None,
            data.get("review_date") or None,
            data.get("notes", ""),
            assessment_id,
        ])
        conn.commit()
        row = conn.execute(
            "SELECT * FROM assessments WHERE id = ?", [assessment_id]
        ).fetchone()
        conn.close()
        row = dict(row)
        row["status"] = assessment_status(row["review_date"])
        self.json_ok(row)

    def delete(self, assessment_id):
        u = self.auth_admin()
        if not u:
            return
        conn = db.get_db()
        conn.execute("DELETE FROM assessments WHERE id = ?", [assessment_id])
        conn.commit()
        conn.close()
        self.json_ok({"message": "Deleted"})


class AdminUploadHandler(BaseHandler):
    def post(self):
        u = self.auth_admin()
        if not u:
            return

        client_id = self.get_body_argument("client_id", None)
        assessment_id = self.get_body_argument("assessment_id", None) or None
        files = self.request.files.get("file", [])

        if not client_id:
            return self.json_error("client_id is required")
        if not files:
            return self.json_error("No file uploaded")

        f = files[0]
        ext = pathlib.Path(f["filename"]).suffix
        stored_name = f"{uuid.uuid4()}{ext}"
        dest = UPLOAD_DIR / stored_name
        dest.write_bytes(f["body"])

        conn = db.get_db()
        cur = conn.execute("""
            INSERT INTO documents (client_id, assessment_id, filename, original_name, file_size)
            VALUES (?, ?, ?, ?, ?)
        """, [
            int(client_id),
            int(assessment_id) if assessment_id else None,
            stored_name,
            f["filename"],
            len(f["body"]),
        ])
        conn.commit()
        doc = conn.execute(
            "SELECT * FROM documents WHERE id = ?", [cur.lastrowid]
        ).fetchone()
        conn.close()
        self.json_ok(dict(doc))


class AdminDeleteDocumentHandler(BaseHandler):
    def delete(self, doc_id):
        u = self.auth_admin()
        if not u:
            return
        conn = db.get_db()
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", [doc_id]).fetchone()
        if not doc:
            conn.close()
            return self.json_error("Not found", 404)
        fpath = UPLOAD_DIR / doc["filename"]
        if fpath.exists():
            fpath.unlink()
        conn.execute("DELETE FROM documents WHERE id = ?", [doc_id])
        conn.commit()
        conn.close()
        self.json_ok({"message": "Deleted"})


class AdminActionHandler(BaseHandler):
    def post(self):
        u = self.auth_admin()
        if not u:
            return
        try:
            data = json.loads(self.request.body)
        except Exception:
            return self.json_error("Invalid JSON")

        for f in ["assessment_id", "client_id", "description"]:
            if not data.get(f):
                return self.json_error(f"'{f}' is required")

        conn = db.get_db()
        cur = conn.execute("""
            INSERT INTO action_items (assessment_id, client_id, description)
            VALUES (?, ?, ?)
        """, [data["assessment_id"], data["client_id"], data["description"]])
        conn.commit()
        row = conn.execute(
            "SELECT * FROM action_items WHERE id = ?", [cur.lastrowid]
        ).fetchone()
        conn.close()
        self.json_ok(dict(row))

    def put(self, item_id):
        u = self.auth_admin()
        if not u:
            return
        try:
            data = json.loads(self.request.body)
        except Exception:
            return self.json_error("Invalid JSON")

        conn = db.get_db()
        conn.execute(
            "UPDATE action_items SET status = ? WHERE id = ?",
            [data.get("status", "open"), item_id]
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM action_items WHERE id = ?", [item_id]
        ).fetchone()
        conn.close()
        self.json_ok(dict(row))


class AdminDeleteActionHandler(BaseHandler):
    def delete(self, item_id):
        u = self.auth_admin()
        if not u:
            return
        conn = db.get_db()
        conn.execute("DELETE FROM action_items WHERE id = ?", [item_id])
        conn.commit()
        conn.close()
        self.json_ok({"message": "Deleted"})


# ──────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────

def make_app():
    return tornado.web.Application(
        [
            # Pages
            (r"/",           PageHandler, {"page": "login.html"}),
            (r"/login",      PageHandler, {"page": "login.html"}),
            (r"/register",   PageHandler, {"page": "register.html"}),
            (r"/dashboard",  PageHandler, {"page": "dashboard.html"}),
            (r"/admin",      PageHandler, {"page": "admin.html"}),

            # Auth API
            (r"/api/auth/register", RegisterHandler),
            (r"/api/auth/login",    LoginHandler),
            (r"/api/auth/logout",   LogoutHandler),
            (r"/api/auth/me",       MeHandler),

            # Client API
            (r"/api/client/dashboard",                  ClientDashboardHandler),
            (r"/api/client/documents",                  ClientDocumentsHandler),
            (r"/api/client/documents/([0-9]+)/download",DocumentDownloadHandler),

            # Admin API
            (r"/api/admin/clients",                     AdminClientsHandler),
            (r"/api/admin/pending",                     AdminPendingHandler),
            (r"/api/admin/clients/([0-9]+)/approve",    AdminApproveHandler),
            (r"/api/admin/clients/([0-9]+)",            AdminClientDetailHandler),
            (r"/api/admin/assessments",                 AdminAssessmentHandler),
            (r"/api/admin/assessments/([0-9]+)",        AdminAssessmentHandler),
            (r"/api/admin/upload",                      AdminUploadHandler),
            (r"/api/admin/documents/([0-9]+)",          AdminDeleteDocumentHandler),
            (r"/api/admin/actions",                     AdminActionHandler),
            (r"/api/admin/actions/([0-9]+)",            AdminActionHandler),
            (r"/api/admin/actions/([0-9]+)/delete",     AdminDeleteActionHandler),

            # PWA files (must be at root scope)
            (r"/manifest\.json", PageHandler, {"page": "manifest.json"}),
            (r"/sw\.js",         PageHandler, {"page": "sw.js"}),

            # Static assets (CSS, images, etc.)
            (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": str(PUBLIC_DIR)}),
        ],
        cookie_secret=get_secret(),
        debug=False,
    )


if __name__ == "__main__":
    db.init_db()
    app = make_app()
    app.listen(PORT)
    print(f"Applegarth Portal running on http://localhost:{PORT}")
    print(f"Admin login: info@applegarthhealthandsafety.co.uk / admin123")
    print("IMPORTANT: Change the admin password after first login!")
    tornado.ioloop.IOLoop.current().start()

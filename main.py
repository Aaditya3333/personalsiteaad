from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, ValidationError
from contextlib import asynccontextmanager
import sqlite3
import bcrypt
from datetime import datetime
import secrets
import uvicorn
import logging
import os
import sys
import traceback

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        logger.info("Application starting up...")
        init_db()
        logger.info("Application startup completed successfully")
        yield
    except Exception as e:
        logger.error(f"Application startup failed: {str(e)}")
        raise
    finally:
        # Shutdown
        logger.info("Application shutting down...")

app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Database setup
def init_db():
    try:
        db_path = os.path.join(os.getcwd(), 'users.db')
        logger.info(f"Initializing database at: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                fullname TEXT NOT NULL,
                username TEXT UNIQUE,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Create admin users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                fullname TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT DEFAULT 'admin',
                department TEXT,
                security_question TEXT,
                security_answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Create sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                user_type TEXT, -- 'user' or 'admin'
                email TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create contacts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_resolved BOOLEAN DEFAULT 0
            )
        ''')

        # Create projects table (for dynamic filtering / backend CRUD)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                tags TEXT,
                image TEXT,
                demo_url TEXT,
                github_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create metrics table for visitor count
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                key TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            )
        ''')

        # Insert default visitor count record if missing
        cursor.execute('INSERT OR IGNORE INTO metrics (key, value) VALUES (?, ?)', ('visitor_count', 0))

        # Seed initial projects if table is empty
        cursor.execute('SELECT COUNT(*) FROM projects')
        project_count = cursor.fetchone()[0]
        if project_count == 0:
            cursor.executemany('''
                INSERT INTO projects (title, description, tags, image, demo_url, github_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', [
                ('E-Commerce Platform', 'Full-stack e-commerce solution with payment integration and admin dashboard.', 'React,Node.js,MongoDB', '/static/images/2.webp', '#', '#'),
                ('Task Management App', 'Collaborative task management tool with real-time updates and team features.', 'Vue.js,FastAPI,Redis', '/static/images/3.jpg', '#', '#'),
                ('Weather Dashboard', 'Real-time weather monitoring dashboard with data visualization and forecasts.', 'JavaScript,Chart.js,API', '/static/images/4.webp', '#', '#')
            ])

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except ValueError:
        return False

class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str

def get_db_connection():
    try:
        import os
        db_path = os.path.join(os.getcwd(), 'users.db')
        conn = sqlite3.connect(db_path)
        # Enable named column access for safe dict conversion
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise

def get_visitor_count() -> int:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM metrics WHERE key = ?', ('visitor_count',))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"Get visitor count error: {str(e)}")
        return 0

def increment_visitor():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE metrics SET value = value + 1 WHERE key = ?', ('visitor_count',))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Increment visitor error: {str(e)}")
        pass

def fetch_projects(tag: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if tag:
        cursor.execute('SELECT * FROM projects WHERE tags LIKE ? ORDER BY created_at DESC', (f'%{tag}%',))
    else:
        cursor.execute('SELECT * FROM projects ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    # Convert sqlite3.Row objects to plain dicts
    return [dict(row) for row in rows]

def add_contact(data: ContactCreate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO contacts (name, email, subject, message)
        VALUES (?, ?, ?, ?)
    ''', (data.name, data.email, data.subject, data.message))
    conn.commit()
    conn.close()

def fetch_unresolved_contacts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM contacts WHERE is_resolved = 0 ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return rows

def create_session(user_id: int, user_type: str, email: str) -> str:
    """Create a new session"""
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now().timestamp() + (24 * 60 * 60)  # 24 hours for users
    
    import os
    db_path = os.path.join(os.getcwd(), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO sessions (id, user_id, user_type, email, expires_at) VALUES (?, ?, ?, ?, ?)',
                 (session_id, user_id, user_type, email, datetime.fromtimestamp(expires_at)))
    conn.commit()
    conn.close()
    
    return session_id

def validate_session(session_id: str):
    """Validate session and return user info"""
    import os
    db_path = os.path.join(os.getcwd(), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sessions WHERE id = ? AND expires_at > ?', 
                 (session_id, datetime.now()))
    session = cursor.fetchone()
    conn.close()
    
    if session:
        return {
            'user_id': session[1],
            'user_type': session[2],
            'email': session[3]
        }
    return None

def delete_session(session_id: str):
    """Delete session"""
    import os
    db_path = os.path.join(os.getcwd(), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
    conn.commit()
    conn.close()

@app.get("/")
async def home(request: Request):
    try:
        increment_visitor()
        visitor_count = get_visitor_count()
        logger.info(f"visitor_count: {visitor_count}")
        return templates.TemplateResponse("index.html", context={"request": request, "visitor_count": visitor_count})
    except Exception as e:
        logger.exception("Home page error")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/about")
async def about(request: Request):
    try:
        visitor_count = get_visitor_count()
        return templates.TemplateResponse("about.html", context={"request": request, "visitor_count": visitor_count})
    except Exception as e:
        logger.exception("About page error")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/projects")
async def projects(request: Request, tag: str = None):
    try:
        visitor_count = get_visitor_count()
        projects = fetch_projects(tag)
        return templates.TemplateResponse(
            "projects.html",
            context={"request": request, "projects": projects, "visitor_count": visitor_count, "selected_tag": tag}
        )
    except Exception as e:
        logger.exception("Projects page error")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/blog")
async def blog(request: Request):
    try:
        visitor_count = get_visitor_count()
        return templates.TemplateResponse("blog.html", context={"request": request, "visitor_count": visitor_count})
    except Exception as e:
        logger.exception("Blog page error")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/contact")
async def contact(request: Request):
    try:
        visitor_count = get_visitor_count()
        return templates.TemplateResponse("contact.html", context={"request": request, "visitor_count": visitor_count})
    except Exception as e:
        logger.exception("Contact page error")
        raise HTTPException(status_code=500, detail="Internal server error")

# 404 Error Handler
@app.exception_handler(404)
async def not_found(request: Request, exc):
    try:
        return templates.TemplateResponse("404.html", context={"request": request}, status_code=404)
    except Exception as e:
        logger.exception("404 template error")
        return HTMLResponse("<h1>404 - Page Not Found</h1>", status_code=404)

# Global 500 error handler to render a friendly page instead of JSON
@app.exception_handler(500)
async def internal_error(request: Request, exc):
    try:
        # Log full traceback
        logger.exception("Unhandled server error")
        # Try to render a simple fallback response
        return HTMLResponse("<h1>500 - Internal Server Error</h1>", status_code=500)
    except Exception:
        # Last resort
        return HTMLResponse("<h1>500 - Internal Server Error</h1>", status_code=500)

# Simple health endpoint for Render
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

# Minimal page without templates to isolate rendering errors
@app.get("/plain")
async def plain():
    try:
        count = get_visitor_count()
        return HTMLResponse(f"<html><body><h1>OK</h1><p>Visitors: {count}</p></body></html>")
    except Exception:
        logger.exception("Plain page failed")
        return HTMLResponse("<h1>Error</h1>", status_code=500)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

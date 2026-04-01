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
    return rows


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

@app.get('/api/session')
async def api_get_session(request: Request):
    session_id = request.cookies.get('session_id')
    if not session_id:
        return {'user': None, 'admin': None}

    session = validate_session(session_id)
    if not session:
        return {'user': None, 'admin': None}

    import os
    db_path = os.path.join(os.getcwd(), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if session['user_type'] == 'user':
        cursor.execute('SELECT fullname, email, username FROM users WHERE id = ?', (session['user_id'],))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {'user': {'fullname': row[0], 'email': row[1], 'username': row[2]}, 'admin': None}
        return {'user': None, 'admin': None}

    if session['user_type'] == 'admin':
        cursor.execute('SELECT fullname, username, email FROM admin_users WHERE id = ?', (session['user_id'],))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {'user': None, 'admin': {'fullname': row[0], 'username': row[1], 'email': row[2]}}
        return {'user': None, 'admin': None}

    conn.close()
    return {'user': None, 'admin': None}

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
        return templates.TemplateResponse("index.html", {"request": request, "visitor_count": visitor_count})
    except Exception as e:
        logger.error(f"Home page error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/about")
async def about(request: Request):
    visitor_count = get_visitor_count()
    return templates.TemplateResponse("about.html", {"request": request, "visitor_count": visitor_count})

@app.get("/projects")
async def projects(request: Request, tag: str = None):
    visitor_count = get_visitor_count()
    project_rows = fetch_projects(tag)
    projects = [dict(p) for p in project_rows]
    return templates.TemplateResponse("projects.html", {"request": request, "projects": projects, "visitor_count": visitor_count, "selected_tag": tag})

@app.get("/blog")
async def blog(request: Request):
    visitor_count = get_visitor_count()
    # keep existing static blog list in template if no DB yet
    return templates.TemplateResponse("blog.html", {"request": request, "visitor_count": visitor_count})

@app.get("/blog/{slug}")
async def blog_detail(request: Request, slug: str):
    visitor_count = get_visitor_count()
    # Sample blog posts data
    blog_posts = {
        "building-scalable-apis": {
            "title": "Building Scalable APIs with FastAPI",
            "date": "March 15, 2024",
            "read_time": "5 min read",
            "image": "https://via.placeholder.com/800x400",
            "tags": ["Python", "FastAPI", "API"],
            "content": """
                <h2>Introduction</h2>
                <p>FastAPI is a modern, fast web framework for building APIs with Python. It's designed to be easy to use while providing high performance and automatic documentation.</p>
                
                <h2>Key Features</h2>
                <ul>
                    <li><strong>Fast Performance:</strong> Built on top of Starlette and Pydantic, offering incredible performance</li>
                    <li><strong>Automatic Documentation:</strong> OpenAPI and JSON Schema documentation automatically generated</li>
                    <li><strong>Type Hints:</strong> Full support for Python type hints</li>
                    <li><strong>Modern Python:</strong> Takes advantage of Python 3.6+ features</li>
                </ul>
                
                <h2>Getting Started</h2>
                <p>Installation is simple with pip:</p>
                <pre><code>pip install fastapi uvicorn</code></pre>
                
                <p>Here's a basic example:</p>
                <pre><code>from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    description: str = None
    price: float
    tax: float = None

@app.post("/items/")
async def create_item(item: Item):
    return item</code></pre>
                
                <h2>Best Practices</h2>
                <p>When building scalable APIs with FastAPI, consider these best practices:</p>
                <ol>
                    <li>Use proper dependency injection</li>
                    <li>Implement proper error handling</li>
                    <li>Add authentication and authorization</li>
                    <li>Use background tasks for long-running operations</li>
                    <li>Implement proper logging</li>
                </ol>
                
                <h2>Conclusion</h2>
                <p>FastAPI provides an excellent foundation for building scalable, high-performance APIs. With its automatic documentation and type safety, it's an excellent choice for modern web development.</p>
            """
        },
        "modern-css-techniques": {
            "title": "Modern CSS Techniques for 2024",
            "date": "March 10, 2024",
            "read_time": "8 min read",
            "image": "https://via.placeholder.com/800x400",
            "tags": ["CSS", "Design", "Frontend"],
            "content": """
                <h2>The Evolution of CSS</h2>
                <p>CSS has evolved tremendously over past few years. Modern CSS provides powerful features that make complex layouts and animations easier than ever before.</p>
                
                <h2>Container Queries</h2>
                <p>Container queries allow you to apply styles based on size of a container element rather than viewport:</p>
                <pre><code>@container (min-width: 400px) {
  .card {
    display: flex;
    flex-direction: row;
  }
</code></pre>
                
                <h2>CSS Grid and Flexbox</h2>
                <p>These layout systems have become essential for modern web design. Grid is perfect for two-dimensional layouts, while Flexbox excels at one-dimensional layouts.</p>
                
                <h2>Custom Properties</h2>
                <p>CSS variables make it easy to create maintainable and dynamic styles:</p>
                <pre><code>:root {
  --primary-color: #667eea;
  --secondary-color: #764ba2;
}

.button {
  background: var(--primary-color);
  color: white;
}</code></pre>
                
                <h2>Conclusion</h2>
                <p>Modern CSS provides powerful tools for creating beautiful, responsive designs. Stay updated with latest features to improve your development workflow.</p>
            """
        },
        "database-optimization": {
            "title": "Database Optimization Strategies",
            "date": "March 5, 2024",
            "read_time": "6 min read",
            "image": "https://via.placeholder.com/800x400",
            "tags": ["Database", "Performance", "SQL"],
            "content": """
                <h2>Why Database Optimization Matters</h2>
                <p>Database performance is crucial for application responsiveness and user experience. Slow queries can significantly impact your application's performance.</p>
                
                <h2>Indexing Strategies</h2>
                <p>Proper indexing is one of most effective ways to improve query performance:</p>
                <ul>
                    <li>Create indexes on frequently queried columns</li>
                    <li>Use composite indexes for multi-column queries</li>
                    <li>Avoid over-indexing as it can slow down writes</li>
                </ul>
                
                <h2>Query Optimization</h2>
                <p>Write efficient queries by:</p>
                <ol>
                    <li>Using EXPLAIN to analyze query execution plans</li>
                    <li>Avoiding SELECT * queries</li>
                    <li>Using appropriate JOIN types</li>
                    <li>Implementing query caching</li>
                </ol>
                
                <h2>Connection Pooling</h2>
                <p>Implement connection pooling to reduce the overhead of establishing new connections for each query.</p>
                
                <h2>Conclusion</h2>
                <p>Database optimization is an ongoing process. Regular monitoring and optimization ensure your application performs at its best.</p>
            """
        }
    }
    
    # Get blog post or return 404
    post = blog_posts.get(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    return templates.TemplateResponse("blog-detail.html", {"request": request, "visitor_count": visitor_count, **post})

@app.get("/analytics")
async def analytics(request: Request):
    visitor_count = get_visitor_count()
    return templates.TemplateResponse("analytics.html", {"request": request, "visitor_count": visitor_count})

@app.get("/chatbot")
async def chatbot(request: Request):
    visitor_count = get_visitor_count()
    return templates.TemplateResponse("chatbot.html", {"request": request, "visitor_count": visitor_count})

@app.get("/dashboard")
async def dashboard(request: Request):
    session_id = request.cookies.get("session_id")
    session = validate_session(session_id) if session_id else None
    
    if not session or session['user_type'] != 'user':
        return RedirectResponse(url="/login", status_code=303)
    
    # Get user data
    import os
    db_path = os.path.join(os.getcwd(), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT fullname, email, created_at FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": {
            "fullname": user[0],
            "email": user[1],
            "created_at": user[2]
        }
    })

@app.get("/admin")
async def admin(request: Request):
    session_id = request.cookies.get("session_id")
    session = validate_session(session_id) if session_id else None

    if not session or session['user_type'] != 'admin':
        return RedirectResponse(url="/admin-login", status_code=303)

    # Get admin data
    import os
    db_path = os.path.join(os.getcwd(), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT fullname, username, role, department FROM admin_users WHERE id = ?', (session['user_id'],))
    admin = cursor.fetchone()
    conn.close()

    visitor_count = get_visitor_count()
    contacts = fetch_unresolved_contacts()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "admin": {
            "fullname": admin[0],
            "username": admin[1],
            "role": admin[2],
            "department": admin[3]
        },
        "visitor_count": visitor_count,
        "contacts": [dict(c) for c in contacts]
    })

@app.get("/admin/contacts")
async def admin_contacts(request: Request):
    session_id = request.cookies.get("session_id")
    session = validate_session(session_id) if session_id else None

    if not session or session['user_type'] != 'admin':
        return RedirectResponse(url="/admin-login", status_code=303)

    visitor_count = get_visitor_count()
    contacts = fetch_unresolved_contacts()

    return templates.TemplateResponse("admin-contacts.html", {
        "request": request,
        "visitor_count": visitor_count,
        "contacts": [dict(c) for c in contacts]
    })

@app.get("/settings")
async def settings(request: Request):
    session_id = request.cookies.get("session_id")
    session = validate_session(session_id) if session_id else None
    
    if not session:
        return RedirectResponse(url="/login", status_code=303)
    
    # Get user data based on session type
    import os
    db_path = os.path.join(os.getcwd(), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    if session['user_type'] == 'admin':
        cursor.execute('SELECT fullname, email, role FROM admin_users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
    else:
        cursor.execute('SELECT fullname, email FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
    
    conn.close()
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": {
            "fullname": user[0],
            "email": user[1],
            "role": user[2] if len(user) > 2 else None
        }
    })

@app.get("/register")
async def register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/login")
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/admin-login")
async def admin_login(request: Request):
    return templates.TemplateResponse("admin-login.html", {"request": request})

@app.post("/register")
async def register_user(request: Request):
    form = await request.form()
    email = form.get('email')
    password = form.get('password')
    confirm_password = form.get('confirm-password')
    fullname = form.get('fullname')
    username = form.get('username')
    terms = form.get('terms') == 'on'
    newsletter = form.get('newsletter') == 'on'
    
    # Validation
    if not all([email, password, fullname, username]):
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "All fields are required"
        })
    
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Passwords do not match"
        })
    
    if not terms:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "You must accept the terms and conditions"
        })
    
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Password must be at least 6 characters long"
        })
    
    try:
        import os
        db_path = os.path.join(os.getcwd(), 'users.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if email already exists
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Email already registered"
            })
        
        # Check if username already exists
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            conn.close()
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Username already taken"
            })
        
        # Insert new user
        cursor.execute('''
            INSERT INTO users (email, password, fullname, username) 
            VALUES (?, ?, ?, ?)
        ''', (email, hash_password(password), fullname, username))
        
        conn.commit()
        conn.close()
        
        return templates.TemplateResponse("login.html", {
            "request": request,
            "success": "Registration successful! Please login."
        })
        
    except Exception as e:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": f"Registration failed: {str(e)}"
        })

@app.post("/login")
async def login_user(request: Request):
    form = await request.form()
    email = form.get('email')
    password = form.get('password')
    
    import os
    db_path = os.path.join(os.getcwd(), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check user credentials
    cursor.execute('SELECT id, email, password, fullname FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    
    if user and verify_password(password, user[2]):
        # Create session
        session_id = create_session(user[0], 'user', user[1])
        
        # Update last login
        cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', 
                     (datetime.now(), user[0]))
        conn.commit()
        conn.close()
        
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=86400)  # 24 hours
        return response
    else:
        conn.close()
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password"
        })

@app.post("/admin-login")
async def admin_login_user(request: Request):
    form = await request.form()
    username = form.get('username')
    password = form.get('password')
    
    import os
    db_path = os.path.join(os.getcwd(), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check admin credentials
    cursor.execute('SELECT id, username, password, fullname FROM admin_users WHERE username = ?', (username,))
    admin = cursor.fetchone()
    
    if admin and verify_password(password, admin[2]):
        # Create session
        session_id = create_session(admin[0], 'admin', admin[1])
        
        # Update last login
        cursor.execute('UPDATE admin_users SET last_login = ? WHERE id = ?', 
                     (datetime.now(), admin[0]))
        conn.commit()
        conn.close()
        
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=28800)  # 8 hours
        return response
    else:
        conn.close()
        return templates.TemplateResponse("admin-login.html", {
            "request": request,
            "error": "Invalid admin credentials"
        })

@app.post("/admin-register")
async def admin_register_user(request: Request):
    form = await request.form()
    admin_code = form.get('admin-code')
    fullname = form.get('fullname')
    email = form.get('email')
    username = form.get('username')
    password = form.get('password')
    role = form.get('role')
    security_question = form.get('security-question')
    security_answer = form.get('security-answer')
    
    # Validate admin code
    if admin_code != 'ADMIN2024':
        return templates.TemplateResponse("admin-register.html", {
            "request": request,
            "error": "Invalid admin registration code"
        })
    
    try:
        import os
        db_path = os.path.join(os.getcwd(), 'users.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if username already exists
        cursor.execute('SELECT id FROM admin_users WHERE username = ?', (username,))
        if cursor.fetchone():
            conn.close()
            return templates.TemplateResponse("admin-register.html", {
                "request": request,
                "error": "Username already exists"
            })
        
        # Insert new admin
        cursor.execute('''
            INSERT INTO admin_users (username, password, fullname, email, role, security_question, security_answer) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (username, hash_password(password), fullname, email, role, security_question, security_answer))
        
        conn.commit()
        conn.close()
        
        return templates.TemplateResponse("admin-login.html", {
            "request": request,
            "success": "Admin registration successful! Please login."
        })
        
    except Exception as e:
        return templates.TemplateResponse("admin-register.html", {
            "request": request,
            "error": f"Registration failed: {str(e)}"
        })

@app.post("/logout")
async def logout_user(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(session_id)
    
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session_id")
    return response

@app.get("/admin-register")
async def admin_register(request: Request):
    return templates.TemplateResponse("admin-register.html", {"request": request})

@app.get("/contact")
async def contact(request: Request):
    visitor_count = get_visitor_count()
    return templates.TemplateResponse("contact.html", {"request": request, "visitor_count": visitor_count})

@app.post("/contact")
async def contact_submit(request: Request, name: str = Form(...), email: str = Form(...), subject: str = Form(...), message: str = Form(...)):
    visitor_count = get_visitor_count()
    try:
        contact_data = ContactCreate(name=name, email=email, subject=subject, message=message)
        add_contact(contact_data)
        return templates.TemplateResponse("contact.html", {
            "request": request,
            "visitor_count": visitor_count,
            "success": "Thank you! Your message has been received. I'll get back to you soon."
        })
    except ValidationError as exc:
        return templates.TemplateResponse("contact.html", {
            "request": request,
            "visitor_count": visitor_count,
            "error": "Please correct the form fields and try again.",
            "validation_errors": exc.errors()
        })
    except Exception as exc:
        return templates.TemplateResponse("contact.html", {
            "request": request,
            "visitor_count": visitor_count,
            "error": f"We could not submit your contact message: {str(exc)}"
        })

# 404 Error Handler
@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)

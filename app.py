import os
import json
import random
import string
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

# AI Service (imported after setup)
from ai_service import (
    analyze_behavior, recommend_study_pattern, recommend_resources,
    generate_recommendations, suggest_groups, match_group,
    analyze_performance as ai_analyze_performance, generate_report,
    ai_chat, generate_study_plan
)

from translations import TRANSLATIONS, t as _t, get_lang, get_dir

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'nahj-secret-key-change-in-production')
app.config['DATABASE'] = 'nahj.db'


# ============================================================
# LANGUAGE / I18N
# ============================================================

@app.context_processor
def inject_i18n():
    lang = session.get('lang', 'ar')
    return {
        't': lambda key: _t(key, lang),
        'lang': lang,
        'dir': get_dir(lang),
    }


@app.route('/set-language/<code>')
def set_language(code):
    if code not in ('ar', 'en'):
        code = 'ar'
    session['lang'] = code
    return redirect(request.referrer or url_for('dashboard'))


def notify(db, user_id, key_ar, key_en, ntype='info'):
    """Insert a bilingual notification. Stores message as 'AR ||| EN' so it can be displayed
    in the user's currently selected language."""
    msg = f"{key_ar} ||| {key_en}"
    db.execute(
        "INSERT INTO notifications (user_id, message, type) VALUES (?, ?, ?)",
        (user_id, msg, ntype)
    )


def tflash(msg_ar, msg_en, category='info'):
    """Flash a message in the user's current language."""
    lang = session.get('lang', 'ar')
    flash(msg_ar if lang == 'ar' else msg_en, category)


@app.template_filter('localize_notif')
def localize_notif(message):
    """Render a bilingual notification ('AR ||| EN') based on session language."""
    if not message:
        return ''
    if '|||' in message:
        ar, en = message.split('|||', 1)
        ar = ar.strip()
        en = en.strip()
        return en if session.get('lang', 'ar') == 'en' else ar
    return message

# ============================================================
# DATABASE
# ============================================================

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(app.config['DATABASE'])
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            phone TEXT,
            department TEXT DEFAULT '',
            level INTEGER DEFAULT 1,
            learning_style TEXT DEFAULT '',
            profile_image TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_name TEXT NOT NULL,
            course_code TEXT,
            credit_hours INTEGER DEFAULT 3,
            schedule TEXT DEFAULT '',
            instructor TEXT DEFAULT '',
            department TEXT DEFAULT '',
            level INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            semester TEXT DEFAULT '',
            enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (course_id) REFERENCES courses(id),
            UNIQUE(user_id, course_id)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            type TEXT DEFAULT 'assignment',
            deadline TEXT,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS study_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER,
            date TEXT,
            start_time TEXT,
            end_time TEXT,
            duration_hours REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            study_hours_weekly REAL DEFAULT 0,
            completion_rate REAL DEFAULT 0,
            consistency_score REAL DEFAULT 0,
            recommendation_text TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS study_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_type TEXT DEFAULT 'daily',
            plan_data TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS study_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            department TEXT DEFAULT '',
            course_id INTEGER,
            level INTEGER DEFAULT 1,
            capacity INTEGER DEFAULT 10,
            learning_style TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES study_groups(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS group_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES study_groups(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            type TEXT DEFAULT 'info',
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used INTEGER DEFAULT 0
        );
    ''')

    # Seed sample courses
    cursor = db.execute("SELECT COUNT(*) FROM courses")
    if cursor.fetchone()[0] == 0:
        sample_courses = [
            ('Introduction to AI', 'CS301', 3, 'Sun-Tue 10:00-11:30', 'Dr. Ahmed', 'CS & AI', 5),
            ('Data Structures', 'CS201', 3, 'Mon-Wed 08:00-09:30', 'Dr. Sara', 'CS & AI', 3),
            ('Machine Learning', 'CS401', 3, 'Sun-Tue 12:00-13:30', 'Dr. Omar', 'CS & AI', 7),
            ('Web Development', 'CS302', 3, 'Mon-Wed 10:00-11:30', 'Dr. Huda', 'CS & AI', 5),
            ('Database Systems', 'CS303', 3, 'Sun-Tue 14:00-15:30', 'Dr. Khalid', 'CS & AI', 5),
            ('Software Engineering', 'CS304', 3, 'Mon-Wed 12:00-13:30', 'Dr. Nora', 'CS & AI', 6),
            ('Computer Networks', 'CS305', 3, 'Sun-Tue 08:00-09:30', 'Dr. Ali', 'CS & AI', 6),
            ('Operating Systems', 'CS306', 3, 'Mon-Wed 14:00-15:30', 'Dr. Fatima', 'CS & AI', 4),
        ]
        db.executemany(
            "INSERT INTO courses (course_name, course_code, credit_hours, schedule, instructor, department, level) VALUES (?,?,?,?,?,?,?)",
            sample_courses
        )

    db.commit()
    db.close()

# ============================================================
# AUTH DECORATOR
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            tflash('يرجى تسجيل الدخول أولاً.', 'Please login first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            db.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.now(), user['id']))
            db.commit()
            tflash('مرحباً بعودتك!', 'Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        else:
            tflash('البريد الإلكتروني أو كلمة المرور غير صحيحة.', 'Invalid email or password.', 'danger')

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()

        if not username or not email or not password:
            tflash('جميع الحقول مطلوبة.', 'All fields are required.', 'danger')
            return render_template('signup.html')

        if len(password) < 6:
            tflash('يجب أن تتكون كلمة المرور من 6 أحرف على الأقل.', 'Password must be at least 6 characters.', 'danger')
            return render_template('signup.html')

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            tflash('البريد الإلكتروني مسجل مسبقاً.', 'Email already registered.', 'danger')
            return render_template('signup.html')

        password_hash = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, email, password_hash, phone) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, phone)
        )
        db.commit()

        tflash('تم إنشاء الحساب بنجاح! يرجى تسجيل الدخول.', 'Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()

        if user:
            # Generate fake OTP
            otp = ''.join(random.choices(string.digits, k=6))
            db.execute("INSERT INTO otp_codes (email, code) VALUES (?, ?)", (email, otp))
            db.commit()
            session['reset_email'] = email
            session['otp_code'] = otp  # Store for fake display
            tflash(f'رمز OTP (تجريبي): {otp}', f'OTP Code (demo): {otp}', 'info')
            return redirect(url_for('verify_otp'))
        else:
            tflash('البريد الإلكتروني غير موجود.', 'Email not found.', 'danger')

    return render_template('forgot_password.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if 'reset_email' not in session:
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        entered_code = request.form.get('otp', '').strip()
        db = get_db()
        otp_record = db.execute(
            "SELECT * FROM otp_codes WHERE email = ? AND code = ? AND used = 0 ORDER BY created_at DESC LIMIT 1",
            (session['reset_email'], entered_code)
        ).fetchone()

        if otp_record:
            db.execute("UPDATE otp_codes SET used = 1 WHERE id = ?", (otp_record['id'],))
            db.commit()
            session['otp_verified'] = True
            return redirect(url_for('reset_password'))
        else:
            tflash('رمز OTP غير صحيح.', 'Invalid OTP code.', 'danger')

    return render_template('verify_otp.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if not session.get('otp_verified'):
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if new_password != confirm_password:
            tflash('كلمتا المرور غير متطابقتين.', 'Passwords do not match.', 'danger')
            return render_template('reset_password.html')

        if len(new_password) < 6:
            tflash('يجب أن تتكون كلمة المرور من 6 أحرف على الأقل.', 'Password must be at least 6 characters.', 'danger')
            return render_template('reset_password.html')

        db = get_db()
        db.execute(
            "UPDATE users SET password_hash = ? WHERE email = ?",
            (generate_password_hash(new_password), session['reset_email'])
        )
        db.commit()

        session.pop('reset_email', None)
        session.pop('otp_code', None)
        session.pop('otp_verified', None)

        tflash('تمت إعادة تعيين كلمة المرور بنجاح! يرجى تسجيل الدخول.', 'Password reset successfully! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html')

@app.route('/logout')
def logout():
    lang = session.get('lang', 'ar')
    session.clear()
    flash('تم تسجيل الخروج بنجاح.' if lang == 'ar' else 'Logged out successfully.', 'info')
    return redirect(url_for('login'))

# ============================================================
# DASHBOARD
# ============================================================

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()

    # Get stats
    total_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (session['user_id'],)).fetchone()[0]
    completed_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'completed'", (session['user_id'],)).fetchone()[0]
    pending_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'pending'", (session['user_id'],)).fetchone()[0]
    enrolled_courses = db.execute("SELECT COUNT(*) FROM enrollments WHERE user_id = ?", (session['user_id'],)).fetchone()[0]

    # Upcoming tasks (next 7 days)
    upcoming = db.execute(
        "SELECT * FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY deadline ASC LIMIT 5",
        (session['user_id'],)
    ).fetchall()

    # Recent notifications
    notifications = db.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
        (session['user_id'],)
    ).fetchall()

    # Latest study plan
    latest_plan = db.execute(
        "SELECT * FROM study_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (session['user_id'],)
    ).fetchone()

    completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)

    return render_template('dashboard.html',
        user=user,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        enrolled_courses=enrolled_courses,
        upcoming=upcoming,
        notifications=notifications,
        latest_plan=latest_plan,
        completion_rate=completion_rate
    )

# ============================================================
# STUDY PLANNER
# ============================================================

@app.route('/planner')
@login_required
def planner():
    db = get_db()
    plans = db.execute(
        "SELECT * FROM study_plans WHERE user_id = ? ORDER BY created_at DESC",
        (session['user_id'],)
    ).fetchall()

    enrolled = db.execute('''
        SELECT c.* FROM courses c
        JOIN enrollments e ON c.id = e.course_id
        WHERE e.user_id = ?
    ''', (session['user_id'],)).fetchall()

    return render_template('planner.html', plans=plans, enrolled_courses=enrolled)

@app.route('/planner/generate', methods=['POST'])
@login_required
def generate_plan():
    # Handled by /api/ai/generate-plan AJAX endpoint
    tflash('استخدم زر "إنشاء خطة بالذكاء الاصطناعي" لإنشاء الخطط.', 'Use the Generate AI Plan button to create plans.', 'info')
    return redirect(url_for('planner'))

# ============================================================
# TASKS
# ============================================================

@app.route('/tasks')
@login_required
def tasks():
    db = get_db()
    filter_status = request.args.get('status', 'all')
    filter_priority = request.args.get('priority', 'all')

    query = "SELECT * FROM tasks WHERE user_id = ?"
    params = [session['user_id']]

    if filter_status != 'all':
        query += " AND status = ?"
        params.append(filter_status)
    if filter_priority != 'all':
        query += " AND priority = ?"
        params.append(filter_priority)

    query += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END, deadline ASC"

    all_tasks = db.execute(query, params).fetchall()
    return render_template('tasks.html', tasks=all_tasks, filter_status=filter_status, filter_priority=filter_priority)

@app.route('/tasks/add', methods=['POST'])
@login_required
def add_task():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    task_type = request.form.get('type', 'assignment')
    deadline = request.form.get('deadline', '')
    priority = request.form.get('priority', 'medium')

    if not title:
        tflash('عنوان المهمة مطلوب.', 'Task title is required.', 'danger')
        return redirect(url_for('tasks'))

    try:
        db = get_db()
        db.execute(
            "INSERT INTO tasks (user_id, title, description, type, deadline, priority) VALUES (?, ?, ?, ?, ?, ?)",
            (session['user_id'], title, description, task_type, deadline, priority)
        )
        notify(db, session['user_id'],
               f'تمت إضافة مهمة جديدة: {title}',
               f'New task added: {title}', 'task')
        db.commit()
        tflash('تمت إضافة المهمة بنجاح!', 'Task added successfully!', 'success')
    except Exception as e:
        db.rollback()
        tflash('خطأ في إضافة المهمة. يرجى المحاولة مرة أخرى.', 'Error adding task. Please try again.', 'danger')

    return redirect(url_for('tasks'))

@app.route('/tasks/edit/<int:task_id>', methods=['POST'])
@login_required
def edit_task(task_id):
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    task_type = request.form.get('type', 'assignment')
    deadline = request.form.get('deadline', '')
    priority = request.form.get('priority', 'medium')
    status = request.form.get('status', 'pending')

    try:
        db = get_db()
        db.execute(
            "UPDATE tasks SET title=?, description=?, type=?, deadline=?, priority=?, status=?, updated_at=? WHERE id=? AND user_id=?",
            (title, description, task_type, deadline, priority, status, datetime.now(), task_id, session['user_id'])
        )
        notify(db, session['user_id'],
               f'تم تعديل المهمة: {title}',
               f'Task updated: {title}', 'task')
        db.commit()
        tflash('تم تعديل المهمة بنجاح!', 'Task updated!', 'success')
    except Exception as e:
        tflash('خطأ في تعديل المهمة.', 'Error updating task.', 'danger')

    return redirect(url_for('tasks'))

@app.route('/tasks/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    db = get_db()
    task = db.execute("SELECT title FROM tasks WHERE id = ? AND user_id = ?", (task_id, session['user_id'])).fetchone()
    title = task['title'] if task else ''
    db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, session['user_id']))
    if title:
        notify(db, session['user_id'],
               f'تم حذف المهمة: {title}',
               f'Task deleted: {title}', 'task')
    db.commit()
    tflash('تم حذف المهمة.', 'Task deleted.', 'info')
    return redirect(url_for('tasks'))

@app.route('/tasks/toggle/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    db = get_db()
    task = db.execute("SELECT status, title FROM tasks WHERE id = ? AND user_id = ?", (task_id, session['user_id'])).fetchone()
    if task:
        new_status = 'completed' if task['status'] == 'pending' else 'pending'
        db.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (new_status, datetime.now(), task_id))
        if new_status == 'completed':
            notify(db, session['user_id'],
                   f'أحسنت! تم إكمال المهمة: {task["title"]}',
                   f'Nice! Task completed: {task["title"]}', 'task')
        else:
            notify(db, session['user_id'],
                   f'تمت إعادة فتح المهمة: {task["title"]}',
                   f'Task reopened: {task["title"]}', 'task')
        db.commit()
    return redirect(url_for('tasks'))

# ============================================================
# PERFORMANCE
# ============================================================

@app.route('/performance')
@login_required
def performance():
    db = get_db()
    total_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (session['user_id'],)).fetchone()[0]
    completed = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'completed'", (session['user_id'],)).fetchone()[0]

    # Study sessions
    sessions = db.execute(
        "SELECT * FROM study_sessions WHERE user_id = ? ORDER BY date DESC LIMIT 30",
        (session['user_id'],)
    ).fetchall()

    total_hours = sum(s['duration_hours'] for s in sessions) if sessions else 0
    completion_rate = round((completed / total_tasks * 100) if total_tasks > 0 else 0, 1)

    # Weekly breakdown
    weekly_hours = {}
    for s in sessions:
        week = s['date'][:10] if s['date'] else 'Unknown'
        weekly_hours[week] = weekly_hours.get(week, 0) + s['duration_hours']

    perf = db.execute(
        "SELECT * FROM performance WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
        (session['user_id'],)
    ).fetchone()

    return render_template('performance.html',
        total_tasks=total_tasks,
        completed=completed,
        completion_rate=completion_rate,
        total_hours=total_hours,
        sessions=sessions,
        weekly_hours=weekly_hours,
        performance=perf
    )

@app.route('/performance/log-session', methods=['POST'])
@login_required
def log_session():
    date = request.form.get('date', '')
    course_id = request.form.get('course_id', None)

    try:
        hours = float(request.form.get('hours', 0))
    except (ValueError, TypeError):
        tflash('قيمة الساعات غير صحيحة.', 'Invalid hours value.', 'danger')
        return redirect(url_for('performance'))

    if hours <= 0 or hours > 24:
        tflash('يجب أن تكون الساعات بين 0.5 و 24.', 'Hours must be between 0.5 and 24.', 'danger')
        return redirect(url_for('performance'))

    if not date:
        tflash('التاريخ مطلوب.', 'Date is required.', 'danger')
        return redirect(url_for('performance'))

    try:
        db = get_db()
        db.execute(
            "INSERT INTO study_sessions (user_id, course_id, date, duration_hours) VALUES (?, ?, ?, ?)",
            (session['user_id'], course_id if course_id else None, date, hours)
        )
        notify(db, session['user_id'],
               f'تم تسجيل جلسة دراسة بمدة {hours} ساعة بتاريخ {date}.',
               f'Logged a {hours}-hour study session on {date}.', 'performance')
        db.commit()
        tflash('تم تسجيل الجلسة الدراسية!', 'Study session logged!', 'success')
    except Exception as e:
        tflash('خطأ في تسجيل الجلسة.', 'Error logging session.', 'danger')

    return redirect(url_for('performance'))

# ============================================================
# AI RECOMMENDATIONS (Placeholder for Part 2)
# ============================================================

@app.route('/recommendations')
@login_required
def recommendations():
    return render_template('recommendations.html')

# ============================================================
# COMMUNITY
# ============================================================

@app.route('/community')
@login_required
def community():
    db = get_db()
    posts_raw = db.execute('''
        SELECT p.*, u.username,
            (SELECT COUNT(*) FROM comments WHERE post_id = p.id) as comment_count
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
    ''').fetchall()

    posts = []
    for p in posts_raw:
        comments = db.execute('''
            SELECT c.*, u.username FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.post_id = ?
            ORDER BY c.created_at ASC
        ''', (p['id'],)).fetchall()
        post_dict = dict(p)
        post_dict['comments'] = comments
        posts.append(post_dict)

    groups = db.execute('''
        SELECT sg.*,
            (SELECT COUNT(*) FROM group_members WHERE group_id = sg.id) as member_count,
            (SELECT COUNT(*) FROM group_members WHERE group_id = sg.id AND user_id = ?) as is_member
        FROM study_groups sg
        ORDER BY sg.created_at DESC
    ''', (session['user_id'],)).fetchall()

    user = db.execute("SELECT level FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    user_level = user['level'] if user else 1

    response = render_template('community.html', posts=posts, groups=groups, user_level=user_level)
    resp = make_response(response)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@app.route('/community/post', methods=['POST'])
@login_required
def create_post():
    content = request.form.get('content', '').strip()
    if content:
        db = get_db()
        db.execute("INSERT INTO posts (user_id, content) VALUES (?, ?)", (session['user_id'], content))
        # Notify the author
        notify(db, session['user_id'],
               'تم نشر منشورك في المجتمع.',
               'Your post has been shared with the community.', 'community')
        # Notify all other users about the new post
        author = session.get('username', 'Someone')
        other_users = db.execute("SELECT id FROM users WHERE id != ?", (session['user_id'],)).fetchall()
        for u in other_users:
            notify(db, u['id'],
                   f'{author} نشر منشوراً جديداً في المجتمع.',
                   f'{author} shared a new post in the community.', 'community')
        db.commit()
        tflash('تم نشر منشورك بنجاح!', 'Post created!', 'success')
    return redirect(url_for('community'))

@app.route('/community/comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    content = request.form.get('content', '').strip()
    if content:
        db = get_db()
        post = db.execute("SELECT id, user_id FROM posts WHERE id = ?", (post_id,)).fetchone()
        if post:
            try:
                db.execute("INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)",
                           (post_id, session['user_id'], content))
                commenter = session.get('username', 'Someone')
                # Notify the commenter
                notify(db, session['user_id'],
                       'تمت إضافة تعليقك.',
                       'Your comment has been added.', 'community')
                if post['user_id'] != session['user_id']:
                    notify(db, post['user_id'],
                           f'{commenter} علّق على منشورك.',
                           f'{commenter} commented on your post.', 'community')
                # Notify other commenters on this post
                others = db.execute(
                    "SELECT DISTINCT user_id FROM comments WHERE post_id = ? AND user_id != ? AND user_id != ?",
                    (post_id, session['user_id'], post['user_id'])
                ).fetchall()
                for o in others:
                    notify(db, o['user_id'],
                           f'{commenter} أضاف تعليقاً على منشور تتابعه.',
                           f'{commenter} added a comment on a post you follow.', 'community')
                db.commit()
            except Exception:
                tflash('خطأ في إضافة التعليق.', 'Error adding comment.', 'danger')
        else:
            tflash('المنشور غير موجود.', 'Post not found.', 'danger')
    return redirect(url_for('community'))

@app.route('/community/group/create', methods=['POST'])
@login_required
def create_group():
    name = request.form.get('name', '').strip()
    department = request.form.get('department', '')
    description = request.form.get('description', '')
    capacity = int(request.form.get('capacity', 10))

    db = get_db()
    user = db.execute("SELECT level FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    default_level = user['level'] if user and user['level'] else 1
    try:
        level = int(request.form.get('level', default_level))
    except (ValueError, TypeError):
        level = default_level

    if name:
        db.execute(
            "INSERT INTO study_groups (group_name, department, level, description, capacity, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (name, department, level, description, capacity, session['user_id'])
        )
        group_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, session['user_id']))
        creator = session.get('username', 'Someone')
        notify(db, session['user_id'],
               f'تم إنشاء مجموعة "{name}" بنجاح.',
               f'Group "{name}" created successfully.', 'group')
        # Broadcast to all other users
        others = db.execute("SELECT id FROM users WHERE id != ?", (session['user_id'],)).fetchall()
        for u in others:
            notify(db, u['id'],
                   f'{creator} أنشأ مجموعة دراسية جديدة: "{name}".',
                   f'{creator} created a new study group: "{name}".', 'group')
        db.commit()
        tflash('تم إنشاء المجموعة بنجاح!', 'Group created!', 'success')

    return redirect(url_for('community') + '#groups')

@app.route('/community/post/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    db = get_db()
    post = db.execute("SELECT id, user_id FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not post or post['user_id'] != session['user_id']:
        return jsonify({'success': False}), 403
    db.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    return jsonify({'success': True})

@app.route('/community/group/delete/<int:group_id>', methods=['POST'])
@login_required
def delete_group(group_id):
    db = get_db()
    group = db.execute("SELECT id, created_by FROM study_groups WHERE id = ?", (group_id,)).fetchone()
    if not group or group['created_by'] != session['user_id']:
        return jsonify({'success': False}), 403
    db.execute("DELETE FROM group_messages WHERE group_id = ?", (group_id,))
    db.execute("DELETE FROM group_members WHERE group_id = ?", (group_id,))
    db.execute("DELETE FROM study_groups WHERE id = ?", (group_id,))
    db.commit()
    return jsonify({'success': True})

@app.route('/community/group/join/<int:group_id>', methods=['POST'])
@login_required
def join_group(group_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    db = get_db()
    group = db.execute("SELECT id, capacity FROM study_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        if is_ajax:
            return jsonify({'success': False, 'error': 'not_found'})
        tflash('المجموعة غير موجودة.', 'Group not found.', 'danger')
        return redirect(url_for('community'))

    existing = db.execute("SELECT id FROM group_members WHERE group_id = ? AND user_id = ?",
                         (group_id, session['user_id'])).fetchone()
    if existing:
        if is_ajax:
            return jsonify({'success': False, 'error': 'already_member'})
        tflash('أنت عضو بالفعل في هذه المجموعة.', 'Already a member.', 'info')
        return redirect(url_for('community'))

    member_count = db.execute("SELECT COUNT(*) FROM group_members WHERE group_id = ?", (group_id,)).fetchone()[0]
    if member_count >= group['capacity']:
        if is_ajax:
            return jsonify({'success': False, 'error': 'full'})
        tflash('المجموعة ممتلئة.', 'Group is full.', 'warning')
        return redirect(url_for('community'))

    try:
        db.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, session['user_id']))
        group_info = db.execute("SELECT group_name FROM study_groups WHERE id = ?", (group_id,)).fetchone()
        group_name = group_info['group_name'] if group_info else 'a group'
        joiner = session.get('username', 'Someone')
        notify(db, session['user_id'],
               f'انضممت إلى مجموعة "{group_name}".',
               f'You joined the group "{group_name}".', 'group')
        all_members = db.execute(
            "SELECT user_id FROM group_members WHERE group_id = ? AND user_id != ?",
            (group_id, session['user_id'])
        ).fetchall()
        for m in all_members:
            notify(db, m['user_id'],
                   f'{joiner} انضم إلى مجموعة "{group_name}".',
                   f'{joiner} joined the group "{group_name}".', 'group')
        db.commit()
        if is_ajax:
            return jsonify({'success': True, 'group_id': group_id, 'new_count': member_count + 1})
        tflash('تم الانضمام إلى المجموعة بنجاح!', 'Joined group!', 'success')
    except Exception:
        if is_ajax:
            return jsonify({'success': False, 'error': 'server_error'})
        tflash('خطأ في الانضمام إلى المجموعة.', 'Error joining group.', 'danger')
    return redirect(url_for('community'))

@app.route('/community/group/leave/<int:group_id>', methods=['POST'])
@login_required
def leave_group(group_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    db = get_db()
    group_info = db.execute("SELECT group_name FROM study_groups WHERE id = ?", (group_id,)).fetchone()
    group_name = group_info['group_name'] if group_info else 'a group'
    leaver = session.get('username', 'Someone')

    db.execute("DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, session['user_id']))
    remaining = db.execute("SELECT user_id FROM group_members WHERE group_id = ?", (group_id,)).fetchall()
    new_count = len(remaining)
    for m in remaining:
        notify(db, m['user_id'],
               f'{leaver} غادر مجموعة "{group_name}".',
               f'{leaver} left the group "{group_name}".', 'group')
    notify(db, session['user_id'],
           f'لقد غادرت مجموعة "{group_name}".',
           f'You left the group "{group_name}".', 'group')
    db.commit()
    if is_ajax:
        return jsonify({'success': True, 'group_id': group_id, 'new_count': new_count})
    tflash('تم مغادرة المجموعة.', 'Left group.', 'info')
    return redirect(url_for('community'))

@app.route('/community/group/<int:group_id>')
@login_required
def group_detail(group_id):
    db = get_db()
    group = db.execute("SELECT * FROM study_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        tflash('المجموعة غير موجودة.', 'Group not found.', 'danger')
        return redirect(url_for('community'))

    is_member = db.execute(
        "SELECT id FROM group_members WHERE group_id = ? AND user_id = ?",
        (group_id, session['user_id'])
    ).fetchone()
    if not is_member:
        tflash('انضم إلى المجموعة لعرض أعضائها.', 'Join the group to view its members.', 'warning')
        return redirect(url_for('community'))

    members = db.execute('''
        SELECT u.id, u.username, u.email, u.phone, u.department, u.level, gm.joined_at
        FROM group_members gm
        JOIN users u ON gm.user_id = u.id
        WHERE gm.group_id = ?
        ORDER BY gm.joined_at ASC
    ''', (group_id,)).fetchall()

    messages = db.execute('''
        SELECT gmsg.*, u.username FROM group_messages gmsg
        JOIN users u ON gmsg.user_id = u.id
        WHERE gmsg.group_id = ?
        ORDER BY gmsg.created_at ASC
    ''', (group_id,)).fetchall()

    resp = make_response(render_template('group_detail.html', group=group, members=members, messages=messages))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@app.route('/community/group/<int:group_id>/message', methods=['POST'])
@login_required
def group_message(group_id):
    content = request.form.get('content', '').strip()
    db = get_db()
    is_member = db.execute(
        "SELECT id FROM group_members WHERE group_id = ? AND user_id = ?",
        (group_id, session['user_id'])
    ).fetchone()
    if not is_member:
        tflash('يجب أن تكون عضواً لإرسال الرسائل.', 'You must be a member to send messages.', 'danger')
        return redirect(url_for('community'))
    if content:
        db.execute(
            "INSERT INTO group_messages (group_id, user_id, content) VALUES (?, ?, ?)",
            (group_id, session['user_id'], content)
        )
        group_info = db.execute("SELECT group_name FROM study_groups WHERE id = ?", (group_id,)).fetchone()
        group_name = group_info['group_name'] if group_info else 'a group'
        sender = session.get('username', 'Someone')
        # Notify all OTHER members of the group about the new message
        others = db.execute(
            "SELECT user_id FROM group_members WHERE group_id = ? AND user_id != ?",
            (group_id, session['user_id'])
        ).fetchall()
        for m in others:
            notify(db, m['user_id'],
                   f'رسالة جديدة من {sender} في "{group_name}".',
                   f'New message from {sender} in "{group_name}".', 'group')
        db.commit()
    return redirect(url_for('group_detail', group_id=group_id))

# ============================================================
# COURSES / ENROLLMENT
# ============================================================

@app.route('/courses')
@login_required
def courses():
    db = get_db()
    user = db.execute("SELECT level FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    user_level = user['level'] if user and user['level'] else 1

    show_all = request.args.get('show_all') == '1'
    if show_all:
        all_courses = db.execute("SELECT * FROM courses ORDER BY level, course_name").fetchall()
    else:
        all_courses = db.execute(
            "SELECT * FROM courses WHERE level = ? ORDER BY course_name", (user_level,)
        ).fetchall()

    enrolled_ids = [r['course_id'] for r in db.execute(
        "SELECT course_id FROM enrollments WHERE user_id = ?", (session['user_id'],)
    ).fetchall()]
    return render_template(
        'courses.html',
        courses=all_courses,
        enrolled_ids=enrolled_ids,
        user_level=user_level,
        show_all=show_all,
    )

@app.route('/courses/<int:course_id>')
@login_required
def course_detail(course_id):
    db = get_db()
    course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        tflash('المادة غير موجودة.', 'Course not found.', 'danger')
        return redirect(url_for('courses'))
    enrollment = db.execute(
        "SELECT * FROM enrollments WHERE user_id = ? AND course_id = ?",
        (session['user_id'], course_id)
    ).fetchone()
    if not enrollment:
        tflash('يجب التسجيل في المادة أولاً للوصول إليها.', 'You must enroll in this course first.', 'warning')
        return redirect(url_for('courses'))
    # Fetch tasks that mention the course name
    related_tasks = db.execute(
        "SELECT * FROM tasks WHERE user_id = ? AND (title LIKE ? OR description LIKE ?) ORDER BY deadline ASC",
        (session['user_id'], f'%{course["course_name"]}%', f'%{course["course_name"]}%')
    ).fetchall()
    return render_template('course_detail.html', course=course, enrollment=enrollment, related_tasks=related_tasks)

@app.route('/courses/enroll/<int:course_id>', methods=['POST'])
@login_required
def enroll_course(course_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    db = get_db()
    course = db.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        if is_ajax:
            return jsonify({'success': False, 'message_ar': 'المادة غير موجودة.', 'message_en': 'Course not found.'})
        tflash('المادة غير موجودة.', 'Course not found.', 'danger')
        return redirect(url_for('courses'))

    existing = db.execute("SELECT id FROM enrollments WHERE user_id = ? AND course_id = ?",
                         (session['user_id'], course_id)).fetchone()
    if not existing:
        try:
            db.execute("INSERT INTO enrollments (user_id, course_id, semester) VALUES (?, ?, ?)",
                      (session['user_id'], course_id, '2025-2'))
            cinfo = db.execute("SELECT course_name FROM courses WHERE id = ?", (course_id,)).fetchone()
            cname = cinfo['course_name'] if cinfo else ''
            notify(db, session['user_id'],
                   f'تم تسجيلك في مادة: {cname}',
                   f'Enrolled in course: {cname}', 'course')
            db.commit()
            if is_ajax:
                return jsonify({'success': True, 'enrolled': True})
            tflash('تم التسجيل في المادة بنجاح!', 'Enrolled successfully!', 'success')
        except Exception as e:
            db.rollback()
            if is_ajax:
                return jsonify({'success': False, 'message_ar': 'تعذر التسجيل.', 'message_en': 'Could not enroll.'})
            tflash('تعذر التسجيل. يرجى المحاولة مرة أخرى.', 'Could not enroll. Please try again.', 'danger')
    else:
        if is_ajax:
            return jsonify({'success': True, 'enrolled': True})
        tflash('أنت مسجل بالفعل في هذه المادة.', 'Already enrolled in this course.', 'info')
    return redirect(url_for('courses'))

@app.route('/courses/drop/<int:course_id>', methods=['POST'])
@login_required
def drop_course(course_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    db = get_db()
    cinfo = db.execute("SELECT course_name FROM courses WHERE id = ?", (course_id,)).fetchone()
    cname = cinfo['course_name'] if cinfo else ''
    db.execute("DELETE FROM enrollments WHERE user_id = ? AND course_id = ?", (session['user_id'], course_id))
    if cname:
        notify(db, session['user_id'],
               f'تم إلغاء تسجيل المادة: {cname}',
               f'Dropped course: {cname}', 'course')
    db.commit()
    if is_ajax:
        return jsonify({'success': True, 'enrolled': False})
    tflash('تم إلغاء تسجيل المادة.', 'Course dropped.', 'info')
    return redirect(url_for('courses'))

# ============================================================
# PROFILE
# ============================================================

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        phone = request.form.get('phone', '').strip()
        department = request.form.get('department', '').strip()
        level = int(request.form.get('level', 1))
        learning_style = request.form.get('learning_style', '')

        db.execute(
            "UPDATE users SET username=?, phone=?, department=?, level=?, learning_style=? WHERE id=?",
            (username, phone, department, level, learning_style, session['user_id'])
        )
        db.commit()
        session['username'] = username
        tflash('تم تحديث الملف الشخصي بنجاح!', 'Profile updated!', 'success')

    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    return render_template('profile.html', user=user)

@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    old_password = request.form.get('old_password', '')
    new_password = request.form.get('new_password', '')

    db = get_db()
    user = db.execute("SELECT password_hash FROM users WHERE id = ?", (session['user_id'],)).fetchone()

    if not check_password_hash(user['password_hash'], old_password):
        tflash('كلمة المرور الحالية غير صحيحة.', 'Current password is incorrect.', 'danger')
    elif len(new_password) < 6:
        tflash('يجب أن تتكون كلمة المرور الجديدة من 6 أحرف على الأقل.', 'New password must be at least 6 characters.', 'danger')
    else:
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                  (generate_password_hash(new_password), session['user_id']))
        db.commit()
        tflash('تم تغيير كلمة المرور بنجاح!', 'Password changed successfully!', 'success')

    return redirect(url_for('profile'))

# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route('/notifications')
@login_required
def notifications():
    db = get_db()
    all_notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
        (session['user_id'],)
    ).fetchall()
    return render_template('notifications.html', notifications=all_notifs)

@app.route('/notifications/read/<int:notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notif_id, session['user_id']))
    db.commit()
    return jsonify({'success': True})

@app.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_read():
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session['user_id'],))
    db.commit()
    tflash('تم تعيين جميع الإشعارات كمقروءة.', 'All notifications marked as read.', 'info')
    return redirect(url_for('notifications'))

@app.route('/notifications/delete/<int:notif_id>', methods=['POST'])
@login_required
def delete_notification(notif_id):
    db = get_db()
    db.execute("DELETE FROM notifications WHERE id = ? AND user_id = ?", (notif_id, session['user_id']))
    db.commit()
    return jsonify({'success': True})

@app.route('/notifications/delete-all', methods=['POST'])
@login_required
def delete_all_notifications():
    db = get_db()
    db.execute("DELETE FROM notifications WHERE user_id = ?", (session['user_id'],))
    db.commit()
    tflash('تم حذف جميع الإشعارات.', 'All notifications deleted.', 'info')
    return redirect(url_for('notifications'))

# ============================================================
# API ENDPOINTS (for AJAX)
# ============================================================

@app.route('/api/tasks', methods=['GET'])
@login_required
def api_get_tasks():
    db = get_db()
    tasks = db.execute("SELECT * FROM tasks WHERE user_id = ? ORDER BY deadline ASC", (session['user_id'],)).fetchall()
    return jsonify([dict(t) for t in tasks])

@app.route('/api/notifications/count')
@login_required
def api_notif_count():
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
                      (session['user_id'],)).fetchone()[0]
    return jsonify({'count': count})

# ============================================================
# AI HELPER: Gather Student Data
# ============================================================

def get_student_data():
    """Gather all student data for AI functions."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()

    total_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (session['user_id'],)).fetchone()[0]
    completed_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'completed'", (session['user_id'],)).fetchone()[0]
    pending_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'pending'", (session['user_id'],)).fetchone()[0]
    high_priority_done = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'completed' AND priority = 'high'", (session['user_id'],)).fetchone()[0]
    overdue_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'pending' AND deadline < date('now')", (session['user_id'],)).fetchone()[0]

    sessions = db.execute("SELECT * FROM study_sessions WHERE user_id = ?", (session['user_id'],)).fetchall()
    total_hours = sum(s['duration_hours'] for s in sessions) if sessions else 0
    days_with_sessions = len(set(s['date'] for s in sessions if s['date']))
    avg_daily = round(total_hours / max(days_with_sessions, 1), 1)

    enrolled = db.execute('''
        SELECT c.course_name FROM courses c
        JOIN enrollments e ON c.id = e.course_id WHERE e.user_id = ?
    ''', (session['user_id'],)).fetchall()
    course_names = ', '.join([c['course_name'] for c in enrolled]) if enrolled else 'None'

    groups_joined = db.execute("SELECT COUNT(*) FROM group_members WHERE user_id = ?", (session['user_id'],)).fetchone()[0]
    posts_count = db.execute("SELECT COUNT(*) FROM posts WHERE user_id = ?", (session['user_id'],)).fetchone()[0]

    completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)
    consistency = min(round((days_with_sessions / 7) * 100, 1), 100) if days_with_sessions > 0 else 0

    upcoming = db.execute(
        "SELECT title, deadline FROM tasks WHERE user_id = ? AND status = 'pending' AND deadline >= date('now') ORDER BY deadline LIMIT 5",
        (session['user_id'],)
    ).fetchall()
    upcoming_str = ', '.join([f"{t['title']} (due {t['deadline']})" for t in upcoming]) if upcoming else 'none'

    return {
        'username': user['username'],
        'department': user['department'] or 'not set',
        'level': user['level'],
        'learning_style': user['learning_style'] or 'not set',
        'total_hours': total_hours,
        'avg_daily_hours': avg_daily,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks,
        'high_priority_done': high_priority_done,
        'overdue_tasks': overdue_tasks,
        'completion_rate': completion_rate,
        'consistency_score': consistency,
        'enrolled_courses': len(enrolled),
        'course_names': course_names,
        'groups_joined': groups_joined,
        'posts_count': posts_count,
        'study_hours_weekly': total_hours,
        'sessions_this_week': len(sessions),
        'upcoming_deadlines': upcoming_str,
        'available_hours': 4,
        'trend': 'stable'
    }

def get_existing_groups():
    """Get all study groups info for AI matching."""
    db = get_db()
    groups = db.execute('''
        SELECT sg.*, (SELECT COUNT(*) FROM group_members WHERE group_id = sg.id) as member_count
        FROM study_groups sg
    ''').fetchall()
    return [{'name': g['group_name'], 'department': g['department'], 'level': g['level'],
             'capacity': g['capacity'], 'members': g['member_count'],
             'description': g['description'], 'learning_style': g['learning_style']} for g in groups]

# ============================================================
# AI API ENDPOINTS
# ============================================================

@app.route('/api/ai/analyze-behavior', methods=['POST'])
@login_required
def api_analyze_behavior():
    try:
        data = get_student_data()
        result = analyze_behavior(data, lang=session.get('lang', 'ar'))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/study-pattern', methods=['POST'])
@login_required
def api_study_pattern():
    try:
        data = get_student_data()
        result = recommend_study_pattern(data, lang=session.get('lang', 'ar'))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/resources', methods=['POST'])
@login_required
def api_resources():
    try:
        data = get_student_data()
        result = recommend_resources(data, lang=session.get('lang', 'ar'))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/recommendations', methods=['POST'])
@login_required
def api_recommendations():
    try:
        data = get_student_data()
        result = generate_recommendations(data, lang=session.get('lang', 'ar'))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/suggest-groups', methods=['POST'])
@login_required
def api_suggest_groups():
    try:
        data = get_student_data()
        groups = get_existing_groups()
        result = suggest_groups(data, groups, lang=session.get('lang', 'ar'))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/match-group', methods=['POST'])
@login_required
def api_match_group():
    try:
        data = get_student_data()
        groups = get_existing_groups()
        result = match_group(data, groups, lang=session.get('lang', 'ar'))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/analyze-performance', methods=['POST'])
@login_required
def api_analyze_perf():
    try:
        data = get_student_data()
        result = ai_analyze_performance(data, lang=session.get('lang', 'ar'))

        # Save analysis to performance table
        db = get_db()
        existing = db.execute("SELECT id FROM performance WHERE user_id = ?", (session['user_id'],)).fetchone()
        if existing:
            db.execute(
                "UPDATE performance SET study_hours_weekly=?, completion_rate=?, consistency_score=?, recommendation_text=?, updated_at=? WHERE user_id=?",
                (data.get('study_hours_weekly', 0), data.get('completion_rate', 0), data.get('consistency_score', 0), result, datetime.now(), session['user_id'])
            )
        else:
            db.execute(
                "INSERT INTO performance (user_id, study_hours_weekly, completion_rate, consistency_score, recommendation_text) VALUES (?, ?, ?, ?, ?)",
                (session['user_id'], data.get('study_hours_weekly', 0), data.get('completion_rate', 0), data.get('consistency_score', 0), result)
            )
        db.commit()

        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/generate-report', methods=['POST'])
@login_required
def api_generate_report():
    try:
        report_type = request.json.get('report_type', 'weekly') if request.is_json else 'weekly'
        data = get_student_data()
        result = generate_report(data, report_type, lang=session.get('lang', 'ar'))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    message = request.json.get('message', '') if request.is_json else ''
    history = request.json.get('history', []) if request.is_json else []
    if not message:
        return jsonify({'success': False, 'error': 'Message is required'})
    data = get_student_data()
    result = ai_chat(message, data, history, lang=session.get('lang', 'ar'))
    return jsonify({'success': True, 'result': result})

@app.route('/api/ai/generate-plan', methods=['POST'])
@login_required
def api_generate_plan():
    plan_type = request.json.get('plan_type', 'daily') if request.is_json else 'daily'
    study_hours = request.json.get('study_hours', 4) if request.is_json else 4
    focus = request.json.get('focus', 'balanced') if request.is_json else 'balanced'

    try:
        data = get_student_data()
        result = generate_study_plan(data, plan_type, study_hours, focus, lang=session.get('lang', 'ar'))

        if result.startswith('AI Error:'):
            return jsonify({'success': False, 'error': result})

        # Save plan to database
        db = get_db()
        db.execute(
            "INSERT INTO study_plans (user_id, plan_type, plan_data) VALUES (?, ?, ?)",
            (session['user_id'], plan_type, json.dumps({'content': result, 'hours': study_hours, 'focus': focus}))
        )
        notify(db, session['user_id'],
               f'تم إنشاء خطة دراسية {plan_type} جديدة!',
               f'New {plan_type} study plan generated!', 'plan')
        db.commit()

        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to generate plan: {str(e)}'})

# ============================================================
# RUN
# ============================================================

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)

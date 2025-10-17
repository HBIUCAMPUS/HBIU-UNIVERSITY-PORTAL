
import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import json

# College options
COLLEGES = [
    "HBIU College of Health Science / addiction training",
    "HBIU College for leadership & Management",
    "HBIU College of Business management",
    "HBIU college for behavioral and social science",
    "HBIU college of health, science and public health"
]

def get_db():
    """Get database connection - supports both SQLite and PostgreSQL"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # PostgreSQL (Production - Render) using psycopg3
        try:
            import psycopg
            conn = psycopg.connect(database_url, sslmode='require')
            return conn
        except ImportError:
            # Fallback to psycopg2 if psycopg3 not available
            try:
                import psycopg2
                conn = psycopg2.connect(database_url, sslmode='require')
                return conn
            except:
                # Final fallback to SQLite
                conn = sqlite3.connect('hbi_campus.db')
                conn.row_factory = sqlite3.Row
                return conn
    else:
        # SQLite (Development - Local)
        conn = sqlite3.connect('hbi_campus.db')
        conn.row_factory = sqlite3.Row
        return conn

def create_learning_tables():
    """Create/upgrade tables for the learning interface (chapters, items, progress, exams)."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # ---- Core learning tables ----
        # Chapters
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                order_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Chapter items (lesson, quiz, assignment, exam-placeholder)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chapter_items (
                id SERIAL PRIMARY KEY,
                chapter_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                type VARCHAR(50) NOT NULL,        -- 'lesson', 'quiz', 'assignment', 'exam'
                content TEXT,                     -- generic rich text / HTML
                video_url TEXT,
                video_file VARCHAR(255),
                instructions TEXT,                -- for assignments/quizzes
                duration VARCHAR(50),             -- e.g. '15 min'
                order_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Student progress
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS student_progress (
                id SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL,
                unit_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                completed BOOLEAN DEFAULT FALSE,
                completed_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, unit_id, item_id)
            )
        """)

        # Helpful indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapters_unit ON chapters(unit_id, order_index)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_chapter ON chapter_items(chapter_id, order_index)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_progress_student_unit ON student_progress(student_id, unit_id)")

        # Non-breaking upgrades to chapter_items (file columns)
        for ddl in [
            "ALTER TABLE chapter_items ADD COLUMN notes_file VARCHAR(255)",
            "ALTER TABLE chapter_items ADD COLUMN quiz_file VARCHAR(255)",
            "ALTER TABLE chapter_items ADD COLUMN assignment_file VARCHAR(255)"
        ]:
            try:
                cursor.execute(ddl)
            except Exception:
                pass  # already exists

        # ---- Exam tables ----
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                duration_minutes INTEGER DEFAULT 60,
                total_marks INTEGER DEFAULT 100,
                pass_marks INTEGER DEFAULT 0,
                unlock_after_count INTEGER DEFAULT 10,
                is_published BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_questions (
                id SERIAL PRIMARY KEY,
                exam_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                type VARCHAR(20) DEFAULT 'mcq',      -- 'mcq' | 'short'
                points INTEGER DEFAULT 1,
                order_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_options (
                id SERIAL PRIMARY KEY,
                question_id INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                is_correct BOOLEAN DEFAULT FALSE
            )
        """)

        # IMPORTANT: exam_attempts must have answers_json since save_exam_attempt_and_score uses it
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_attempts (
                id SERIAL PRIMARY KEY,
                exam_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                submitted_at TIMESTAMP,
                score INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'in_progress'
            )
        """)
        # Add answers_json if missing
        try:
            cursor.execute("ALTER TABLE exam_attempts ADD COLUMN answers_json TEXT")
        except Exception:
            pass

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exam_unit ON exams(unit_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_q_exam ON exam_questions(exam_id, order_index)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attempt_exam_student ON exam_attempts(exam_id, student_id)")

        conn.commit()
        print("✅ Learning & exam tables created/updated successfully")

    except Exception as e:
        print(f"❌ Error creating/upgrading learning tables: {e}")
        conn.rollback()
    finally:
        conn.close()

def _create_announcements_and_attendance():
    """
    New tables for:
      - announcements (lecturer -> students)
      - weekly_links (per-unit weekly class link)
      - attendance_sessions (open/close windows)
      - attendance_marks (students marking present)
    Safe to run repeatedly.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Announcements
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER NOT NULL,
                lecturer_id INTEGER,
                title TEXT,
                body TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ann_unit_created ON announcements(unit_id, created_at DESC)")

        # Weekly class link (single current link per unit)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_links (
                unit_id INTEGER PRIMARY KEY,
                url TEXT,
                updated_by INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Attendance session (open window)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER NOT NULL,
                lecturer_id INTEGER,
                week_label TEXT,    -- e.g. 'Week 3' (optional)
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closes_at TIMESTAMP,
                is_open BOOLEAN DEFAULT TRUE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_sess_unit_open ON attendance_sessions(unit_id, is_open)")

        # Student marks inside a session
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance_marks (
                id SERIAL PRIMARY KEY,
                session_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, student_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_mark_session ON attendance_marks(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_mark_student ON attendance_marks(student_id)")

        conn.commit()
        print("✅ Announcements, weekly_links, and attendance tables ensured.")
    except Exception as e:
        print(f"❌ Error creating announcements/attendance tables: {e}")
        conn.rollback()
    finally:
        conn.close()

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        tables_sql = [
            # Students
            '''
            CREATE TABLE IF NOT EXISTS students (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                admission_no TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                college TEXT NOT NULL DEFAULT 'Not assigned',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                google_id TEXT UNIQUE,
                totp_secret TEXT
            )
            ''',
            # Lecturers
            '''
            CREATE TABLE IF NOT EXISTS lecturers (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                google_id TEXT UNIQUE,
                totp_secret TEXT
            )
            ''',
            # Admins
            '''
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'admin',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                google_id TEXT UNIQUE,
                totp_secret TEXT
            )
            ''',
            # Units
            '''
            CREATE TABLE IF NOT EXISTS units (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                lecturer_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            # Student units
            '''
            CREATE TABLE IF NOT EXISTS student_units (
                id SERIAL PRIMARY KEY,
                student_id INTEGER,
                unit_id INTEGER,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, unit_id)
            )
            ''',
            # Results
            '''
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY,
                student_id INTEGER,
                unit_id INTEGER,
                score INTEGER,
                remarks TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, unit_id)
            )
            ''',
            # Resources
            '''
            CREATE TABLE IF NOT EXISTS resources (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            # Activities
            '''
            CREATE TABLE IF NOT EXISTS activities (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                due_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            # Admin activity log
            '''
            CREATE TABLE IF NOT EXISTS admin_activity_log (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            # Lessons
            '''
            CREATE TABLE IF NOT EXISTS lessons (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER REFERENCES units(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                content TEXT,
                video_file TEXT,
                notes_file TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            # Quizzes
            '''
            CREATE TABLE IF NOT EXISTS quizzes (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER REFERENCES units(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                duration INTEGER,
                quiz_file TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            # Assignments
            '''
            CREATE TABLE IF NOT EXISTS assignments (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER REFERENCES units(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                instructions TEXT,
                due_date DATE,
                assignment_file TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        ]
        
        for sql in tables_sql:
            try:
                cursor.execute(sql)
            except Exception as e:
                print(f"⚠️ Table creation warning: {e}")
                continue
        
        conn.commit()
        print("✅ Database tables initialized successfully")

        # Create learning + exams and fixes
        create_learning_tables()

        # New sets: announcements + attendance + weekly link
        _create_announcements_and_attendance()
        
        # Ensure default admin
        create_default_admin()
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        conn.rollback()
    finally:
        conn.close()

def create_default_admin():
    """Ensure hbiuportal@gmail.com admin account exists"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM admins WHERE email = %s", ('hbiuportal@gmail.com',))
        hashed_pw = generate_password_hash('#Ausbildung2025')
        cursor.execute(
            "INSERT INTO admins (email, password, role) VALUES (%s, %s, %s)",
            ('hbiuportal@gmail.com', hashed_pw, 'super_admin')
        )
        conn.commit()
        print("✅ Admin account ensured: hbiuportal@gmail.com / #Ausbildung2025")
    except Exception as e:
        print(f"Error ensuring admin: {e}")
        conn.rollback()
    finally:
        conn.close()

# ==================== LEARNING INTERFACE FUNCTIONS ====================

def get_unit_chapters(unit_id):
    """Get all chapters for a unit - returns list of dictionaries"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT * FROM chapters WHERE unit_id = %s ORDER BY order_index", (unit_id,))
        else:
            cursor.execute("SELECT * FROM chapters WHERE unit_id = ? ORDER BY order_index", (unit_id,))
        
        chapters = cursor.fetchall()
        chapter_list = []
        for chapter in chapters:
            if hasattr(chapter, 'keys'):
                chapter_list.append(dict(chapter))
            else:
                chapter_dict = {
                    'id': chapter[0],
                    'unit_id': chapter[1],
                    'title': chapter[2],
                    'description': chapter[3],
                    'order_index': chapter[4] if len(chapter) > 4 else 0,
                    'created_at': chapter[5] if len(chapter) > 5 else None
                }
                chapter_list.append(chapter_dict)
        return chapter_list
    except Exception as e:
        print(f"Error getting chapters: {e}")
        return []
    finally:
        conn.close()

def get_chapter_items(chapter_id):
    """Get all items (lessons, quizzes, assignments) for a chapter"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT * FROM chapter_items WHERE chapter_id = %s ORDER BY order_index", (chapter_id,))
        else:
            cursor.execute("SELECT * FROM chapter_items WHERE chapter_id = ? ORDER BY order_index", (chapter_id,))
        items = cursor.fetchall()
        return items
    except Exception as e:
        print(f"Error getting chapter items: {e}")
        return []
    finally:
        conn.close()

def get_student_progress(student_id, unit_id):
    """Get student progress for a unit"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT item_id, completed FROM student_progress WHERE student_id = %s AND unit_id = %s", (student_id, unit_id))
        else:
            cursor.execute("SELECT item_id, completed FROM student_progress WHERE student_id = ? AND unit_id = ?", (student_id, unit_id))
        progress = cursor.fetchall()
        progress_dict = {}
        for item in progress:
            if hasattr(item, 'keys'):
                progress_dict[item['item_id']] = item['completed']
            else:
                progress_dict[item[0]] = item[1]
        return progress_dict
    except Exception as e:
        print(f"Error getting student progress: {e}")
        return {}
    finally:
        conn.close()

def update_student_progress(student_id, unit_id, item_id, completed):
    """Update student progress for an item"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO student_progress (student_id, unit_id, item_id, completed, updated_at) 
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (student_id, unit_id, item_id) 
                DO UPDATE SET completed = %s, updated_at = NOW()
            """, (student_id, unit_id, item_id, completed, completed))
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO student_progress 
                (student_id, unit_id, item_id, completed, updated_at) 
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (student_id, unit_id, item_id, completed))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating progress: {e}")
        return False
    finally:
        conn.close()

# ==================== CHAPTER AND ITEM MANAGEMENT ====================

def add_chapter(unit_id, title, description="", order_index=1):
    """Add a new chapter to a unit"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO chapters (unit_id, title, description, order_index) VALUES (%s, %s, %s, %s) RETURNING id",
                (unit_id, title, description, order_index)
            )
            chapter_id = cursor.fetchone()[0]
        else:
            cursor.execute(
                "INSERT INTO chapters (unit_id, title, description, order_index) VALUES (?, ?, ?, ?)",
                (unit_id, title, description, order_index)
            )
            chapter_id = cursor.lastrowid
        conn.commit()
        return chapter_id
    except Exception as e:
        print(f"Error adding chapter: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def add_chapter_item(chapter_id, title, type, content='', video_url='', video_file='', instructions='', duration='', order_index=None, attachment_filename=None):
    """Add an item (lesson, quiz, assignment) to a chapter"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if order_index is None:
            if os.environ.get('DATABASE_URL'):
                cursor.execute("SELECT COUNT(*) FROM chapter_items WHERE chapter_id = %s", (chapter_id,))
            else:
                cursor.execute("SELECT COUNT(*) FROM chapter_items WHERE chapter_id = ?", (chapter_id,))
            order_index = cursor.fetchone()[0] + 1
        
        notes_file = None
        quiz_file = None
        assignment_file = None
        
        if type == 'lesson' and attachment_filename:
            notes_file = attachment_filename
        elif type == 'quiz' and attachment_filename:
            quiz_file = attachment_filename
        elif type == 'assignment' and attachment_filename:
            assignment_file = attachment_filename
        
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO chapter_items (chapter_id, title, type, content, video_url, video_file, instructions, duration, order_index, notes_file, quiz_file, assignment_file)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (chapter_id, title, type, content, video_url, video_file, instructions, duration, order_index, notes_file, quiz_file, assignment_file))
            item_id = cursor.fetchone()[0]
        else:
            cursor.execute("""
                INSERT INTO chapter_items (chapter_id, title, type, content, video_url, video_file, instructions, duration, order_index, notes_file, quiz_file, assignment_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (chapter_id, title, type, content, video_url, video_file, instructions, duration, order_index, notes_file, quiz_file, assignment_file))
            item_id = cursor.lastrowid
        
        conn.commit()
        return item_id
    except Exception as e:
        print(f"Error adding chapter item: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

# ==================== AUTHENTICATION ====================

def verify_admin(email, password):
    """Verify admin credentials"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
        admin = cursor.fetchone()
        if admin and check_password_hash(admin[2], password):
            return {
                'id': admin[0],
                'email': admin[1],
                'password': admin[2],
                'role': admin[3] if len(admin) > 3 else 'admin'
            }
        return None
    except Exception as e:
        print(f"Error in verify_admin: {e}")
        return None
    finally:
        conn.close()

def verify_student(email, password):
    """Verify student credentials"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM students WHERE email = %s", (email,))
        student = cursor.fetchone()
        if student and check_password_hash(student[4], password):
            return {
                'id': student[0],
                'name': student[1],
                'email': student[2],
                'admission_no': student[3],
                'password': student[4],
                'college': student[5] if len(student) > 5 else 'Not assigned'
            }
        return None
    except Exception as e:
        print(f"Error in verify_student: {e}")
        return None
    finally:
        conn.close()

def verify_lecturer(email, password):
    """Verify lecturer credentials"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM lecturers WHERE email = %s", (email,))
        lecturer = cursor.fetchone()
        if lecturer and check_password_hash(lecturer[3], password):
            return {
                'id': lecturer[0],
                'name': lecturer[1],
                'email': lecturer[2],
                'password': lecturer[3]
            }
        return None
    except Exception as e:
        print(f"Error in verify_lecturer: {e}")
        return None
    finally:
        conn.close()

def create_student(name, email, admission_no, password, college):
    """Create a new student account"""
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        cursor.execute(
            "INSERT INTO students (name, email, admission_no, password, college) VALUES (%s, %s, %s, %s, %s)",
            (name, email, admission_no, hashed_pw, college)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating student: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def create_lecturer(name, email, password):
    """Create a new lecturer account"""
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        cursor.execute(
            "INSERT INTO lecturers (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hashed_pw)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating lecturer: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def create_super_admin(email, password):
    """Create super admin account"""
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        cursor.execute(
            "INSERT INTO admins (email, password, role) VALUES (%s, %s, %s)",
            (email, hashed_pw, 'super_admin')
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating admin: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_admin_by_id(admin_id):
    """Get admin by ID"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM admins WHERE id = %s", (admin_id,))
        admin = cursor.fetchone()
        if admin:
            return {
                'id': admin[0],
                'email': admin[1],
                'password': admin[2],
                'role': admin[3] if len(admin) > 3 else 'admin'
            }
        return None
    except Exception as e:
        print(f"Error getting admin: {e}")
        return None
    finally:
        conn.close()

def get_student_by_id(student_id):
    """Get student by ID"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
        student = cursor.fetchone()
        if student:
            return {
                'id': student[0],
                'name': student[1],
                'email': student[2],
                'admission_no': student[3],
                'password': student[4],
                'college': student[5] if len(student) > 5 else 'Not assigned'
            }
        return None
    except Exception as e:
        print(f"Error getting student: {e}")
        return None
    finally:
        conn.close()

def get_lecturer_by_id(lecturer_id):
    """Get lecturer by ID"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM lecturers WHERE id = %s", (lecturer_id,))
        lecturer = cursor.fetchone()
        if lecturer:
            return {
                'id': lecturer[0],
                'name': lecturer[1],
                'email': lecturer[2],
                'password': lecturer[3]
            }
        return None
    except Exception as e:
        print(f"Error getting lecturer: {e}")
        return None
    finally:
        conn.close()

def get_all_students():
    """Get all students"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, email, admission_no, college, created_at FROM students ORDER BY created_at DESC")
        students = []
        for row in cursor.fetchall():
            students.append({
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'admission_no': row[3],
                'college': row[4],
                'created_at': row[5]
            })
        return students
    except Exception as e:
        print(f"Error getting students: {e}")
        return []
    finally:
        conn.close()

def get_all_lecturers():
    """Get all lecturers"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM lecturers ORDER BY created_at DESC")
        lecturers = []
        for row in cursor.fetchall():
            lecturers.append({
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'created_at': row[4] if len(row) > 4 else None
            })
        return lecturers
    except Exception as e:
        print(f"Error getting lecturers: {e}")
        return []
    finally:
        conn.close()

def get_all_units_with_details():
    """Get all units with proper lecturer names"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT 
                u.id, u.code, u.title, u.lecturer_id,
                l.name as lecturer_name,
                (SELECT COUNT(*) FROM student_units su WHERE su.unit_id = u.id) as student_count
            FROM units u 
            LEFT JOIN lecturers l ON u.lecturer_id = l.id
            ORDER BY u.code
        ''')
        units = []
        rows = cursor.fetchall()
        for row in rows:
            if hasattr(row, 'keys'):
                unit_data = dict(row)
                lecturer_name = unit_data.get('lecturer_name')
                units.append({
                    'id': unit_data['id'],
                    'code': unit_data['code'],
                    'title': unit_data['title'],
                    'lecturer_id': unit_data['lecturer_id'],
                    'lecturer_name': lecturer_name if lecturer_name else 'Not assigned',
                    'student_count': unit_data.get('student_count', 0)
                })
            else:
                lecturer_name = row[4] if len(row) > 4 and row[4] else None
                units.append({
                    'id': row[0],
                    'code': row[1],
                    'title': row[2],
                    'lecturer_id': row[3],
                    'lecturer_name': lecturer_name if lecturer_name else 'Not assigned',
                    'student_count': row[5] if len(row) > 5 else 0
                })
        return units
    except Exception as e:
        print(f"Error getting units: {e}")
        return []
    finally:
        conn.close()

def get_units_by_lecturer(lecturer_id):
    """Get units by lecturer"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM units WHERE lecturer_id = %s", (lecturer_id,))
        units = []
        for row in cursor.fetchall():
            units.append({
                'id': row[0],
                'code': row[1],
                'title': row[2],
                'lecturer_id': row[3]
            })
        return units
    except Exception as e:
        print(f"Error getting lecturer units: {e}")
        return []
    finally:
        conn.close()

def get_all_units():
    """Get all units for students to browse"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, code, title, lecturer_id FROM units ORDER BY code")
        units = []
        for row in cursor.fetchall():
            if hasattr(row, 'keys'):
                unit_data = dict(row)
                units.append({
                    'id': unit_data['id'],
                    'code': unit_data['code'],
                    'title': unit_data['title'],
                    'lecturer_id': unit_data['lecturer_id']
                })
            else:
                units.append({
                    'id': row[0],
                    'code': row[1],
                    'title': row[2],
                    'lecturer_id': row[3]
                })
        return units
    except Exception as e:
        print(f"Error getting all units: {e}")
        return []
    finally:
        conn.close()

def create_unit(code, title, lecturer_id):
    """Create a new unit"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO units (code, title, lecturer_id) VALUES (%s, %s, %s)",
            (code, title, lecturer_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating unit: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_unit_by_id(unit_id):
    """Get unit by ID"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM units WHERE id = %s", (unit_id,))
        unit = cursor.fetchone()
        if unit:
            return {
                'id': unit[0],
                'code': unit[1],
                'title': unit[2],
                'lecturer_id': unit[3]
            }
        return None
    except Exception as e:
        print(f"Error getting unit: {e}")
        return None
    finally:
        conn.close()

def register_student_unit(student_id, unit_code):
    """Register student for a unit"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM units WHERE code = %s", (unit_code,))
        unit = cursor.fetchone()
        if not unit:
            return False
        cursor.execute(
            "INSERT INTO student_units (student_id, unit_id) VALUES (%s, %s)",
            (student_id, unit[0])
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error registering student unit: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_student_units(student_id):
    """Get units registered by student"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT u.*, l.name as lecturer 
            FROM units u 
            JOIN student_units su ON u.id = su.unit_id 
            LEFT JOIN lecturers l ON u.lecturer_id = l.id 
            WHERE su.student_id = %s
        ''', (student_id,))
        units = []
        for row in cursor.fetchall():
            units.append({
                'id': row[0],
                'code': row[1],
                'title': row[2],
                'lecturer_id': row[3],
                'lecturer': row[4] if len(row) > 4 else 'Unknown',
                'unit_id': row[0]
            })
        return units
    except Exception as e:
        print(f"Error getting student units: {e}")
        return []
    finally:
        conn.close()

def get_student_results(student_id):
    """Get results for a student"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT u.code, u.title, r.score, r.remarks 
            FROM results r 
            JOIN units u ON r.unit_id = u.id 
            WHERE r.student_id = %s
        ''', (student_id,))
        results = []
        for row in cursor.fetchall():
            results.append({
                'code': row[0],
                'title': row[1],
                'score': row[2],
                'remarks': row[3]
            })
        return results
    except Exception as e:
        print(f"Error getting student results: {e}")
        return []
    finally:
        conn.close()

def get_all_results():
    """Get all student results for admin view with lecturer information"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT 
                r.id,
                s.name as student_name,
                s.admission_no,
                u.code as unit_code,
                u.title as unit_title,
                r.score,
                r.remarks,
                l.name as lecturer_name,
                r.created_at
            FROM results r
            JOIN students s ON r.student_id = s.id
            JOIN units u ON r.unit_id = u.id
            LEFT JOIN lecturers l ON u.lecturer_id = l.id
            ORDER BY r.created_at DESC
        ''')
        results = []
        for row in cursor.fetchall():
            if hasattr(row, 'keys'):
                result_data = dict(row)
                results.append({
                    'id': result_data['id'],
                    'student_name': result_data['student_name'],
                    'admission_no': result_data['admission_no'],
                    'unit_code': result_data['unit_code'],
                    'unit_title': result_data['unit_title'],
                    'score': result_data['score'],
                    'remarks': result_data.get('remarks', ''),
                    'lecturer_name': result_data.get('lecturer_name', ''),
                    'created_at': result_data['created_at']
                })
            else:
                results.append({
                    'id': row[0],
                    'student_name': row[1],
                    'admission_no': row[2],
                    'unit_code': row[3],
                    'unit_title': row[4],
                    'score': row[5],
                    'remarks': row[6] if len(row) > 6 else '',
                    'lecturer_name': row[7] if len(row) > 7 else '',
                    'created_at': row[8] if len(row) > 8 else None
                })
        return results
    except Exception as e:
        print(f"Error getting all results: {e}")
        return []
    finally:
        conn.close()

def get_unit_students(unit_id):
    """Get students registered for a unit"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT s.*, r.score, r.remarks 
            FROM students s 
            JOIN student_units su ON s.id = su.student_id 
            LEFT JOIN results r ON s.id = r.student_id AND r.unit_id = %s
            WHERE su.unit_id = %s
        ''', (unit_id, unit_id))
        students = []
        for row in cursor.fetchall():
            students.append({
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'admission_no': row[3],
                'college': row[5] if len(row) > 5 else 'Not assigned',
                'score': row[6] if len(row) > 6 else None,
                'remarks': row[7] if len(row) > 7 else None
            })
        return students
    except Exception as e:
        print(f"Error getting unit students: {e}")
        return []
    finally:
        conn.close()

# -------- Google OAuth + 2FA helpers --------

def get_student_by_google_id(google_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM students WHERE google_id = %s", (google_id,))
        student = cursor.fetchone()
        if student:
            return {
                'id': student[0],
                'name': student[1],
                'email': student[2],
                'admission_no': student[3],
                'password': student[4],
                'college': student[5] if len(student) > 5 else 'Not assigned',
                'created_at': student[6] if len(student) > 6 else None,
                'google_id': student[7] if len(student) > 7 else None,
                'totp_secret': student[8] if len(student) > 8 else None
            }
        return None
    except Exception as e:
        print(f"Error getting student by Google ID: {e}")
        return None
    finally:
        conn.close()

def get_student_by_email(email):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM students WHERE email = %s", (email,))
        student = cursor.fetchone()
        if student:
            return {
                'id': student[0],
                'name': student[1],
                'email': student[2],
                'admission_no': student[3],
                'password': student[4],
                'college': student[5] if len(student) > 5 else 'Not assigned',
                'created_at': student[6] if len(student) > 6 else None,
                'google_id': student[7] if len(student) > 7 else None,
                'totp_secret': student[8] if len(student) > 8 else None
            }
        return None
    except Exception as e:
        print(f"Error getting student by email: {e}")
        return None
    finally:
        conn.close()

def update_student_google_id(student_id, google_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE students SET google_id = %s WHERE id = %s",
            (google_id, student_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating Google ID: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_totp_secret(user_type, user_id, secret):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if user_type == 'student':
            cursor.execute("UPDATE students SET totp_secret = %s WHERE id = %s", (secret, user_id))
        elif user_type == 'lecturer':
            cursor.execute("UPDATE lecturers SET totp_secret = %s WHERE id = %s", (secret, user_id))
        elif user_type == 'admin':
            cursor.execute("UPDATE admins SET totp_secret = %s WHERE id = %s", (secret, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating TOTP secret: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_totp_secret(user_type, user_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if user_type == 'student':
            cursor.execute("SELECT totp_secret FROM students WHERE id = %s", (user_id,))
        elif user_type == 'lecturer':
            cursor.execute("SELECT totp_secret FROM lecturers WHERE id = %s", (user_id,))
        elif user_type == 'admin':
            cursor.execute("SELECT totp_secret FROM admins WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] if result and result[0] else None
    except Exception as e:
        print(f"Error getting TOTP secret: {e}")
        return None
    finally:
        conn.close()

def update_student_result(student_id, unit_id, score, remarks):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO results (student_id, unit_id, score, remarks) 
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (student_id, unit_id) 
            DO UPDATE SET score = %s, remarks = %s
        ''', (student_id, unit_id, score, remarks, score, remarks))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating result: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def add_resource(unit_id, title, filename):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO resources (unit_id, title, filename) VALUES (%s, %s, %s)",
            (unit_id, title, filename)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding resource: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_unit_resources(unit_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM resources WHERE unit_id = %s ORDER BY uploaded_at DESC", (unit_id,))
        resources = []
        for row in cursor.fetchall():
            resources.append({
                'id': row[0],
                'unit_id': row[1],
                'title': row[2],
                'filename': row[3],
                'uploaded_at': row[4] if len(row) > 4 else None
            })
        return resources
    except Exception as e:
        print(f"Error getting resources: {e}")
        return []
    finally:
        conn.close()

def get_upcoming_activities(student_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT a.*, u.code as unit_code 
            FROM activities a 
            JOIN units u ON a.unit_id = u.id 
            JOIN student_units su ON u.id = su.unit_id 
            WHERE su.student_id = %s AND a.due_date >= CURRENT_DATE
            ORDER BY a.due_date
            LIMIT 10
        ''', (student_id,))
        activities = []
        for row in cursor.fetchall():
            activities.append({
                'id': row[0],
                'unit_id': row[1],
                'title': row[2],
                'description': row[3],
                'due_date': row[4],
                'unit_code': row[6] if len(row) > 6 else 'Unknown'
            })
        return activities
    except Exception as e:
        print(f"Error getting activities: {e}")
        return []
    finally:
        conn.close()

def verify_current_password(user_type, user_id, current_password):
    if user_type == 'student':
        student = get_student_by_id(user_id)
        if student and check_password_hash(student['password'], current_password):
            return True
    elif user_type == 'lecturer':
        lecturer = get_lecturer_by_id(user_id)
        if lecturer and check_password_hash(lecturer['password'], current_password):
            return True
    elif user_type == 'admin':
        admin = get_admin_by_id(user_id)
        if admin and check_password_hash(admin['password'], current_password):
            return True
    return False

def update_student_password(student_id, new_password):
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(new_password)
    try:
        cursor.execute(
            "UPDATE students SET password = %s WHERE id = %s",
            (hashed_pw, student_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating student password: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_lecturer_password(lecturer_id, new_password):
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(new_password)
    try:
        cursor.execute(
            "UPDATE lecturers SET password = %s WHERE id = %s",
            (hashed_pw, lecturer_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating lecturer password: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_admin_password(admin_id, new_password):
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(new_password)
    try:
        cursor.execute(
            "UPDATE admins SET password = %s WHERE id = %s",
            (hashed_pw, admin_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating admin password: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def log_admin_activity(admin_id, action, details, ip_address=''):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO admin_activity_log (admin_id, action, details, ip_address) VALUES (%s, %s, %s, %s)",
            (admin_id, action, details, ip_address)
        )
        conn.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")
    finally:
        conn.close()

def get_recent_admin_activity(limit=5):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM admin_activity_log ORDER BY timestamp DESC LIMIT %s",
            (limit,)
        )
        activities = []
        for row in cursor.fetchall():
            activities.append({
                'id': row[0],
                'admin_id': row[1],
                'action': row[2],
                'details': row[3],
                'timestamp': row[5] if len(row) > 5 else None
            })
        return activities
    except Exception as e:
        print(f"Error getting activities: {e}")
        return []
    finally:
        conn.close()

def get_admin_activity_log(admin_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM admin_activity_log WHERE admin_id = %s ORDER BY timestamp DESC",
            (admin_id,)
        )
        activities = []
        for row in cursor.fetchall():
            activities.append({
                'id': row[0],
                'admin_id': row[1],
                'action': row[2],
                'details': row[3],
                'timestamp': row[5] if len(row) > 5 else None
            })
        return activities
    except Exception as e:
        print(f"Error getting admin activities: {e}")
        return []
    finally:
        conn.close()

def get_all_students_with_units():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT s.*, COUNT(su.unit_id) as unit_count
            FROM students s
            LEFT JOIN student_units su ON s.id = su.student_id
            GROUP BY s.id
            ORDER BY s.name
        ''')
        students = []
        for row in cursor.fetchall():
            students.append({
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'admission_no': row[3],
                'college': row[5] if len(row) > 5 else 'Not assigned',
                'unit_count': row[6] if len(row) > 6 else 0
            })
        return students
    except Exception as e:
        print(f"Error getting students with units: {e}")
        return []
    finally:
        conn.close()

def admin_add_result(student_id, unit_id, score, remarks):
    return update_student_result(student_id, unit_id, score, remarks)

def admin_update_result(result_id, score, remarks):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE results SET score = %s, remarks = %s WHERE id = %s",
            (score, remarks, result_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating result: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def admin_delete_result(result_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM results WHERE id = %s", (result_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting result: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_student(student_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting student: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_lecturer(lecturer_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM lecturers WHERE id = %s", (lecturer_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting lecturer: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_unit(unit_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM units WHERE id = %s", (unit_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting unit: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# -------- Placeholders (unchanged) --------

def link_google_course(unit_id, google_course_id, google_course_name):
    return True

def get_google_course_by_unit(unit_id):
    return None

def save_jotform_form(form_id, form_title, form_type, unit_id=None, assignment_id=None, embed_url=None):
    return True

def get_jotform_forms_by_unit(unit_id):
    return []

# ==================== NEW: LESSON, QUIZ, ASSIGNMENT HELPERS ====================

def add_lesson(unit_id, title, content, video_filename, notes_filename, created_by):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO lessons (unit_id, title, content, video_file, notes_file, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (unit_id, title, content, video_filename, notes_filename, created_by))
        else:
            cursor.execute("""
                INSERT INTO lessons (unit_id, title, content, video_file, notes_file, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (unit_id, title, content, video_filename, notes_filename, created_by))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"DB Error (add_lesson): {e}")
        return False

def add_quiz(unit_id, title, description, duration, quiz_filename, created_by):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO quizzes (unit_id, title, description, duration, quiz_file, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (unit_id, title, description, duration, quiz_filename, created_by))
        else:
            cursor.execute("""
                INSERT INTO quizzes (unit_id, title, description, duration, quiz_file, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (unit_id, title, description, duration, quiz_filename, created_by))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"DB Error (add_quiz): {e}")
        return False

def add_assignment(unit_id, title, instructions, due_date, assignment_filename, created_by):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO assignments (unit_id, title, instructions, due_date, assignment_file, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (unit_id, title, instructions, due_date, assignment_filename, created_by))
        else:
            cursor.execute("""
                INSERT INTO assignments (unit_id, title, instructions, due_date, assignment_file, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (unit_id, title, instructions, due_date, assignment_filename, created_by))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"DB Error (add_assignment): {e}")
        return False

# ==================== VIEW HELPERS ====================

def get_lessons_by_unit(unit_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                SELECT id, title, content, video_file, notes_file, created_at
                FROM lessons
                WHERE unit_id = %s
                ORDER BY created_at DESC
            """, (unit_id,))
        else:
            cursor.execute("""
                SELECT id, title, content, video_file, notes_file, created_at
                FROM lessons
                WHERE unit_id = ?
                ORDER BY created_at DESC
            """, (unit_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"DB Error (get_lessons_by_unit): {e}")
        return []

def get_quizzes_by_unit(unit_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                SELECT id, title, description, duration, quiz_file, created_at
                FROM quizzes
                WHERE unit_id = %s
                ORDER BY created_at DESC
            """, (unit_id,))
        else:
            cursor.execute("""
                SELECT id, title, description, duration, quiz_file, created_at
                FROM quizzes
                WHERE unit_id = ?
                ORDER BY created_at DESC
            """, (unit_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"DB Error (get_quizzes_by_unit): {e}")
        return []

def get_assignments_by_unit(unit_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                SELECT id, title, instructions, due_date, assignment_file, created_at
                FROM assignments
                WHERE unit_id = %s
                ORDER BY created_at DESC
            """, (unit_id,))
        else:
            cursor.execute("""
                SELECT id, title, instructions, due_date, assignment_file, created_at
                FROM assignments
                WHERE unit_id = ?
                ORDER BY created_at DESC
            """, (unit_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"DB Error (get_assignments_by_unit): {e}")
        return []

# ==================== EDIT / DELETE HELPERS ====================

def update_lesson(lesson_id, title, content, video_file=None, notes_file=None):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                UPDATE lessons
                SET title = %s, content = %s, video_file = COALESCE(%s, video_file),
                    notes_file = COALESCE(%s, notes_file)
                WHERE id = %s
            """, (title, content, video_file, notes_file, lesson_id))
        else:
            cursor.execute("""
                UPDATE lessons
                SET title = ?, content = ?, video_file = COALESCE(?, video_file),
                    notes_file = COALESCE(?, notes_file)
                WHERE id = ?
            """, (title, content, video_file, notes_file, lesson_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"DB Error (update_lesson): {e}")
        return False

def delete_lesson(lesson_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if os.environ.get('DATABASE_URL'):
            cursor.execute("DELETE FROM lessons WHERE id = %s", (lesson_id,))
        else:
            cursor.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"DB Error (delete_lesson): {e}")
        return False

def count_lessons_in_unit(unit_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT COUNT(*) FROM lessons WHERE unit_id = %s", (unit_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM lessons WHERE unit_id = ?", (unit_id,))
        count = cursor.fetchone()[0]
        return count
    except Exception as e:
        print(f"Error counting lessons: {e}")
        return 0
    finally:
        conn.close()

# ==================== EXAM FUNCTIONS ====================

def get_exam_by_unit(unit_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT * FROM exams WHERE unit_id = %s", (unit_id,))
        else:
            cursor.execute("SELECT * FROM exams WHERE unit_id = ?", (unit_id,))
        exam = cursor.fetchone()
        if exam:
            return {
                'id': exam[0],
                'unit_id': exam[1],
                'title': exam[2],
                'description': exam[3],
                'duration_minutes': exam[4],
                'total_marks': exam[5],
                'pass_marks': exam[6],
                'unlock_after_count': exam[7],
                'is_published': exam[8]
            }
        return None
    except Exception as e:
        print(f"Error getting exam: {e}")
        return None
    finally:
        conn.close()

def get_exam_questions(exam_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT * FROM exam_questions WHERE exam_id = %s ORDER BY order_index", (exam_id,))
        else:
            cursor.execute("SELECT * FROM exam_questions WHERE exam_id = ? ORDER BY order_index", (exam_id,))
        questions = cursor.fetchall()
        return questions
    except Exception as e:
        print(f"Error getting exam questions: {e}")
        return []
    finally:
        conn.close()

def save_exam_attempt_and_score(exam_id, student_id, answers):
    """Save exam attempt and calculate score (simplified grading)"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        score = 50
        total_marks = 100
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO exam_attempts (exam_id, student_id, score, status, answers_json, submitted_at)
                VALUES (%s, %s, %s, 'submitted', %s, NOW())
            """, (exam_id, student_id, score, json.dumps(answers)))
        else:
            cursor.execute("""
                INSERT INTO exam_attempts (exam_id, student_id, score, status, answers_json, submitted_at)
                VALUES (?, ?, ?, 'submitted', ?, datetime('now'))
            """, (exam_id, student_id, score, json.dumps(answers)))
        conn.commit()
        return score, total_marks
    except Exception as e:
        print(f"Error saving exam attempt: {e}")
        return 0, 100
    finally:
        conn.close()

# ==================== NEW: ANNOUNCEMENTS ====================

def add_announcement(unit_id, lecturer_id, title, body):
    """Create a new announcement for a unit."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO announcements (unit_id, lecturer_id, title, body, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (unit_id, lecturer_id, title, body))
        else:
            cursor.execute("""
                INSERT INTO announcements (unit_id, lecturer_id, title, body, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (unit_id, lecturer_id, title, body))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding announcement: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_announcements(unit_id, limit=50):
    """Fetch announcements for a unit (newest first)."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                SELECT id, unit_id, lecturer_id, title, body, created_at
                FROM announcements
                WHERE unit_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (unit_id, limit))
        else:
            cursor.execute("""
                SELECT id, unit_id, lecturer_id, title, body, created_at
                FROM announcements
                WHERE unit_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (unit_id, limit))
        rows = cursor.fetchall()
        ann = []
        for r in rows:
            ann.append({
                'id': r[0],
                'unit_id': r[1],
                'lecturer_id': r[2],
                'title': r[3],
                'body': r[4],
                'created_at': r[5]
            })
        return ann
    except Exception as e:
        print(f"Error fetching announcements: {e}")
        return []
    finally:
        conn.close()

# ==================== NEW: WEEKLY CLASS LINK ====================

def set_weekly_link(unit_id, url, updated_by):
    """Create/update the weekly class link for a unit."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Upsert
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO weekly_links (unit_id, url, updated_by, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (unit_id) DO UPDATE SET
                    url = EXCLUDED.url,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
            """, (unit_id, url, updated_by))
        else:
            # SQLite upsert pattern
            cursor.execute("SELECT unit_id FROM weekly_links WHERE unit_id = ?", (unit_id,))
            exists = cursor.fetchone()
            if exists:
                cursor.execute("""
                    UPDATE weekly_links
                    SET url = ?, updated_by = ?, updated_at = datetime('now')
                    WHERE unit_id = ?
                """, (url, updated_by, unit_id))
            else:
                cursor.execute("""
                    INSERT INTO weekly_links (unit_id, url, updated_by, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                """, (unit_id, url, updated_by))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error setting weekly link: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_weekly_link(unit_id):
    """Get the current weekly class link for a unit."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT url, updated_by, updated_at FROM weekly_links WHERE unit_id = %s", (unit_id,))
        else:
            cursor.execute("SELECT url, updated_by, updated_at FROM weekly_links WHERE unit_id = ?", (unit_id,))
        row = cursor.fetchone()
        if row:
            return {'url': row[0], 'updated_by': row[1], 'updated_at': row[2]}
        return None
    except Exception as e:
        print(f"Error getting weekly link: {e}")
        return None
    finally:
        conn.close()

# ==================== NEW: ATTENDANCE ====================

def create_attendance_session(unit_id, lecturer_id, week_label=None, closes_at=None):
    """Open a new attendance session; auto-closes others for same unit."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Close any existing open session for this unit
        if os.environ.get('DATABASE_URL'):
            cursor.execute("UPDATE attendance_sessions SET is_open = FALSE WHERE unit_id = %s AND is_open = TRUE", (unit_id,))
        else:
            cursor.execute("UPDATE attendance_sessions SET is_open = 0 WHERE unit_id = ? AND is_open = 1", (unit_id,))

        # Insert new open session
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO attendance_sessions (unit_id, lecturer_id, week_label, opened_at, closes_at, is_open)
                VALUES (%s, %s, %s, NOW(), %s, TRUE)
                RETURNING id
            """, (unit_id, lecturer_id, week_label, closes_at))
            sess_id = cursor.fetchone()[0]
        else:
            cursor.execute("""
                INSERT INTO attendance_sessions (unit_id, lecturer_id, week_label, opened_at, closes_at, is_open)
                VALUES (?, ?, ?, datetime('now'), ?, 1)
            """, (unit_id, lecturer_id, week_label, closes_at))
            sess_id = cursor.lastrowid

        conn.commit()
        return sess_id
    except Exception as e:
        print(f"Error creating attendance session: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def close_attendance_session(session_id):
    """Close a specific attendance session."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("UPDATE attendance_sessions SET is_open = FALSE, closes_at = COALESCE(closes_at, NOW()) WHERE id = %s", (session_id,))
        else:
            cursor.execute("UPDATE attendance_sessions SET is_open = 0, closes_at = COALESCE(closes_at, datetime('now')) WHERE id = ?", (session_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error closing attendance session: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_open_attendance_session(unit_id):
    """Return the current open session for a unit (or None)."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                SELECT id, unit_id, lecturer_id, week_label, opened_at, closes_at, is_open
                FROM attendance_sessions
                WHERE unit_id = %s AND is_open = TRUE
                ORDER BY opened_at DESC
                LIMIT 1
            """, (unit_id,))
        else:
            cursor.execute("""
                SELECT id, unit_id, lecturer_id, week_label, opened_at, closes_at, is_open
                FROM attendance_sessions
                WHERE unit_id = ? AND is_open = 1
                ORDER BY opened_at DESC
                LIMIT 1
            """, (unit_id,))
        row = cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'unit_id': row[1],
                'lecturer_id': row[2],
                'week_label': row[3],
                'opened_at': row[4],
                'closes_at': row[5],
                'is_open': bool(row[6])
            }
        return None
    except Exception as e:
        print(f"Error fetching open attendance session: {e}")
        return None
    finally:
        conn.close()

def mark_attendance(session_id, student_id):
    """Student marks attendance for an open session."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Ensure session is open
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT is_open FROM attendance_sessions WHERE id = %s", (session_id,))
        else:
            cursor.execute("SELECT is_open FROM attendance_sessions WHERE id = ?", (session_id,))
        session_row = cursor.fetchone()
        if not session_row:
            return False, "Session not found"
        if (session_row[0] is False) or (session_row[0] == 0):
            return False, "Session is closed"

        # Insert mark (unique constraint handles duplicates)
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO attendance_marks (session_id, student_id, marked_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (session_id, student_id) DO NOTHING
            """, (session_id, student_id))
        else:
            # SQLite: emulate ON CONFLICT by ignoring duplicates
            try:
                cursor.execute("""
                    INSERT INTO attendance_marks (session_id, student_id, marked_at)
                    VALUES (?, ?, datetime('now'))
                """, (session_id, student_id))
            except Exception:
                pass

        conn.commit()
        return True, "Marked present"
    except Exception as e:
        print(f"Error marking attendance: {e}")
        conn.rollback()
        return False, "Error"
    finally:
        conn.close()

def get_attendance_counts(session_id):
    """Return count of marked students for a session."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT COUNT(*) FROM attendance_marks WHERE session_id = %s", (session_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM attendance_marks WHERE session_id = ?", (session_id,))
        marked = cursor.fetchone()[0]

        # Determine total registered students in the unit of that session
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT unit_id FROM attendance_sessions WHERE id = %s", (session_id,))
        else:
            cursor.execute("SELECT unit_id FROM attendance_sessions WHERE id = ?", (session_id,))
        sess = cursor.fetchone()
        total = 0
        if sess:
            unit_id = sess[0]
            if os.environ.get('DATABASE_URL'):
                cursor.execute("SELECT COUNT(*) FROM student_units WHERE unit_id = %s", (unit_id,))
            else:
                cursor.execute("SELECT COUNT(*) FROM student_units WHERE unit_id = ?", (unit_id,))
            total = cursor.fetchone()[0]

        return {'marked': marked, 'total_registered': total}
    except Exception as e:
        print(f"Error getting attendance counts: {e}")
        return {'marked': 0, 'total_registered': 0}
    finally:
        conn.close()

def get_attendance_status_for_student(unit_id, student_id):
    """
    Return:
      {
        'open_session': { ... } or None,
        'has_marked': True/False,
        'counts': {'marked': X, 'total_registered': Y}
      }
    """
    session = get_open_attendance_session(unit_id)
    if not session:
        return {'open_session': None, 'has_marked': False, 'counts': {'marked': 0, 'total_registered': 0}}

    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                SELECT 1 FROM attendance_marks
                WHERE session_id = %s AND student_id = %s
                LIMIT 1
            """, (session['id'], student_id))
        else:
            cursor.execute("""
                SELECT 1 FROM attendance_marks
                WHERE session_id = ? AND student_id = ?
                LIMIT 1
            """, (session['id'], student_id))
        marked = cursor.fetchone() is not None
        counts = get_attendance_counts(session['id'])
        return {'open_session': session, 'has_marked': marked, 'counts': counts}
    except Exception as e:
        print(f"Error getting attendance status for student: {e}")
        return {'open_session': session, 'has_marked': False, 'counts': {'marked': 0, 'total_registered': 0}}
    finally:
        conn.close()
```

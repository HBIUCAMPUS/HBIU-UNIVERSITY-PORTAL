import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
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
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE,
                UNIQUE(student_id, unit_id, item_id)
            )
        """)

        # Add helpful indexes (safe to run multiple times in PG/SQLite)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapters_unit ON chapters(unit_id, order_index)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_chapter ON chapter_items(chapter_id, order_index)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_progress_student_unit ON student_progress(student_id, unit_id)")

        # ---- Non-breaking upgrades to chapter_items (file columns) ----
        # SQLite doesn't support IF NOT EXISTS on ADD COLUMN; swallow duplicate-column errors.
        for ddl in [
            "ALTER TABLE chapter_items ADD COLUMN notes_file VARCHAR(255)",        # lesson notes upload
            "ALTER TABLE chapter_items ADD COLUMN quiz_file VARCHAR(255)",         # optional quiz file upload
            "ALTER TABLE chapter_items ADD COLUMN assignment_file VARCHAR(255)"    # assignment brief upload
        ]:
            try:
                cursor.execute(ddl)
            except Exception:
                pass  # column already exists -> ignore

        # ---- Exam tables ----
        # An exam belongs to a unit (not to a chapter), but you can still put an 'exam' item
        # into the last chapter to show it in the sidebar.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                duration_minutes INTEGER DEFAULT 60,
                total_marks INTEGER DEFAULT 100,
                pass_marks INTEGER DEFAULT 0,
                unlock_after_count INTEGER DEFAULT 10,  -- number of non-exam items to complete before unlocked
                is_published BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_options (
                id SERIAL PRIMARY KEY,
                question_id INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                is_correct BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (question_id) REFERENCES exam_questions(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_attempts (
                id SERIAL PRIMARY KEY,
                exam_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                submitted_at TIMESTAMP,
                score INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'in_progress',  -- 'in_progress' | 'submitted' | 'graded'
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_answers (
                id SERIAL PRIMARY KEY,
                attempt_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                selected_option_id INTEGER,  -- for MCQ
                answer_text TEXT,            -- for short answers
                is_correct BOOLEAN,          -- nullable until graded
                FOREIGN KEY (attempt_id) REFERENCES exam_attempts(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES exam_questions(id) ON DELETE CASCADE,
                FOREIGN KEY (selected_option_id) REFERENCES exam_options(id) ON DELETE SET NULL
            )
        """)

        # Exam indexes
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

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Use simplified table creation that works for both databases
        tables_sql = [
            # UPDATED: Students table with Google OAuth and 2FA support
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
            
            # UPDATED: Lecturers table with Google OAuth and 2FA support
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
            
            # UPDATED: Admins table with Google OAuth and 2FA support
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
            
            # Units table
            '''
            CREATE TABLE IF NOT EXISTS units (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                lecturer_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            
            # Student units junction table
            '''
            CREATE TABLE IF NOT EXISTS student_units (
                id SERIAL PRIMARY KEY,
                student_id INTEGER,
                unit_id INTEGER,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, unit_id)
            )
            ''',
            
            # Results table
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
            
            # Resources table
            '''
            CREATE TABLE IF NOT EXISTS resources (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            
            # Activities table
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

            # NEW: Lessons table
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

            # NEW: Quizzes table
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

            # NEW: Assignments table
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
        
        # Execute all table creation statements
        for sql in tables_sql:
            try:
                cursor.execute(sql)
            except Exception as e:
                print(f"⚠️ Table creation warning: {e}")
                continue
        
        conn.commit()
        print("✅ Database tables initialized successfully")

        # Create learning tables
        create_learning_tables()
        
        # Create default admin account
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
        # Delete any existing admin with this email (cleanup)
        cursor.execute("DELETE FROM admins WHERE email = %s", ('hbiuportal@gmail.com',))
        
        # Create your custom admin
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
    """Get all chapters for a unit - NEW FUNCTION"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT * FROM chapters WHERE unit_id = %s ORDER BY order_index", (unit_id,))
        else:
            cursor.execute("SELECT * FROM chapters WHERE unit_id = ? ORDER BY order_index", (unit_id,))
        chapters = cursor.fetchall()
        return chapters
    except Exception as e:
        print(f"Error getting chapters: {e}")
        return []
    finally:
        conn.close()

def get_chapter_items(chapter_id):
    """Get all items (lessons, quizzes, assignments) for a chapter - NEW FUNCTION"""
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
    """Get student progress for a unit - NEW FUNCTION"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT item_id, completed FROM student_progress WHERE student_id = %s AND unit_id = %s", (student_id, unit_id))
        else:
            cursor.execute("SELECT item_id, completed FROM student_progress WHERE student_id = ? AND unit_id = ?", (student_id, unit_id))
        progress = cursor.fetchall()
        # Convert to dictionary for easier lookup
        progress_dict = {}
        for item in progress:
            if hasattr(item, 'keys'):  # PostgreSQL
                progress_dict[item['item_id']] = item['completed']
            else:  # SQLite
                progress_dict[item[0]] = item[1]
        return progress_dict
    except Exception as e:
        print(f"Error getting student progress: {e}")
        return {}
    finally:
        conn.close()

def update_student_progress(student_id, unit_id, item_id, completed):
    """Update student progress for an item - NEW FUNCTION"""
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

# ==================== AUTHENTICATION FUNCTIONS ====================

def verify_admin(email, password):
    """Verify admin credentials"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
        admin = cursor.fetchone()
        
        if admin and check_password_hash(admin[2], password):  # password is 3rd column
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
        
        if student and check_password_hash(student[4], password):  # password is 5th column
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
        
        if lecturer and check_password_hash(lecturer[3], password):  # password is 4th column
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
        # Explicit column selection - much more reliable
        cursor.execute("SELECT id, name, email, admission_no, college, created_at FROM students ORDER BY created_at DESC")
        students = []
        for row in cursor.fetchall():
            students.append({
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'admission_no': row[3],
                'college': row[4],      # Now this is definitely college
                'created_at': row[5]    # Now this is definitely created_at
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
        # Simple and clear query
        if os.environ.get('DATABASE_URL'):
            cursor.execute('''
                SELECT 
                    u.id, u.code, u.title, u.lecturer_id,
                    l.name as lecturer_name,
                    (SELECT COUNT(*) FROM student_units su WHERE su.unit_id = u.id) as student_count
                FROM units u 
                LEFT JOIN lecturers l ON u.lecturer_id = l.id
                ORDER BY u.code
            ''')
        else:
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
            if hasattr(row, 'keys'):  # PostgreSQL
                unit_data = dict(row)
                # Ensure we get the actual lecturer name
                lecturer_name = unit_data.get('lecturer_name')
                
                units.append({
                    'id': unit_data['id'],
                    'code': unit_data['code'],
                    'title': unit_data['title'],
                    'lecturer_id': unit_data['lecturer_id'],
                    'lecturer_name': lecturer_name if lecturer_name else 'Not assigned',
                    'student_count': unit_data.get('student_count', 0)
                })
            else:  # SQLite
                # row[4] should be lecturer_name from the JOIN
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
    """Get all units for students to browse (simple version)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT id, code, title, lecturer_id FROM units ORDER BY code")
        else:
            cursor.execute("SELECT id, code, title, lecturer_id FROM units ORDER BY code")
        
        units = []
        for row in cursor.fetchall():
            if hasattr(row, 'keys'):  # PostgreSQL
                unit_data = dict(row)
                units.append({
                    'id': unit_data['id'],
                    'code': unit_data['code'],
                    'title': unit_data['title'],
                    'lecturer_id': unit_data['lecturer_id']
                })
            else:  # SQLite
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
        # Get unit id from code
        cursor.execute("SELECT id FROM units WHERE code = %s", (unit_code,))
        unit = cursor.fetchone()
        
        if not unit:
            return False
        
        # Register student
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
                'unit_id': row[0]  # For compatibility with templates
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
        if os.environ.get('DATABASE_URL'):
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
        else:
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
            if hasattr(row, 'keys'):  # PostgreSQL
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
            else:  # SQLite
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

# ADD THESE NEW FUNCTIONS TO YOUR EXISTING database.py FILE

def get_student_by_google_id(google_id):
    """Get student by Google ID - NEW FUNCTION"""
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
    """Get student by email - NEW FUNCTION"""
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
    """Update student with Google ID - NEW FUNCTION"""
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
    """Update TOTP secret for user - NEW FUNCTION"""
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
    """Get TOTP secret for user - NEW FUNCTION"""
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
    """Update student result"""
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
    """Add resource to unit"""
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
    """Get resources for a unit"""
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
    """Get upcoming activities for student"""
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
    """Verify current password for password change"""
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
    """Update student password"""
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
    """Update lecturer password"""
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
    """Update admin password"""
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
    """Log admin activity"""
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
    """Get recent admin activity"""
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
    """Get activity log for specific admin"""
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
    """Get all students with their registered units"""
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
    """Admin function to add result"""
    return update_student_result(student_id, unit_id, score, remarks)

def admin_update_result(result_id, score, remarks):
    """Admin function to update result"""
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
    """Admin function to delete result"""
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
    """Delete student"""
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
    """Delete lecturer"""
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
    """Delete unit"""
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

# Google Classroom and JotForm functions (placeholder implementations)
def link_google_course(unit_id, google_course_id, google_course_name):
    """Link Google Classroom course - placeholder"""
    return True

def get_google_course_by_unit(unit_id):
    """Get Google Classroom course - placeholder"""
    return None

def save_jotform_form(form_id, form_title, form_type, unit_id=None, assignment_id=None, embed_url=None):
    """Save JotForm form - placeholder"""
    return True

def get_jotform_forms_by_unit(unit_id):
    """Get JotForm forms - placeholder"""
# ==================== NEW: LESSON, QUIZ, ASSIGNMENT FUNCTIONS ====================

def add_lesson(unit_id, title, content, video_filename, notes_filename, created_by):
    """Insert a new lesson into the database"""
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
    """Insert a new quiz into the database"""
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
    """Insert a new assignment into the database"""
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
# ==================== VIEW & FETCH HELPERS ====================

def get_lessons_by_unit(unit_id):
    """Fetch all lessons for a specific unit"""
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
    """Fetch all quizzes for a specific unit"""
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
    """Fetch all assignments for a specific unit"""
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


# ==================== EDIT / DELETE HELPERS (OPTIONAL) ====================

def update_lesson(lesson_id, title, content, video_file=None, notes_file=None):
    """Edit an existing lesson"""
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
    """Delete a lesson"""
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
def count_lessons_in_unit(unit_id:int)->int:
    conn = get_db(); cur = conn.cursor()
    pg = bool(os.environ.get('DATABASE_URL'))
    sql = "SELECT COUNT(*) FROM learning_items WHERE unit_id = %s AND type = 'lesson'" if pg else \
          "SELECT COUNT(*) FROM learning_items WHERE unit_id = ? AND type = 'lesson'"
    cur.execute(sql, (unit_id,))
    n = cur.fetchone()[0]
    conn.close()
    return n or 0

def get_or_create_exam_chapter(unit_id:int):
    """Ensure a chapter named 'Final Examination' exists."""
    conn = get_db(); cur = conn.cursor()
    pg = bool(os.environ.get('DATABASE_URL'))

    # find
    sql = "SELECT id FROM learning_chapters WHERE unit_id=%s AND title='Final Examination'" if pg else \
          "SELECT id FROM learning_chapters WHERE unit_id=? AND title='Final Examination'"
    cur.execute(sql, (unit_id,))
    row = cur.fetchone()
    if row: 
        cid = row[0]
    else:
        ins = "INSERT INTO learning_chapters (unit_id, title, position) VALUES (%s,%s,%s) RETURNING id" if pg else \
              "INSERT INTO learning_chapters (unit_id, title, position) VALUES (?,?,?)"
        if pg:
            cur.execute(ins, (unit_id,'Final Examination', 9999))
            cid = cur.fetchone()[0]
        else:
            cur.execute(ins, (unit_id,'Final Examination', 9999))
            cid = cur.lastrowid
        conn.commit()
    conn.close()
    return cid

def create_exam(unit_id:int, title:str, instructions:str, duration_minutes:int, total_marks:int, created_by:int):
    """Create learning_item(type='exam') + exams row; returns exam_id and exam_item_id."""
    chapter_id = get_or_create_exam_chapter(unit_id)
    conn = get_db(); cur = conn.cursor()
    pg = bool(os.environ.get('DATABASE_URL'))

    # learning item for exam
    ins_item = ("INSERT INTO learning_items (chapter_id, unit_id, type, title, position, created_by) "
                "VALUES (%s,%s,'exam',%s,9999,%s) RETURNING id") if pg else \
               "INSERT INTO learning_items (chapter_id, unit_id, type, title, position, created_by) VALUES (?,?,?,?,?,?)"
    if pg:
        cur.execute(ins_item, (chapter_id, unit_id, title, created_by))
        exam_item_id = cur.fetchone()[0]
    else:
        cur.execute(ins_item, (chapter_id, unit_id, title, 9999, created_by))
        exam_item_id = cur.lastrowid

    # exams row
    ins_exam = ("INSERT INTO exams (unit_id, item_id, title, instructions, duration_minutes, total_marks, is_published) "
                "VALUES (%s,%s,%s,%s,%s,%s, FALSE) RETURNING id") if pg else \
               "INSERT INTO exams (unit_id, item_id, title, instructions, duration_minutes, total_marks, is_published) VALUES (?,?,?,?,?,?,0)"
    params = (unit_id, exam_item_id, title, instructions, duration_minutes, total_marks)
    if pg:
        cur.execute(ins_exam, params)
        exam_id = cur.fetchone()[0]
    else:
        cur.execute(ins_exam, params)
        exam_id = cur.lastrowid

    conn.commit(); conn.close()
    return exam_id, exam_item_id

def add_exam_questions(exam_id:int, questions:list):
    """
    questions: list of dicts:
      { 'qtype':'mcq'|'tf'|'text', 'question': '...', 'options': ['A','B'] (mcq only),
        'correct': 'A'|'true'|None, 'marks': 2, 'position':1 }
    """
    conn = get_db(); cur = conn.cursor()
    pg = bool(os.environ.get('DATABASE_URL'))
    sql = "INSERT INTO exam_questions (exam_id, qtype, question, options_json, correct_answer, marks, position) VALUES (%s,%s,%s,%s,%s,%s,%s)" if pg else \
          "INSERT INTO exam_questions (exam_id, qtype, question, options_json, correct_answer, marks, position) VALUES (?,?,?,?,?,?,?)"
    for q in questions:
        opts = json.dumps(q.get('options')) if q.get('options') is not None else None
        cur.execute(sql, (exam_id, q['qtype'], q['question'], opts, str(q.get('correct')) if q.get('correct') is not None else None,
                          int(q.get('marks',1)), int(q.get('position',0))))
    conn.commit(); conn.close()

def get_exam_by_unit(unit_id:int):
    conn = get_db(); cur = conn.cursor()
    pg = bool(os.environ.get('DATABASE_URL'))
    sql = "SELECT id, item_id, title, instructions, duration_minutes, total_marks, is_published FROM exams WHERE unit_id=%s" if pg else \
          "SELECT id, item_id, title, instructions, duration_minutes, total_marks, is_published FROM exams WHERE unit_id=?"
    cur.execute(sql,(unit_id,))
    row = cur.fetchone()
    conn.close()
    if not row: return None
    keys = ['id','item_id','title','instructions','duration_minutes','total_marks','is_published']
    return dict(zip(keys,row))

def get_exam_questions(exam_id:int):
    conn = get_db(); cur = conn.cursor()
    pg = bool(os.environ.get('DATABASE_URL'))
    sql = "SELECT id,qtype,question,options_json,correct_answer,marks,position FROM exam_questions WHERE exam_id=%s ORDER BY position,id" if pg else \
          "SELECT id,qtype,question,options_json,correct_answer,marks,position FROM exam_questions WHERE exam_id=? ORDER BY position,id"
    cur.execute(sql,(exam_id,))
    rows = cur.fetchall(); conn.close()
    out=[]
    for r in rows:
        d={'id':r[0],'qtype':r[1],'question':r[2],'options': json.loads(r[3]) if r[3] else None,
           'correct': r[4], 'marks': r[5], 'position': r[6]}
        out.append(d)
    return out

def save_exam_attempt_and_score(exam_id:int, student_id:int, answers:dict):
    """Auto-grade MCQ/TF, leave text ungraded (0 marks). Returns (raw_score,total_marks)."""
    qs = get_exam_questions(exam_id)
    total = sum(int(q.get('marks',1)) for q in qs)
    score = 0
    for q in qs:
        if q['qtype'] in ('mcq','tf'):
            if str(answers.get(str(q['id']))) == str(q.get('correct')):
                score += int(q.get('marks',1))
        # 'text' -> manual grade later

    conn = get_db(); cur = conn.cursor()
    pg = bool(os.environ.get('DATABASE_URL'))
    payload = json.dumps(answers)
    if pg:
        # upsert-like: try update, else insert
        cur.execute("UPDATE exam_attempts SET submitted_at=NOW(), raw_score=%s, total_marks=%s, answers_json=%s, status='submitted' WHERE exam_id=%s AND student_id=%s",
                    (score,total,payload,exam_id,student_id))
        if cur.rowcount == 0:
            cur.execute("INSERT INTO exam_attempts (exam_id, student_id, submitted_at, raw_score, total_marks, answers_json, status) VALUES (%s,%s,NOW(),%s,%s,%s,'submitted')",
                        (exam_id,student_id,score,total,payload))
    else:
        cur.execute("SELECT id FROM exam_attempts WHERE exam_id=? AND student_id=?",(exam_id,student_id))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE exam_attempts SET submitted_at=CURRENT_TIMESTAMP, raw_score=?, total_marks=?, answers_json=?, status='submitted' WHERE id=?",
                        (score,total,payload,row[0]))
        else:
            cur.execute("INSERT INTO exam_attempts (exam_id, student_id, submitted_at, raw_score, total_marks, answers_json, status) VALUES (?,?,CURRENT_TIMESTAMP,?,?,?,'submitted')",
                        (exam_id,student_id,score,total,payload))
    conn.commit(); conn.close()
    return score, total
    def get_next_chapter_number(unit_id):
        """Get the next chapter number for a unit"""
        conn = get_db()
        cursor = conn.cursor()
        try:
            if os.environ.get('DATABASE_URL'):
                cursor.execute("SELECT COUNT(*) FROM chapters WHERE unit_id = %s", (unit_id,))
            else:
                cursor.execute("SELECT COUNT(*) FROM chapters WHERE unit_id = ?", (unit_id,))
            count = cursor.fetchone()[0]
            return count + 1
        except Exception as e:
            print(f"Error getting chapter count: {e}")
            return 1
        finally:
            conn.close()

def add_chapter(unit_id, title, description='', order_index=None):
    """Add a new chapter to a unit"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if order_index is None:
            order_index = get_next_chapter_number(unit_id)
        
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO chapters (unit_id, title, description, order_index) 
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (unit_id, title, description, order_index))
            chapter_id = cursor.fetchone()[0]
        else:
            cursor.execute("""
                INSERT INTO chapters (unit_id, title, description, order_index) 
                VALUES (?, ?, ?, ?)
            """, (unit_id, title, description, order_index))
            chapter_id = cursor.lastrowid
        
        conn.commit()
        return chapter_id
    except Exception as e:
        print(f"Error adding chapter: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def add_chapter_item(chapter_id, title, type, content='', video_url='', video_file='', instructions='', duration='', order_index=None):
    """Add an item (lesson, quiz, assignment) to a chapter"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if order_index is None:
            # Get next order index for this chapter
            if os.environ.get('DATABASE_URL'):
                cursor.execute("SELECT COUNT(*) FROM chapter_items WHERE chapter_id = %s", (chapter_id,))
            else:
                cursor.execute("SELECT COUNT(*) FROM chapter_items WHERE chapter_id = ?", (chapter_id,))
            order_index = cursor.fetchone()[0] + 1
        
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                INSERT INTO chapter_items (chapter_id, title, type, content, video_url, video_file, instructions, duration, order_index)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (chapter_id, title, type, content, video_url, video_file, instructions, duration, order_index))
            item_id = cursor.fetchone()[0]
        else:
            cursor.execute("""
                INSERT INTO chapter_items (chapter_id, title, type, content, video_url, video_file, instructions, duration, order_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (chapter_id, title, type, content, video_url, video_file, instructions, duration, order_index))
            item_id = cursor.lastrowid
        
        conn.commit()
        return item_id
    except Exception as e:
        print(f"Error adding chapter item: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


    return []

# database.py
import os
from werkzeug.security import generate_password_hash, check_password_hash

# Render provides DATABASE_URL environment variable
def get_db():
    if os.environ.get('DATABASE_URL'):
        # PostgreSQL for production (Render)
        import psycopg2
        from urllib.parse import urlparse
        
        result = urlparse(os.environ['DATABASE_URL'])
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
        return conn
    else:
        # SQLite for development
        import sqlite3
        conn = sqlite3.connect('hbi_campus.db')
        conn.row_factory = sqlite3.Row
        return conn

def migrate_db():
    """Add missing columns to existing database without losing data"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if os.environ.get('DATABASE_URL'):
            # PostgreSQL migration
            # Check if is_active column exists in admins table
            cursor.execute('''
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'admins' AND column_name = 'is_active'
            ''')
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE admins ADD COLUMN is_active BOOLEAN DEFAULT TRUE')
                print("Added is_active column to admins table (PostgreSQL)")
            
            # Update existing records
            cursor.execute("UPDATE admins SET is_active = TRUE WHERE is_active IS NULL")
            
        else:
            # SQLite migration
            # Check if is_active column exists in admins table
            cursor.execute("PRAGMA table_info(admins)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'is_active' not in columns:
                cursor.execute("ALTER TABLE admins ADD COLUMN is_active INTEGER DEFAULT 1")
                print("Added is_active column to admins table (SQLite)")
            
            # Update existing records
            cursor.execute("UPDATE admins SET is_active = 1 WHERE is_active IS NULL")
        
        conn.commit()
        print("Database migration completed successfully")
        
    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    if os.environ.get('DATABASE_URL'):
        # PostgreSQL table creation (Render)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                admission_no TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lecturers (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'admin',
                is_active BOOLEAN DEFAULT TRUE,
                last_login TIMESTAMP,
                last_password_change TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_activity_log (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES admins (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS units (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                lecturer_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lecturer_id) REFERENCES lecturers (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS student_units (
                id SERIAL PRIMARY KEY,
                student_id INTEGER,
                unit_id INTEGER,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students (id),
                FOREIGN KEY (unit_id) REFERENCES units (id),
                UNIQUE(student_id, unit_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY,
                student_id INTEGER,
                unit_id INTEGER,
                score INTEGER,
                remarks TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students (id),
                FOREIGN KEY (unit_id) REFERENCES units (id),
                UNIQUE(student_id, unit_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resources (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                due_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_resets (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER,
                token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES admins (id)
            )
        ''')
        
        # ==================== GOOGLE CLASSROOM INTEGRATION TABLES ====================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS google_classroom_courses (
                id SERIAL PRIMARY KEY,
                unit_id INTEGER,
                google_course_id TEXT UNIQUE NOT NULL,
                google_course_name TEXT NOT NULL,
                sync_enabled BOOLEAN DEFAULT TRUE,
                last_sync TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS google_classroom_assignments (
                id SERIAL PRIMARY KEY,
                activity_id INTEGER,
                google_course_id TEXT NOT NULL,
                google_assignment_id TEXT UNIQUE NOT NULL,
                sync_status TEXT DEFAULT 'pending',
                last_sync TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (activity_id) REFERENCES activities (id),
                FOREIGN KEY (google_course_id) REFERENCES google_classroom_courses (google_course_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS google_classroom_sync_log (
                id SERIAL PRIMARY KEY,
                sync_type TEXT NOT NULL,
                entity_id INTEGER,
                status TEXT NOT NULL,
                message TEXT,
                sync_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # ==================== JOTFORM INTEGRATION TABLES ====================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jotform_forms (
                id SERIAL PRIMARY KEY,
                form_id TEXT UNIQUE NOT NULL,
                form_title TEXT NOT NULL,
                form_type TEXT NOT NULL,
                unit_id INTEGER,
                assignment_id INTEGER,
                embed_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units (id),
                FOREIGN KEY (assignment_id) REFERENCES activities (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jotform_submissions (
                id SERIAL PRIMARY KEY,
                form_id TEXT NOT NULL,
                submission_id TEXT UNIQUE NOT NULL,
                submission_type TEXT NOT NULL,
                student_id INTEGER,
                submission_data TEXT,
                processed BOOLEAN DEFAULT FALSE,
                submitted_at TIMESTAMP,
                processed_at TIMESTAMP,
                FOREIGN KEY (form_id) REFERENCES jotform_forms (form_id),
                FOREIGN KEY (student_id) REFERENCES students (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jotform_webhook_logs (
                id SERIAL PRIMARY KEY,
                webhook_type TEXT NOT NULL,
                payload TEXT,
                processed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
    else:
        # SQLite table creation (Development)
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                admission_no TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS lecturers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'admin',
                is_active INTEGER DEFAULT 1,
                last_login DATETIME,
                last_password_change DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS admin_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES admins (id)
            );
            
            CREATE TABLE IF NOT EXISTS units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                lecturer_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lecturer_id) REFERENCES lecturers (id)
            );
            
            CREATE TABLE IF NOT EXISTS student_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                unit_id INTEGER,
                registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students (id),
                FOREIGN KEY (unit_id) REFERENCES units (id),
                UNIQUE(student_id, unit_id)
            );
            
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                unit_id INTEGER,
                score INTEGER,
                remarks TEXT,
                recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students (id),
                FOREIGN KEY (unit_id) REFERENCES units (id),
                UNIQUE(student_id, unit_id)
            );
            
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id INTEGER,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units (id)
            );
            
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                due_date DATE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units (id)
            );
            
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                token TEXT UNIQUE NOT NULL,
                expires_at DATETIME NOT NULL,
                used INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES admins (id)
            );
            
            -- Google Classroom Integration Tables
            CREATE TABLE IF NOT EXISTS google_classroom_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id INTEGER,
                google_course_id TEXT UNIQUE NOT NULL,
                google_course_name TEXT NOT NULL,
                sync_enabled INTEGER DEFAULT 1,
                last_sync DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units (id)
            );
            
            CREATE TABLE IF NOT EXISTS google_classroom_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER,
                google_course_id TEXT NOT NULL,
                google_assignment_id TEXT UNIQUE NOT NULL,
                sync_status TEXT DEFAULT 'pending',
                last_sync DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (activity_id) REFERENCES activities (id),
                FOREIGN KEY (google_course_id) REFERENCES google_classroom_courses (google_course_id)
            );
            
            CREATE TABLE IF NOT EXISTS google_classroom_sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                entity_id INTEGER,
                status TEXT NOT NULL,
                message TEXT,
                sync_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- JotForm Integration Tables
            CREATE TABLE IF NOT EXISTS jotform_forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                form_id TEXT UNIQUE NOT NULL,
                form_title TEXT NOT NULL,
                form_type TEXT NOT NULL,
                unit_id INTEGER,
                assignment_id INTEGER,
                embed_url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units (id),
                FOREIGN KEY (assignment_id) REFERENCES activities (id)
            );
            
            CREATE TABLE IF NOT EXISTS jotform_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                form_id TEXT NOT NULL,
                submission_id TEXT UNIQUE NOT NULL,
                submission_type TEXT NOT NULL,
                student_id INTEGER,
                submission_data TEXT,
                processed INTEGER DEFAULT 0,
                submitted_at DATETIME,
                processed_at DATETIME,
                FOREIGN KEY (form_id) REFERENCES jotform_forms (form_id),
                FOREIGN KEY (student_id) REFERENCES students (id)
            );
            
            CREATE TABLE IF NOT EXISTS jotform_webhook_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_type TEXT NOT NULL,
                payload TEXT,
                processed INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        ''')
    
    conn.commit()
    conn.close()
    
    # Run migration to ensure all columns exist
    migrate_db()
    
    # Create default admin if none exists
    create_default_admin()

def create_default_admin():
    """Create a default admin account if none exists"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if any admin exists
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT COUNT(*) FROM admins")
        else:
            cursor.execute("SELECT COUNT(*) FROM admins")
        
        admin_count = cursor.fetchone()[0]
        
        if admin_count == 0:
            # Create default admin
            hashed_pw = generate_password_hash('admin123')
            if os.environ.get('DATABASE_URL'):
                cursor.execute(
                    "INSERT INTO admins (email, password, role) VALUES (%s, %s, %s)",
                    ('admin@university.edu', hashed_pw, 'super_admin')
                )
            else:
                cursor.execute(
                    "INSERT INTO admins (email, password, role) VALUES (?, ?, ?)",
                    ('admin@university.edu', hashed_pw, 'super_admin')
                )
            conn.commit()
            print("Default admin created: admin@university.edu / admin123")
        else:
            print(f"Admin accounts already exist: {admin_count} accounts found")
            
    except Exception as e:
        print(f"Error creating default admin: {e}")
        conn.rollback()
    finally:
        conn.close()

# ==================== SAFE VERIFY_ADMIN FUNCTION ====================

def verify_admin(email, password):
    """Safe version of verify_admin that handles missing columns"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # First try the query with is_active check
        try:
            if os.environ.get('DATABASE_URL'):
                cursor.execute("SELECT * FROM admins WHERE email = %s AND is_active = TRUE", (email,))
            else:
                cursor.execute("SELECT * FROM admins WHERE email = ? AND is_active = 1", (email,))
            admin = cursor.fetchone()
        except Exception as e:
            # If that fails, try without is_active check
            print(f"Note: is_active check failed, trying without it: {e}")
            if os.environ.get('DATABASE_URL'):
                cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
            else:
                cursor.execute("SELECT * FROM admins WHERE email = ?", (email,))
            admin = cursor.fetchone()
        
        if admin and check_password_hash(admin['password'], password):
            # FIXED: Additional safety check for is_active if column exists
            try:
                # Use dictionary-style access instead of .get() for sqlite3.Row
                is_active = admin['is_active'] if 'is_active' in admin else None
                if is_active is not None:
                    if os.environ.get('DATABASE_URL'):
                        if not is_active:
                            return None
                    else:
                        if is_active != 1:
                            return None
            except (KeyError, AttributeError):
                # Column doesn't exist or can't be accessed, proceed
                pass
                
            return admin
        return None
        
    except Exception as e:
        print(f"Error in verify_admin: {e}")
        return None
    finally:
        conn.close()

# ==================== GOOGLE CLASSROOM INTEGRATION FUNCTIONS ====================

def link_google_course(unit_id, google_course_id, google_course_name):
    """Link a university unit with a Google Classroom course"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute('''
                INSERT INTO google_classroom_courses (unit_id, google_course_id, google_course_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (google_course_id) 
                DO UPDATE SET unit_id = %s, google_course_name = %s
            ''', (unit_id, google_course_id, google_course_name, unit_id, google_course_name))
        else:
            cursor.execute('''
                INSERT OR REPLACE INTO google_classroom_courses 
                (unit_id, google_course_id, google_course_name)
                VALUES (?, ?, ?)
            ''', (unit_id, google_course_id, google_course_name))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error linking Google course: {e}")
        return False
    finally:
        conn.close()

def get_google_course_by_unit(unit_id):
    """Get Google Classroom course linked to a unit"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute('''
                SELECT * FROM google_classroom_courses WHERE unit_id = %s
            ''', (unit_id,))
        else:
            cursor.execute('''
                SELECT * FROM google_classroom_courses WHERE unit_id = ?
            ''', (unit_id,))
        course = cursor.fetchone()
        return course
    except Exception as e:
        print(f"Error getting Google course: {e}")
        return None
    finally:
        conn.close()

def log_google_sync_activity(sync_type, entity_id, status, message):
    """Log Google Classroom synchronization activities"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute('''
                INSERT INTO google_classroom_sync_log (sync_type, entity_id, status, message)
                VALUES (%s, %s, %s, %s)
            ''', (sync_type, entity_id, status, message))
        else:
            cursor.execute('''
                INSERT INTO google_classroom_sync_log (sync_type, entity_id, status, message)
                VALUES (?, ?, ?, ?)
            ''', (sync_type, entity_id, status, message))
        conn.commit()
    except Exception as e:
        print(f"Error logging Google sync activity: {e}")
    finally:
        conn.close()

# ==================== JOTFORM INTEGRATION FUNCTIONS ====================

def save_jotform_form(form_id, form_title, form_type, unit_id=None, assignment_id=None, embed_url=None):
    """Save JotForm form details to database"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute('''
                INSERT INTO jotform_forms (form_id, form_title, form_type, unit_id, assignment_id, embed_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (form_id) 
                DO UPDATE SET form_title = %s, form_type = %s, unit_id = %s, assignment_id = %s, embed_url = %s
            ''', (form_id, form_title, form_type, unit_id, assignment_id, embed_url, 
                  form_title, form_type, unit_id, assignment_id, embed_url))
        else:
            cursor.execute('''
                INSERT OR REPLACE INTO jotform_forms 
                (form_id, form_title, form_type, unit_id, assignment_id, embed_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (form_id, form_title, form_type, unit_id, assignment_id, embed_url))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving JotForm form: {e}")
        return False
    finally:
        conn.close()

def log_jotform_submission(submission_type, form_id, submission_id, submission_data, student_id=None):
    """Log JotForm submission to database"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute('''
                INSERT INTO jotform_submissions 
                (submission_type, form_id, submission_id, student_id, submission_data, submitted_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ''', (submission_type, form_id, submission_id, student_id, submission_data))
        else:
            cursor.execute('''
                INSERT INTO jotform_submissions 
                (submission_type, form_id, submission_id, student_id, submission_data, submitted_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (submission_type, form_id, submission_id, student_id, submission_data))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error logging JotForm submission: {e}")
        return False
    finally:
        conn.close()

def get_jotform_forms_by_unit(unit_id):
    """Get JotForm forms associated with a unit"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute('''
                SELECT * FROM jotform_forms WHERE unit_id = %s ORDER BY created_at DESC
            ''', (unit_id,))
        else:
            cursor.execute('''
                SELECT * FROM jotform_forms WHERE unit_id = ? ORDER BY created_at DESC
            ''', (unit_id,))
        forms = cursor.fetchall()
        return forms
    except Exception as e:
        print(f"Error getting JotForm forms: {e}")
        return []
    finally:
        conn.close()

def log_jotform_webhook(webhook_type, payload):
    """Log JotForm webhook to database"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute('''
                INSERT INTO jotform_webhook_logs (webhook_type, payload)
                VALUES (%s, %s)
            ''', (webhook_type, payload))
        else:
            cursor.execute('''
                INSERT INTO jotform_webhook_logs (webhook_type, payload)
                VALUES (?, ?)
            ''', (webhook_type, payload))
        conn.commit()
    except Exception as e:
        print(f"Error logging webhook: {e}")
    finally:
        conn.close()

# ==================== EXISTING FUNCTIONALITIES (PRESERVED) ====================

def create_student(name, email, admission_no, password):
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO students (name, email, admission_no, password) VALUES (%s, %s, %s, %s)",
                (name, email, admission_no, hashed_pw)
            )
        else:
            cursor.execute(
                "INSERT INTO students (name, email, admission_no, password) VALUES (?, ?, ?, ?)",
                (name, email, admission_no, hashed_pw)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def create_lecturer(name, email, password):
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO lecturers (name, email, password) VALUES (%s, %s, %s)",
                (name, email, hashed_pw)
            )
        else:
            cursor.execute(
                "INSERT INTO lecturers (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_pw)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def create_admin(email, password):
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO admins (email, password) VALUES (%s, %s)",
                (email, hashed_pw)
            )
        else:
            cursor.execute(
                "INSERT INTO admins (email, password) VALUES (?, ?)",
                (email, hashed_pw)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def create_super_admin(email, password):
    """Create super admin with enhanced security"""
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO admins (email, password, role, is_active) VALUES (%s, %s, %s, %s)",
                (email, hashed_pw, 'super_admin', True)
            )
        else:
            cursor.execute(
                "INSERT INTO admins (email, password, role, is_active) VALUES (?, ?, ?, ?)",
                (email, hashed_pw, 'super_admin', 1)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def verify_student(email, password):
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute("SELECT * FROM students WHERE email = %s", (email,))
    else:
        cursor.execute("SELECT * FROM students WHERE email = ?", (email,))
    student = cursor.fetchone()
    conn.close()
    
    if student and check_password_hash(student['password'], password):
        return student
    return None

def verify_lecturer(email, password):
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute("SELECT * FROM lecturers WHERE email = %s", (email,))
    else:
        cursor.execute("SELECT * FROM lecturers WHERE email = ?", (email,))
    lecturer = cursor.fetchone()
    conn.close()
    
    if lecturer and check_password_hash(lecturer['password'], password):
        return lecturer
    return None

def get_admin_by_id(admin_id):
    """Get admin by ID with security checks"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT * FROM admins WHERE id = %s AND is_active = TRUE", (admin_id,))
        else:
            cursor.execute("SELECT * FROM admins WHERE id = ? AND is_active = 1", (admin_id,))
        admin = cursor.fetchone()
        return admin
    except:
        # Fallback if is_active column doesn't exist
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT * FROM admins WHERE id = %s", (admin_id,))
        else:
            cursor.execute("SELECT * FROM admins WHERE id = ?", (admin_id,))
        admin = cursor.fetchone()
        return admin
    finally:
        conn.close()

def verify_current_password(user_type, user_id, current_password):
    """Verify current password for any user type"""
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

# ==================== PASSWORD MANAGEMENT ENHANCEMENTS ====================

def update_student_password(student_id, new_password):
    """Update student password with security"""
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(new_password)
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "UPDATE students SET password = %s WHERE id = %s",
                (hashed_pw, student_id)
            )
        else:
            cursor.execute(
                "UPDATE students SET password = ? WHERE id = ?",
                (hashed_pw, student_id)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def update_lecturer_password(lecturer_id, new_password):
    """Update lecturer password with security"""
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(new_password)
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "UPDATE lecturers SET password = %s WHERE id = %s",
                (hashed_pw, lecturer_id)
            )
        else:
            cursor.execute(
                "UPDATE lecturers SET password = ? WHERE id = ?",
                (hashed_pw, lecturer_id)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def update_admin_password(admin_id, new_password):
    """Update admin password with security"""
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(new_password)
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "UPDATE admins SET password = %s, last_password_change = CURRENT_TIMESTAMP WHERE id = %s",
                (hashed_pw, admin_id)
            )
        else:
            cursor.execute(
                "UPDATE admins SET password = ?, last_password_change = CURRENT_TIMESTAMP WHERE id = ?",
                (hashed_pw, admin_id)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_student_by_id(student_id):
    """Get student by ID"""
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
    else:
        cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()
    conn.close()
    return student

def get_lecturer_by_id(lecturer_id):
    """Get lecturer by ID"""
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute("SELECT * FROM lecturers WHERE id = %s", (lecturer_id,))
    else:
        cursor.execute("SELECT * FROM lecturers WHERE id = ?", (lecturer_id,))
    lecturer = cursor.fetchone()
    conn.close()
    return lecturer

# ==================== ADMIN SECURITY ENHANCEMENTS ====================

def log_admin_activity(admin_id, action, details, ip_address=''):
    """Log admin activities for security auditing"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO admin_activity_log (admin_id, action, details, ip_address) VALUES (%s, %s, %s, %s)",
                (admin_id, action, details, ip_address)
            )
        else:
            cursor.execute(
                "INSERT INTO admin_activity_log (admin_id, action, details, ip_address) VALUES (?, ?, ?, ?)",
                (admin_id, action, details, ip_address)
            )
        conn.commit()
    except:
        pass  # Don't break the app if logging fails
    finally:
        conn.close()

def get_recent_admin_activity(limit=10):
    """Get recent admin activities"""
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute('''
            SELECT al.*, a.email 
            FROM admin_activity_log al 
            JOIN admins a ON al.admin_id = a.id 
            ORDER BY al.timestamp DESC 
            LIMIT %s
        ''', (limit,))
    else:
        cursor.execute('''
            SELECT al.*, a.email 
            FROM admin_activity_log al 
            JOIN admins a ON al.admin_id = a.id 
            ORDER BY al.timestamp DESC 
            LIMIT ?
        ''', (limit,))
    activities = cursor.fetchall()
    conn.close()
    return activities

def get_admin_activity_log(admin_id):
    """Get activity log for specific admin"""
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute('''
            SELECT * FROM admin_activity_log 
            WHERE admin_id = %s 
            ORDER BY timestamp DESC
        ''', (admin_id,))
    else:
        cursor.execute('''
            SELECT * FROM admin_activity_log 
            WHERE admin_id = ? 
            ORDER BY timestamp DESC
        ''', (admin_id,))
    activities = cursor.fetchall()
    conn.close()
    return activities

# ==================== EXISTING FUNCTIONS (PRESERVED) ====================

def create_unit(code, title, lecturer_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO units (code, title, lecturer_id) VALUES (%s, %s, %s)",
                (code, title, lecturer_id)
            )
        else:
            cursor.execute(
                "INSERT INTO units (code, title, lecturer_id) VALUES (?, ?, ?)",
                (code, title, lecturer_id)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_units_by_lecturer(lecturer_id):
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute('''
            SELECT u.*, COUNT(su.student_id) as student_count 
            FROM units u 
            LEFT JOIN student_units su ON u.id = su.unit_id 
            WHERE u.lecturer_id = %s 
            GROUP BY u.id
        ''', (lecturer_id,))
    else:
        cursor.execute('''
            SELECT u.*, COUNT(su.student_id) as student_count 
            FROM units u 
            LEFT JOIN student_units su ON u.id = su.unit_id 
            WHERE u.lecturer_id = ? 
            GROUP BY u.id
        ''', (lecturer_id,))
    units = cursor.fetchall()
    conn.close()
    return units

def get_all_units():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.*, l.name as lecturer 
        FROM units u 
        LEFT JOIN lecturers l ON u.lecturer_id = l.id
    ''')
    units = cursor.fetchall()
    conn.close()
    return units

def get_all_units_with_details():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.*, l.name as lecturer_name, COUNT(su.student_id) as student_count
        FROM units u 
        LEFT JOIN lecturers l ON u.lecturer_id = l.id
        LEFT JOIN student_units su ON u.id = su.unit_id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    ''')
    units = cursor.fetchall()
    conn.close()
    return units

def register_student_unit(student_id, unit_code):
    conn = get_db()
    cursor = conn.cursor()
    
    # Get unit id from code
    if os.environ.get('DATABASE_URL'):
        cursor.execute("SELECT id FROM units WHERE code = %s", (unit_code,))
    else:
        cursor.execute("SELECT id FROM units WHERE code = ?", (unit_code,))
    unit = cursor.fetchone()
    
    if not unit:
        return False
    
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO student_units (student_id, unit_id) VALUES (%s, %s)",
                (student_id, unit['id'])
            )
        else:
            cursor.execute(
                "INSERT INTO student_units (student_id, unit_id) VALUES (?, ?)",
                (student_id, unit['id'])
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_student_units(student_id):
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute('''
            SELECT u.*, l.name as lecturer 
            FROM units u 
            JOIN student_units su ON u.id = su.unit_id 
            LEFT JOIN lecturers l ON u.lecturer_id = l.id 
            WHERE su.student_id = %s
        ''', (student_id,))
    else:
        cursor.execute('''
            SELECT u.*, l.name as lecturer 
            FROM units u 
            JOIN student_units su ON u.id = su.unit_id 
            LEFT JOIN lecturers l ON u.lecturer_id = l.id 
            WHERE su.student_id = ?
        ''', (student_id,))
    units = cursor.fetchall()
    conn.close()
    return units

def get_unit_students(unit_id):
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute('''
            SELECT s.*, r.score, r.remarks 
            FROM students s 
            JOIN student_units su ON s.id = su.student_id 
            LEFT JOIN results r ON s.id = r.student_id AND r.unit_id = %s
            WHERE su.unit_id = %s
        ''', (unit_id, unit_id))
    else:
        cursor.execute('''
            SELECT s.*, r.score, r.remarks 
            FROM students s 
            JOIN student_units su ON s.id = su.student_id 
            LEFT JOIN results r ON s.id = r.student_id AND r.unit_id = ?
            WHERE su.unit_id = ?
        ''', (unit_id, unit_id))
    students = cursor.fetchall()
    conn.close()
    return students

def update_student_result(student_id, unit_id, score, remarks):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute('''
                INSERT INTO results (student_id, unit_id, score, remarks)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (student_id, unit_id) 
                DO UPDATE SET score = %s, remarks = %s
            ''', (student_id, unit_id, score, remarks, score, remarks))
        else:
            cursor.execute('''
                INSERT OR REPLACE INTO results (student_id, unit_id, score, remarks)
                VALUES (?, ?, ?, ?)
            ''', (student_id, unit_id, score, remarks))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_student_results(student_id):
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute('''
            SELECT u.code, u.title, r.score, r.remarks 
            FROM results r 
            JOIN units u ON r.unit_id = u.id 
            WHERE r.student_id = %s
        ''', (student_id,))
    else:
        cursor.execute('''
            SELECT u.code, u.title, r.score, r.remarks 
            FROM results r 
            JOIN units u ON r.unit_id = u.id 
            WHERE r.student_id = ?
        ''', (student_id,))
    results = cursor.fetchall()
    conn.close()
    return results

def add_resource(unit_id, title, filename):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO resources (unit_id, title, filename) VALUES (%s, %s, %s)",
                (unit_id, title, filename)
            )
        else:
            cursor.execute(
                "INSERT INTO resources (unit_id, title, filename) VALUES (?, ?, ?)",
                (unit_id, title, filename)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_unit_resources(unit_id):
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute("SELECT * FROM resources WHERE unit_id = %s ORDER BY uploaded_at DESC", (unit_id,))
    else:
        cursor.execute("SELECT * FROM resources WHERE unit_id = ? ORDER BY uploaded_at DESC", (unit_id,))
    resources = cursor.fetchall()
    conn.close()
    return resources

def get_unit_by_id(unit_id):
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute('''
            SELECT u.*, l.name as lecturer_name 
            FROM units u 
            LEFT JOIN lecturers l ON u.lecturer_id = l.id 
            WHERE u.id = %s
        ''', (unit_id,))
    else:
        cursor.execute('''
            SELECT u.*, l.name as lecturer_name 
            FROM units u 
            LEFT JOIN lecturers l ON u.lecturer_id = l.id 
            WHERE u.id = ?
        ''', (unit_id,))
    unit = cursor.fetchone()
    conn.close()
    return unit

def get_upcoming_activities(student_id):
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute('''
            SELECT a.*, u.code as unit_code 
            FROM activities a 
            JOIN units u ON a.unit_id = u.id 
            JOIN student_units su ON u.id = su.unit_id 
            WHERE su.student_id = %s AND a.due_date >= CURRENT_DATE
            AND a.due_date <= CURRENT_DATE + INTERVAL '7 days'
            ORDER BY a.due_date
        ''', (student_id,))
    else:
        cursor.execute('''
            SELECT a.*, u.code as unit_code 
            FROM activities a 
            JOIN units u ON a.unit_id = u.id 
            JOIN student_units su ON u.id = su.unit_id 
            WHERE su.student_id = ? AND a.due_date >= date('now') 
            AND a.due_date <= date('now', '+7 days')
            ORDER BY a.due_date
        ''', (student_id,))
    activities = cursor.fetchall()
    conn.close()
    return activities

# ==================== ADMIN FUNCTIONS ====================

def get_all_students():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students ORDER BY created_at DESC")
    students = cursor.fetchall()
    conn.close()
    return students

def get_all_lecturers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lecturers ORDER BY created_at DESC")
    lecturers = cursor.fetchall()
    conn.close()
    return lecturers

def delete_student(student_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
        else:
            cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def delete_lecturer(lecturer_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("DELETE FROM lecturers WHERE id = %s", (lecturer_id,))
        else:
            cursor.execute("DELETE FROM lecturers WHERE id = ?", (lecturer_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def delete_unit(unit_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("DELETE FROM units WHERE id = %s", (unit_id,))
        else:
            cursor.execute("DELETE FROM units WHERE id = ?", (unit_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_all_results():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, s.name as student_name, s.admission_no, u.code as unit_code, u.title as unit_title,
               l.name as lecturer_name
        FROM results r
        JOIN students s ON r.student_id = s.id
        JOIN units u ON r.unit_id = u.id
        LEFT JOIN lecturers l ON u.lecturer_id = l.id
        ORDER BY r.recorded_at DESC
    ''')
    results = cursor.fetchall()
    conn.close()
    return results

def get_all_students_with_units():
    conn = get_db()
    cursor = conn.cursor()
    if os.environ.get('DATABASE_URL'):
        cursor.execute('''
            SELECT s.*, STRING_AGG(u.code, ', ') as registered_units
            FROM students s
            LEFT JOIN student_units su ON s.id = su.student_id
            LEFT JOIN units u ON su.unit_id = u.id
            GROUP BY s.id
            ORDER BY s.name
        ''')
    else:
        cursor.execute('''
            SELECT s.*, GROUP_CONCAT(u.code, ', ') as registered_units
            FROM students s
            LEFT JOIN student_units su ON s.id = su.student_id
            LEFT JOIN units u ON su.unit_id = u.id
            GROUP BY s.id
            ORDER BY s.name
        ''')
    students = cursor.fetchall()
    conn.close()
    return students

def admin_update_result(result_id, score, remarks):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "UPDATE results SET score = %s, remarks = %s WHERE id = %s",
                (score, remarks, result_id)
            )
        else:
            cursor.execute(
                "UPDATE results SET score = ?, remarks = ? WHERE id = ?",
                (score, remarks, result_id)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def admin_delete_result(result_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("DELETE FROM results WHERE id = %s", (result_id,))
        else:
            cursor.execute("DELETE FROM results WHERE id = ?", (result_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def admin_add_result(student_id, unit_id, score, remarks):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute(
                "INSERT INTO results (student_id, unit_id, score, remarks) VALUES (%s, %s, %s, %s)",
                (student_id, unit_id, score, remarks)
            )
        else:
            cursor.execute(
                "INSERT INTO results (student_id, unit_id, score, remarks) VALUES (?, ?, ?, ?)",
                (student_id, unit_id, score, remarks)
            )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()
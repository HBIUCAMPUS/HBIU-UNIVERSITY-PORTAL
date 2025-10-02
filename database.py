import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

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

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Use simplified table creation that works for both databases
        tables_sql = [
            # Students table
            '''
            CREATE TABLE IF NOT EXISTS students (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                admission_no TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            
            # Lecturers table
            '''
            CREATE TABLE IF NOT EXISTS lecturers (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            
            # Admins table
            '''
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'admin',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            '''
        ]
        
        # Execute all table creation statements
        for sql in tables_sql:
            try:
                cursor.execute(sql)
            except Exception as e:
                print(f"Table creation warning: {e}")
                continue
        
        conn.commit()
        print("✅ Database tables initialized successfully")
        
        # Create default admin account
        create_default_admin()
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        conn.rollback()
    finally:
        conn.close()

def create_default_admin():
    """Create a default admin account if none exists"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if any admin exists
        cursor.execute("SELECT COUNT(*) FROM admins")
        admin_count = cursor.fetchone()[0]
        
        if admin_count == 0:
            # Create default admin
            hashed_pw = generate_password_hash('Admin123!@#')
            cursor.execute(
                "INSERT INTO admins (email, password, role) VALUES (%s, %s, %s)",
                ('admin@hbi.edu', hashed_pw, 'super_admin')
            )
            conn.commit()
            print("✅ Default admin created: admin@hbi.edu / Admin123!@#")
        else:
            print(f"ℹ️ Admin accounts already exist: {admin_count} accounts found")
            
    except Exception as e:
        print(f"Error creating default admin: {e}")
        conn.rollback()
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
                'password': student[4]
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

def create_student(name, email, admission_no, password):
    """Create a new student account"""
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(password)
    
    try:
        cursor.execute(
            "INSERT INTO students (name, email, admission_no, password) VALUES (%s, %s, %s, %s)",
            (name, email, admission_no, hashed_pw)
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
                'password': student[4]
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
        cursor.execute("SELECT * FROM students ORDER BY created_at DESC")
        students = []
        for row in cursor.fetchall():
            students.append({
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'admission_no': row[3],
                'created_at': row[5] if len(row) > 5 else None
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
                'score': row[5] if len(row) > 5 else None,
                'remarks': row[6] if len(row) > 6 else None
            })
        return students
    except Exception as e:
        print(f"Error getting unit students: {e}")
        return []
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

def get_all_results():
    """Get all results"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT r.*, s.name as student_name, s.admission_no, u.code as unit_code, u.title as unit_title
            FROM results r
            JOIN students s ON r.student_id = s.id
            JOIN units u ON r.unit_id = u.id
            ORDER BY r.recorded_at DESC
        ''')
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'student_id': row[1],
                'unit_id': row[2],
                'score': row[3],
                'remarks': row[4],
                'student_name': row[6] if len(row) > 6 else 'Unknown',
                'admission_no': row[7] if len(row) > 7 else 'Unknown',
                'code': row[8] if len(row) > 8 else 'Unknown',
                'title': row[9] if len(row) > 9 else 'Unknown'
            })
        return results
    except Exception as e:
        print(f"Error getting all results: {e}")
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
                'unit_count': row[5] if len(row) > 5 else 0
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
    return []

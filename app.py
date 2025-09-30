# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
import database as db
import os
from werkzeug.utils import secure_filename
from flask import send_from_directory
from functools import wraps
from datetime import datetime, timedelta
import pickle
import json
app = Flask(__name__)

# -------------------
# Enhanced Security Configuration for Render
# -------------------
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-dev-only')
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')

# Security headers middleware
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    if os.environ.get('DATABASE_URL'):  # Production - enforce HTTPS
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# Ensure upload directory exists (works on both local and Render)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# -------------------
# Security Utilities
# -------------------
class Security:
    @staticmethod
    def validate_password_strength(password):
        """Validate password meets security requirements"""
        import re
        errors = []
        
        if len(password) < 8:
            errors.append("Must be at least 8 characters long")
        
        if not re.search(r"[A-Z]", password):
            errors.append("Must contain at least one uppercase letter (A-Z)")
        
        if not re.search(r"[a-z]", password):
            errors.append("Must contain at least one lowercase letter (a-z)")
        
        if not re.search(r"\d", password):
            errors.append("Must contain at least one number (0-9)")
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            errors.append("Must contain at least one special character (!@#$% etc.)")
        
        if errors:
            return False, errors
        else:
            return True, "Password meets all security requirements"

    @staticmethod
    def generate_secure_password(length=12):
        """Generate a secure random password"""
        import secrets
        import string
        characters = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(characters) for _ in range(length))

    @staticmethod
    def validate_admin_session(session, request):
        """Validate admin session security"""
        if 'admin_id' not in session:
            return False, "Not logged in"
        
        if 'login_time' in session:
            try:
                login_time = datetime.fromisoformat(session['login_time'])
                if datetime.now() - login_time > timedelta(hours=2):
                    return False, "Session expired"
            except:
                return False, "Invalid session data"
        
        if 'ip_address' in session and session['ip_address'] != request.remote_addr:
            return False, "Session security violation"
        
        return True, "Session valid"

# Rate limiting for login attempts
failed_attempts = {}

def check_login_attempts(ip_address, max_attempts=5, lockout_time=15):
    """Check if IP has exceeded login attempts"""
    from datetime import datetime, timedelta
    now = datetime.now()
    
    if ip_address in failed_attempts:
        attempts, last_attempt = failed_attempts[ip_address]
        
        if now - last_attempt > timedelta(minutes=lockout_time):
            del failed_attempts[ip_address]
        elif attempts >= max_attempts:
            return False, f"Too many login attempts. Try again in {lockout_time} minutes."
    
    return True, "OK"

def record_failed_attempt(ip_address):
    """Record a failed login attempt"""
    from datetime import datetime
    now = datetime.now()
    
    if ip_address in failed_attempts:
        attempts, _ = failed_attempts[ip_address]
        failed_attempts[ip_address] = (attempts + 1, now)
    else:
        failed_attempts[ip_address] = (1, now)

def clear_login_attempts(ip_address):
    """Clear failed attempts on successful login"""
    if ip_address in failed_attempts:
        del failed_attempts[ip_address]

# -------------------
# Enhanced Admin Authentication Decorator
# -------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from datetime import timedelta
        
        # Check session validity
        session_valid, message = Security.validate_admin_session(session, request)
        if not session_valid:
            flash(f'Security alert: {message}', 'danger')
            session.clear()
            return redirect(url_for('admin_login'))
        
        # Check if user is actually an admin in database (prevent session hijacking)
        if 'admin_id' in session:
            admin = db.get_admin_by_id(session['admin_id'])
            if not admin:
                flash('Security alert: Admin account not found', 'danger')
                session.clear()
                return redirect(url_for('admin_login'))
        
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """Require super admin privileges for sensitive operations"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session or session.get('admin_role') != 'super_admin':
            flash('Super admin privileges required for this action.', 'danger')
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------
# Google Classroom Integration (Simplified)
# -------------------
class GoogleClassroomService:
    def __init__(self):
        self.creds = None
        self.service = None
        
    def get_credentials(self, user_id=None):
        """Get or create Google API credentials for a user"""
        return "https://example.com/auth"  # Placeholder
    
    def get_authorization_url(self, user_id=None):
        """Get authorization URL for OAuth flow"""
        return "https://example.com/auth"  # Placeholder
    
    def save_credentials_from_flow(self, authorization_response, user_id=None):
        """Save credentials from authorization flow"""
        return True

# Global service instance
classroom_service = GoogleClassroomService()

def get_user_courses(user_id=None):
    """Get all courses for the authenticated user"""
    return [], None  # Placeholder

# -------------------
# JotForm Integration
# -------------------
class JotFormService:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv('JOTFORM_API_KEY')
        self.base_url = "https://api.jotform.com"
        self.headers = {
            'APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
    
    def get_forms(self, limit=50, offset=0):
        """Get all forms from JotForm account"""
        try:
            import requests
            url = f"{self.base_url}/user/forms"
            params = {
                'limit': limit,
                'offset': offset,
                'orderby': 'created_at'
            }
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            return response.json().get('content', [])
        except Exception as e:
            print(f"Error fetching forms: {e}")
            return []
    
    def get_form(self, form_id):
        """Get specific form details"""
        try:
            import requests
            url = f"{self.base_url}/form/{form_id}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            return response.json().get('content', {})
        except Exception as e:
            print(f"Error fetching form {form_id}: {e}")
            return {}
    
    def get_form_submissions(self, form_id, limit=100, offset=0):
        """Get submissions for a specific form"""
        try:
            import requests
            url = f"{self.base_url}/form/{form_id}/submissions"
            params = {
                'limit': limit,
                'offset': offset,
                'orderby': 'created_at'
            }
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            return response.json().get('content', [])
        except Exception as e:
            print(f"Error fetching submissions for form {form_id}: {e}")
            return []

# Global JotForm service instance
jotform_service = JotFormService()

# -------------------
# Routes (ALL EXISTING FUNCTIONALITY PRESERVED)
# -------------------
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route("/")
def home():
    if 'user_id' in session and 'user_type' in session:
        if session['user_type'] == 'student':
            return redirect(url_for('student_dashboard'))
        elif session['user_type'] == 'lecturer':
            return redirect(url_for('lecturer_dashboard'))
    return render_template("home.html")

@app.route("/home")
def home_route():
    """Home page route"""
    return redirect(url_for('home'))

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Try student login first
        student = db.verify_student(email, password)
        if student:
            session['user_id'] = student['id']
            session['user_type'] = 'student'
            session['user_name'] = student['name']
            flash('Login successful!', 'success')
            return redirect(url_for('student_dashboard'))
        
        # Try lecturer login
        lecturer = db.verify_lecturer(email, password)
        if lecturer:
            session['user_id'] = lecturer['id']
            session['user_type'] = 'lecturer'
            session['user_name'] = lecturer['name']
            flash('Login successful!', 'success')
            return redirect(url_for('lecturer_dashboard'))
        
        flash('Invalid email or password', 'danger')
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('home'))

@app.route("/register/student", methods=['GET', 'POST'])
def register_student():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        admission_no = request.form['admission_no']
        password = request.form['password']
        
        if db.create_student(name, email, admission_no, password):
            flash('Student account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Email or admission number already exists', 'danger')
    
    return render_template("register_students.html")

@app.route("/register/lecturer", methods=['GET', 'POST'])
def register_lecturer():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        
        if db.create_lecturer(name, email, password):
            flash('Lecturer account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Email already exists', 'danger')
    
    return render_template("register_lecturer.html")

@app.route("/student/dashboard")
def student_dashboard():
    if 'user_id' not in session or session['user_type'] != 'student':
        flash('Please login as student', 'warning')
        return redirect(url_for('login'))
    
    registered_units = db.get_student_units(session['user_id'])
    results = db.get_student_results(session['user_id'])
    activities = db.get_upcoming_activities(session['user_id'])
    
    return render_template("students_dashboard.html", 
                         registered=registered_units, 
                         results=results, 
                         activities=activities)

@app.route("/lecturer/dashboard")
def lecturer_dashboard():
    if 'user_id' not in session or session['user_type'] != 'lecturer':
        flash('Please login as lecturer', 'warning')
        return redirect(url_for('login'))
    
    units = db.get_units_by_lecturer(session['user_id'])
    return render_template("lecturer_dashboard.html", units=units)

@app.route("/lecturer/create-unit", methods=['GET', 'POST'])
def create_unit():
    if 'user_id' not in session or session['user_type'] != 'lecturer':
        flash('Please login as lecturer', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        code = request.form['code']
        title = request.form['title']
        
        if db.create_unit(code, title, session['user_id']):
            flash('Unit created successfully!', 'success')
            return redirect(url_for('lecturer_dashboard'))
        else:
            flash('Unit code already exists', 'danger')
    
    return render_template("create_unit.html")

@app.route("/units")
def view_units():
    if 'user_id' not in session or session['user_type'] != 'student':
        flash('Please login as student', 'warning')
        return redirect(url_for('login'))
    
    units = db.get_all_units()
    return render_template("view_units.html", units=units)

@app.route("/units/register", methods=['POST'])
def register_unit():
    if 'user_id' not in session or session['user_type'] != 'student':
        flash('Please login as student', 'warning')
        return redirect(url_for('login'))
    
    unit_code = request.form['code']
    if db.register_student_unit(session['user_id'], unit_code):
        flash('Unit registered successfully!', 'success')
    else:
        flash('Invalid unit code or already registered', 'danger')
    
    return redirect(url_for('view_units'))

@app.route("/unit/<int:unit_id>")
def unit_detail(unit_id):
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('home'))
    
    resources = db.get_unit_resources(unit_id)
    
    students = None
    if 'user_type' in session and session['user_type'] == 'lecturer':
        students = db.get_unit_students(unit_id)
    
    return render_template("unit_detail.html", unit=unit, resources=resources, students=students)

@app.route("/lecturer/unit/<int:unit_id>/results", methods=['GET', 'POST'])
def unit_results(unit_id):
    if 'user_id' not in session or session['user_type'] != 'lecturer':
        flash('Please login as lecturer', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        student_id = request.form['student_id']
        score = request.form['score']
        remarks = request.form.get('remarks', '')
        
        if db.update_student_result(student_id, unit_id, score, remarks):
            flash('Result updated successfully!', 'success')
        else:
            flash('Error updating result', 'danger')
    
    students = db.get_unit_students(unit_id)
    return render_template("results.html", students=students, unit_id=unit_id)

@app.route("/lecturer/unit/<int:unit_id>/upload", methods=['GET', 'POST'])
def upload_resource(unit_id):
    if 'user_id' not in session or session['user_type'] != 'lecturer':
        flash('Please login as lecturer', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        file = request.files['file']
        
        if file and file.filename:
            filename = secure_filename(file.filename)
            # Use Render's persistent disk storage
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            if db.add_resource(unit_id, title, filename):
                flash('Resource uploaded successfully!', 'success')
                return redirect(url_for('unit_detail', unit_id=unit_id))
            else:
                flash('Error uploading resource', 'danger')
    
    return render_template("upload_resource.html")

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/student/results")
def student_results():
    if 'user_id' not in session or session['user_type'] != 'student':
        flash('Please login as student', 'warning')
        return redirect(url_for('login'))
    
    results = db.get_student_results(session['user_id'])
    return render_template("students_results.html", results=results)

@app.route("/test")
def test():
    return "✅ Flask is working and connected to database!"

# ==================== UPDATE PROFILE ROUTE ====================

@app.route("/update-profile", methods=['GET', 'POST'])
def update_profile():
    """Update user profile information"""
    if 'user_id' not in session or 'user_type' not in session:
        flash('Please log in to update your profile', 'warning')
        return redirect(url_for('login'))
    
    user_type = session['user_type']
    user_id = session['user_id']
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        
        if not name or not email:
            flash('Please fill in all fields', 'danger')
            return render_template("update_profile.html")
        
        # Update based on user type using database functions
        success = False
        try:
            if user_type == 'student':
                # Use database function to update student profile
                conn = db.get_db()
                cursor = conn.cursor()
                if os.environ.get('DATABASE_URL'):
                    cursor.execute("UPDATE students SET name = %s, email = %s WHERE id = %s", (name, email, user_id))
                else:
                    cursor.execute("UPDATE students SET name = ?, email = ? WHERE id = ?", (name, email, user_id))
                conn.commit()
                conn.close()
                session['user_name'] = name
                success = True
                
            elif user_type == 'lecturer':
                # Use database function to update lecturer profile
                conn = db.get_db()
                cursor = conn.cursor()
                if os.environ.get('DATABASE_URL'):
                    cursor.execute("UPDATE lecturers SET name = %s, email = %s WHERE id = %s", (name, email, user_id))
                else:
                    cursor.execute("UPDATE lecturers SET name = ?, email = ? WHERE id = ?", (name, email, user_id))
                conn.commit()
                conn.close()
                session['user_name'] = name
                success = True
                
            elif user_type == 'admin':
                # Use database function to update admin email
                conn = db.get_db()
                cursor = conn.cursor()
                if os.environ.get('DATABASE_URL'):
                    cursor.execute("UPDATE admins SET email = %s WHERE id = %s", (email, user_id))
                else:
                    cursor.execute("UPDATE admins SET email = ? WHERE id = ?", (email, user_id))
                conn.commit()
                conn.close()
                session['admin_email'] = email
                success = True
            
        except Exception as e:
            print(f"Profile update error: {e}")
            flash('Error updating profile. Please try again.', 'danger')
        
        if success:
            flash('Profile updated successfully!', 'success')
            # Redirect based on user type
            if user_type == 'student':
                return redirect(url_for('student_dashboard'))
            elif user_type == 'lecturer':
                return redirect(url_for('lecturer_dashboard'))
            else:
                return redirect(url_for('admin_dashboard'))
    
    # GET request - load current user data
    user_data = None
    if user_type == 'student':
        user_data = db.get_student_by_id(user_id)
    elif user_type == 'lecturer':
        user_data = db.get_lecturer_by_id(user_id)
    elif user_type == 'admin':
        user_data = db.get_admin_by_id(user_id)
    
    return render_template("update_profile.html", user_data=user_data, user_type=user_type)

# ==================== JOTFORM ROUTES ====================

@app.route('/jotform/forms')
def jotform_forms():
    """JotForm forms dashboard"""
    if 'admin_id' not in session and 'lecturer_id' not in session:
        flash('Please login as admin or lecturer to access forms', 'error')
        return redirect(url_for('login'))
    
    # Get university units for the logged-in user
    if 'admin_id' in session:
        units = db.get_all_units_with_details()
    else:
        lecturer_id = session.get('lecturer_id')
        units = db.get_units_by_lecturer(lecturer_id) if lecturer_id else []
    
    # Placeholder for forms data
    forms = []
    
    return render_template('jotform_forms.html', 
                         forms=forms, 
                         units=units,
                         user_type=session.get('user_type'))

@app.route('/jotform/create-course-form/<int:unit_id>')
def create_course_registration_form(unit_id):
    """Create a course registration form in JotForm"""
    if 'admin_id' not in session and 'lecturer_id' not in session:
        return redirect(url_for('login'))
    
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'error')
        return redirect(url_for('jotform_forms'))
    
    flash(f'Course registration form for "{unit["code"]}" coming soon!', 'info')
    return redirect(url_for('jotform_forms'))

@app.route('/jotform/webhook', methods=['POST'])
def jotform_webhook():
    """Handle JotForm webhook notifications"""
    # This will handle form submissions from JotForm
    return jsonify({'status': 'webhook received'})

# ==================== GOOGLE CLASSROOM ROUTES ====================

@app.route('/google-classroom')
def google_classroom_dashboard():
    """Google Classroom integration dashboard"""
    if 'admin_id' not in session and 'lecturer_id' not in session:
        flash('Please login as admin or lecturer to access Google Classroom', 'error')
        return redirect(url_for('login'))
    
    # Get user ID based on who's logged in
    user_id = session.get('admin_id') or session.get('lecturer_id')
    
    # Get Google Classroom courses (you'll implement this later)
    courses = []  # Placeholder - will be populated with real data
    
    # Get university units for the logged-in user
    if 'admin_id' in session:
        units = db.get_all_units_with_details()
    else:
        lecturer_id = session.get('lecturer_id')
        units = db.get_units_by_lecturer(lecturer_id) if lecturer_id else []
    
    return render_template('google_classroom.html', 
                         courses=courses, 
                         units=units,
                         user_type=session.get('user_type'))

@app.route('/google/connect')
def google_connect():
    """Initiate Google OAuth flow"""
    if 'admin_id' not in session and 'lecturer_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login'))
    
    # This will redirect to Google OAuth
    flash('Google Classroom connection coming soon!', 'info')
    return redirect(url_for('google_classroom_dashboard'))

@app.route('/sync-unit/<int:unit_id>')
def sync_unit_to_classroom(unit_id):
    """Sync a unit to Google Classroom - ENHANCED FEEDBACK"""
    if 'admin_id' not in session and 'lecturer_id' not in session:
        flash('Please log in to sync units', 'error')
        return redirect(url_for('login'))
    
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'error')
        return redirect(url_for('google_classroom_dashboard'))
    
    try:
        # Get additional unit details for better feedback
        units_with_details = db.get_all_units_with_details()
        unit_detail = next((u for u in units_with_details if u['id'] == unit_id), None)
        
        if unit_detail:
            lecturer_name = unit_detail.get('lecturer_name', 'Not assigned')
            student_count = unit_detail.get('student_count', 0)
            
            # Enhanced flash message with more details
            flash(
                f'Sync initiated for "{unit["code"]} - {unit["title"]}"! '
                f'(Lecturer: {lecturer_name}, Students: {student_count}) - '
                f'Feature coming soon!', 
                'info'
            )
        else:
            # Fallback to basic message if details not available
            flash(f'Unit "{unit["code"]}" sync feature coming soon!', 'info')
            
        # Log the sync attempt for debugging
        print(f"SYNC ATTEMPT: Unit {unit_id} ({unit['code']}) - User: {session.get('admin_id') or session.get('lecturer_id')}")
        
    except Exception as e:
        # If anything goes wrong, still provide basic functionality
        print(f"Sync info error (non-critical): {e}")
        flash(f'Unit "{unit["code"]}" sync feature coming soon!', 'info')
    
    return redirect(url_for('google_classroom_dashboard'))

# -------------------
# Enhanced Admin Routes with Security
# -------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        try:
            admin = db.verify_admin(email, password)
            if admin:
                session['admin_id'] = admin['id']
                session['admin_email'] = admin['email']
                session['user_type'] = 'admin'
                
                # FIXED: Use dictionary-style access for sqlite3.Row
                session['admin_role'] = admin['role'] if 'role' in admin else 'admin'
                
                # Log the login activity
                db.log_admin_activity(admin['id'], 'LOGIN', 'Admin logged in', request.remote_addr)
                
                flash('Login successful!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid email or password', 'error')
        except Exception as e:
            print(f"Admin login error: {e}")
            flash('Login error. Please try again.', 'error')
    
    return render_template('admin_login.html')

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    stats = {
        'students_count': len(db.get_all_students()),
        'lecturers_count': len(db.get_all_lecturers()),
        'units_count': len(db.get_all_units_with_details()),
        'registrations_count': len(db.get_all_students()) + len(db.get_all_lecturers()),
        'recent_activity': db.get_recent_admin_activity(5)
    }
    return render_template("admin.html", stats=stats)

@app.route("/admin/students")
@admin_required
def admin_students():
    students = db.get_all_students()
    return render_template("admin_students.html", students=students)

@app.route("/admin/lecturers")
@admin_required
def admin_lecturers():
    lecturers = db.get_all_lecturers()
    return render_template("admin_lecturers.html", lecturers=lecturers)

@app.route("/admin/units")
@admin_required
def admin_units():
    units = db.get_all_units_with_details()
    return render_template("admin_units.html", units=units)

@app.route("/admin/create-user", methods=['GET', 'POST'])
@admin_required
def admin_create_user():
    if request.method == 'POST':
        user_type = request.form['user_type']
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        
        if user_type == 'student':
            admission_no = request.form['admission_no']
            if db.create_student(name, email, admission_no, password):
                db.log_admin_activity(session['admin_id'], 'create_student', f'Created student: {email}')
                flash('Student created successfully!', 'success')
            else:
                flash('Email or admission number already exists', 'danger')
        else:
            if db.create_lecturer(name, email, password):
                db.log_admin_activity(session['admin_id'], 'create_lecturer', f'Created lecturer: {email}')
                flash('Lecturer created successfully!', 'success')
            else:
                flash('Email already exists', 'danger')
        
        return redirect(url_for('admin_dashboard'))
    
    return render_template("admin_create_user.html")

@app.route("/admin/create-unit", methods=['GET', 'POST'])
@admin_required
def admin_create_unit():
    if request.method == 'POST':
        code = request.form['code']
        title = request.form['title']
        lecturer_id = request.form['lecturer_id']
        
        if db.create_unit(code, title, lecturer_id):
            db.log_admin_activity(session['admin_id'], 'create_unit', f'Created unit: {code}')
            flash('Unit created successfully!', 'success')
        else:
            flash('Unit code already exists', 'danger')
        
        return redirect(url_for('admin_dashboard'))
    
    lecturers = db.get_all_lecturers()
    return render_template("admin_create_unit.html", lecturers=lecturers)

# ==================== PASSWORD MANAGEMENT ROUTES ====================

@app.route("/change-password", methods=['GET', 'POST'])
def change_password():
    """Universal password change route for all user types"""
    if 'user_id' not in session or 'user_type' not in session:
        flash('Please log in to change your password', 'warning')
        return redirect(url_for('login'))
    
    user_type = session['user_type']
    user_id = session['user_id']
    
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Validate input
        if not all([current_password, new_password, confirm_password]):
            flash('Please fill in all fields', 'danger')
            return render_template("change_password.html")
        
        # Check if new passwords match
        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return render_template("change_password.html")
        
        # Validate password strength
        is_strong, message = Security.validate_password_strength(new_password)
        if not is_strong:
            flash('Password does not meet security requirements:', 'danger')
            for error in message:
                flash(f'- {error}', 'danger')
            return render_template("change_password.html")
        
        # Verify current password
        if not db.verify_current_password(user_type, user_id, current_password):
            flash('Current password is incorrect', 'danger')
            return render_template("change_password.html")
        
        # Update password based on user type
        success = False
        if user_type == 'student':
            success = db.update_student_password(user_id, new_password)
            user_name = session.get('user_name', 'Student')
        elif user_type == 'lecturer':
            success = db.update_lecturer_password(user_id, new_password)
            user_name = session.get('user_name', 'Lecturer')
        elif user_type == 'admin':
            success = db.update_admin_password(user_id, new_password)
            user_name = session.get('user_name', 'Admin')
            db.log_admin_activity(user_id, 'password_change', 'Password updated successfully')
        
        if success:
            flash('Password changed successfully!', 'success')
            
            # Redirect based on user type
            if user_type == 'student':
                return redirect(url_for('student_dashboard'))
            elif user_type == 'lecturer':
                return redirect(url_for('lecturer_dashboard'))
            else:
                return redirect(url_for('admin_dashboard'))
        else:
            flash('Error changing password. Please try again.', 'danger')
    
    return render_template("change_password.html")

@app.route("/admin/change-password", methods=['GET', 'POST'])
@admin_required
def admin_change_password():
    """Admin-specific password change"""
    return change_password()

# ==================== ADMIN RESULTS ROUTES ====================

@app.route("/admin/results")
@admin_required
def admin_results():
    results = db.get_all_results()
    return render_template("admin_results.html", results=results)

@app.route("/admin/results/add", methods=['GET', 'POST'])
@admin_required
def admin_results_add():
    if request.method == 'POST':
        student_id = request.form['student_id']
        unit_id = request.form['unit_id']
        score = request.form['score']
        remarks = request.form.get('remarks', '')
        
        if db.admin_add_result(student_id, unit_id, score, remarks):
            db.log_admin_activity(session['admin_id'], 'add_result', f'Added result for student ID: {student_id}')
            flash('Result added successfully!', 'success')
            return redirect(url_for('admin_results'))
        else:
            flash('Error adding result', 'danger')
    
    students = db.get_all_students_with_units()
    units = db.get_all_units()
    return render_template("admin_results_add.html", students=students, units=units)

@app.route("/admin/results/edit/<int:result_id>", methods=['GET', 'POST'])
@admin_required
def admin_results_edit(result_id):
    # We need to get the specific result first
    all_results = db.get_all_results()
    result = None
    for r in all_results:
        if r['id'] == result_id:
            result = r
            break
    
    if not result:
        flash('Result not found', 'danger')
        return redirect(url_for('admin_results'))
    
    if request.method == 'POST':
        score = request.form['score']
        remarks = request.form.get('remarks', '')
        
        if db.admin_update_result(result_id, score, remarks):
            db.log_admin_activity(session['admin_id'], 'edit_result', f'Edited result ID: {result_id}')
            flash('Result updated successfully!', 'success')
            return redirect(url_for('admin_results'))
        else:
            flash('Error updating result', 'danger')
    
    return render_template("admin_results_edit.html", result=result)

@app.route("/admin/results/delete/<int:result_id>", methods=['POST'])
@admin_required
def admin_results_delete(result_id):
    if db.admin_delete_result(result_id):
        db.log_admin_activity(session['admin_id'], 'delete_result', f'Deleted result ID: {result_id}')
        flash('Result deleted successfully!', 'success')
    else:
        flash('Error deleting result', 'danger')
    return redirect(url_for('admin_results'))

# Enhanced sensitive operations require super admin
@app.route("/admin/delete-student/<int:student_id>", methods=['POST'])
@super_admin_required
def admin_delete_student(student_id):
    if db.delete_student(student_id):
        db.log_admin_activity(session['admin_id'], 'delete_student', f'Deleted student ID: {student_id}')
        flash('Student deleted successfully!', 'success')
    else:
        flash('Error deleting student', 'danger')
    return redirect(url_for('admin_students'))

@app.route("/admin/delete-lecturer/<int:lecturer_id>", methods=['POST'])
@super_admin_required
def admin_delete_lecturer(lecturer_id):
    if db.delete_lecturer(lecturer_id):
        db.log_admin_activity(session['admin_id'], 'delete_lecturer', f'Deleted lecturer ID: {lecturer_id}')
        flash('Lecturer deleted successfully!', 'success')
    else:
        flash('Error deleting lecturer', 'danger')
    return redirect(url_for('admin_lecturers'))

@app.route("/admin/delete-unit/<int:unit_id>", methods=['POST'])
@super_admin_required
def admin_delete_unit(unit_id):
    if db.delete_unit(unit_id):
        db.log_admin_activity(session['admin_id'], 'delete_unit', f'Deleted unit ID: {unit_id}')
        flash('Unit deleted successfully!', 'success')
    else:
        flash('Error deleting unit', 'danger')
    return redirect(url_for('admin_units'))

@app.route("/admin/activity-log")
@admin_required
def admin_activity_log():
    activities = db.get_admin_activity_log(session['admin_id'])
    return render_template("admin_activity_log.html", activities=activities)

@app.route("/admin/logout")
def admin_logout():
    if 'admin_id' in session:
        db.log_admin_activity(session['admin_id'], 'logout', 'Admin logged out')
    
    # Secure session cleanup
    session.clear()
    flash('Admin logged out successfully', 'info')
    return redirect(url_for('home'))

# -------------------
# Error handling
# -------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500

# -------------------
# Run app (OPTIMIZED FOR RENDER)
# -------------------
# -------------------
# Run app (OPTIMIZED FOR RENDER)
# -------------------
if __name__ == "__main__":
    # Import here to avoid circular imports
    from datetime import timedelta
    
    # Initialize database within app context
    with app.app_context():
        db.init_db()
    
    # Create default super admin account (run only once)
    try:
        db.create_super_admin('admin@hbi.edu', 'Admin123!@#')
        print("✅ Default super admin account created: admin@hbi.edu / Admin123!@#")
    except:
        print("ℹ️ Admin account already exists or error creating admin")
    
    # Render-compatible configuration
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    
    # Run app with debug mode to see errors
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
else:
    # This runs when using Gunicorn (Render production)
    with app.app_context():
        db.init_db()
        try:
            db.create_super_admin('admin@hbi.edu', 'Admin123!@#')
            print("✅ Database initialized for production")
        except:
            print("ℹ️ Database already initialized")

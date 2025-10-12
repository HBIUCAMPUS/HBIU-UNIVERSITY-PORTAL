# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
import database as db
import os
from werkzeug.utils import secure_filename
from flask import send_from_directory
from functools import wraps
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import pickle
import json

# NEW IMPORTS FOR GOOGLE LOGIN & 2FA
from authlib.integrations.flask_client import OAuth
from flask_mail import Mail
import pyotp
import qrcode
import io
import base64
from flask_mail import Mail, Message  # Make sure Message is included

app = Flask(__name__)

# -------------------
# Enhanced Security Configuration for Render
# -------------------
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-dev-only')
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')

# NEW: Google OAuth Configuration
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_OAUTH_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET'),
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    client_kwargs={
        'scope': 'openid email profile'
    }
)
# NEW: Flask-Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'hbiuportal@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')  # Your app password
app.config['MAIL_DEFAULT_SENDER'] = 'hbiuportal@gmail.com'

mail = Mail(app)
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
        # Keep the placeholder for existing functionality
        return "https://example.com/auth"  # Placeholder
    
    def get_authorization_url(self, user_id=None):
        """Get authorization URL for OAuth flow"""
        # Enhanced: Return real Google OAuth URL while maintaining placeholder functionality
        # This URL will work if you implement actual OAuth later
        return "https://accounts.google.com/o/oauth2/auth?scope=https://www.googleapis.com/auth/classroom.courses&response_type=code"
    
    def save_credentials_from_flow(self, authorization_response, user_id=None):
        """Save credentials from authorization flow"""
        # Keep existing functionality
        return True
    
    def create_course(self, course_data):
        """Create a Google Classroom course - NEW METHOD (doesn't break existing code)"""
        # This is a new method that won't affect existing functionality
        print(f"DEMO: Would create Google Classroom course: {course_data}")
        # Return demo data that matches expected format
        return {
            'id': f"demo_course_{course_data.get('name', '').replace(' ', '_').lower()}",
            'name': course_data.get('name', 'Demo Course'),
            'section': course_data.get('section', ''),
            'description': course_data.get('description', ''),
            'courseState': 'ACTIVE'
        }

# Global service instance (unchanged)
classroom_service = GoogleClassroomService()

def get_user_courses(user_id=None):
    """Get all courses for the authenticated user"""
    # Return empty list as before - no changes to existing functionality
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
# NEW: Google OAuth and 2FA Routes (Added without affecting existing routes)
# -------------------
@app.route('/create-my-admin')
def create_my_admin():
    """Temporary route to create hbiuportal@gmail.com admin account"""
    try:
        from werkzeug.security import generate_password_hash
        
        conn = db.get_db()
        cursor = conn.cursor()
        
        # Check if admin already exists
        cursor.execute("SELECT * FROM admins WHERE email = %s", ('hbiuportal@gmail.com',))
        existing_admin = cursor.fetchone()
        
        if existing_admin:
            return "✅ Admin hbiuportal@gmail.com already exists"
        
        # Create new admin account
        hashed_pw = generate_password_hash('#Ausbildung2025')
        cursor.execute(
            "INSERT INTO admins (email, password, role) VALUES (%s, %s, %s)",
            ('hbiuportal@gmail.com', hashed_pw, 'super_admin')
        )
        conn.commit()
        conn.close()
        
        return """
        ✅ Admin account created successfully!
        Email: hbiuportal@gmail.com
        Password: #Ausbildung2025
        Role: super_admin
        
        You can now login at /admin/login
        """
        
    except Exception as e:
        return f"❌ Error creating admin: {str(e)}"

@app.route('/login/google')
def google_login():
    """Initiate Google OAuth login - NEW ROUTE"""
    try:
        redirect_uri = url_for('google_callback', _external=True)
        return google.authorize_redirect(redirect_uri)
    except Exception as e:
        print(f"Google OAuth error: {e}")
        flash('Google login is currently unavailable. Please use email login.', 'error')
        return redirect(url_for('login'))

@app.route('/login/google/callback')
def google_callback():
    """Google OAuth callback - NEW ROUTE"""
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if user_info:
            # Check if user exists in database by Google ID
            student = db.get_student_by_google_id(user_info['sub'])
            if not student:
                # Check by email
                student = db.get_student_by_email(user_info['email'])
                if student:
                    # Link Google account to existing student
                    db.update_student_google_id(student['id'], user_info['sub'])
                else:
                    # Store Google user info for registration
                    session['google_user'] = {
                        'sub': user_info['sub'],
                        'name': user_info['name'],
                        'email': user_info['email'],
                        'picture': user_info.get('picture', '')
                    }
                    return redirect(url_for('google_register'))
            
            # Check if 2FA is enabled
            if student.get('totp_secret'):
                session['pre_2fa_user'] = {
                    'id': student['id'],
                    'type': 'student',
                    'email': student['email'],
                    'name': student['name']
                }
                return redirect(url_for('verify_2fa'))
            else:
                session['user_id'] = student['id']
                session['user_type'] = 'student'
                session['user_email'] = student['email']
                session['user_name'] = student['name']
                flash('Google login successful!', 'success')
                return redirect(url_for('student_dashboard'))
    
    except Exception as e:
        print(f"Google OAuth callback error: {e}")
        flash('Google login failed. Please try again or use email login.', 'error')
    
    return redirect(url_for('login'))

@app.route('/register/google')
def google_register():
    """Registration page for Google OAuth users - NEW ROUTE"""
    google_user = session.get('google_user')
    if not google_user:
        return redirect(url_for('login'))
    return render_template('google_register.html', google_user=google_user)

@app.route('/register/google/complete', methods=['POST'])
def complete_google_registration():
    """Complete Google OAuth registration - NEW ROUTE"""
    google_user = session.get('google_user')
    if not google_user:
        return redirect(url_for('login'))
    
    admission_no = request.form.get('admission_no')
    college = request.form.get('college')
    
    # Create student account with random password
    if db.create_student(
        name=google_user['name'],
        email=google_user['email'],
        admission_no=admission_no,
        password=generate_password_hash(os.urandom(24).hex()),
        college=college
    ):
        # Link Google account
        student = db.get_student_by_email(google_user['email'])
        db.update_student_google_id(student['id'], google_user['sub'])
        
        session.pop('google_user', None)
        
        # Auto-login and redirect to 2FA setup
        session['user_id'] = student['id']
        session['user_type'] = 'student'
        session['user_email'] = student['email']
        session['user_name'] = student['name']
        
        flash('Registration successful! Please setup 2FA for security.', 'success')
        return redirect(url_for('setup_2fa'))
    
    flash('Registration failed. Please try again.', 'error')
    return redirect(url_for('login'))

@app.route('/setup-2fa')
def setup_2fa():
    """Setup 2FA for user - NEW ROUTE"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Generate TOTP secret
    totp_secret = pyotp.random_base32()
    session['pending_totp_secret'] = totp_secret
    
    # Create TOTP object
    totp = pyotp.TOTP(totp_secret)
    provisioning_uri = totp.provisioning_uri(
        name=session['user_email'],
        issuer_name='HBIU University Portal'
    )
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 for HTML display
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return render_template('setup_2fa.html', 
                         qr_code=img_str, 
                         totp_secret=totp_secret)

@app.route('/verify-2fa-setup', methods=['POST'])
def verify_2fa_setup():
    """Verify 2FA setup - NEW ROUTE"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    totp_code = request.form.get('totp_code')
    totp_secret = session.get('pending_totp_secret')
    
    if not totp_secret:
        flash('Session expired. Please try again.', 'error')
        return redirect(url_for('setup_2fa'))
    
    totp = pyotp.TOTP(totp_secret)
    if totp.verify(totp_code):
        # Save TOTP secret to database
        db.update_totp_secret(session['user_type'], session['user_id'], totp_secret)
        session.pop('pending_totp_secret', None)
        flash('2FA setup successful! Your account is now more secure.', 'success')
        return redirect(url_for('student_dashboard'))
    else:
        flash('Invalid code. Please try again.', 'error')
        return redirect(url_for('setup_2fa'))

@app.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    """Verify 2FA code for login - NEW ROUTE"""
    if request.method == 'GET':
        return render_template('verify_2fa.html')
    
    # POST request - verify code
    totp_code = request.form.get('totp_code')
    pre_2fa_user = session.get('pre_2fa_user')
    
    if not pre_2fa_user:
        flash('Session expired. Please login again.', 'error')
        return redirect(url_for('login'))
    
    # Get TOTP secret from database
    totp_secret = db.get_totp_secret(pre_2fa_user['type'], pre_2fa_user['id'])
    
    if totp_secret:
        totp = pyotp.TOTP(totp_secret)
        if totp.verify(totp_code):
            # 2FA successful, log user in
            session['user_id'] = pre_2fa_user['id']
            session['user_type'] = pre_2fa_user['type']
            session['user_email'] = pre_2fa_user['email']
            session['user_name'] = pre_2fa_user['name']
            session.pop('pre_2fa_user', None)
            flash('Login successful!', 'success')
            return redirect(url_for('student_dashboard'))
    
    flash('Invalid 2FA code. Please try again.', 'error')
    return render_template('verify_2fa.html')

# -------------------
# ALL YOUR EXISTING ROUTES REMAIN UNCHANGED BELOW
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
        college = request.form['college']  # NEW: Get college from form
        
        if db.create_student(name, email, admission_no, password, college):  # UPDATED: Pass college parameter
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

# ==================== FIXED: REMOVED DUPLICATE ROUTE ====================
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

@app.route('/unit/<int:unit_id>/learn')
def learning_interface(unit_id):
    # Unit
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('home'))

    # Chapters (sorted if order_index exists)
    chapters = db.get_unit_chapters(unit_id) or []
    chapters.sort(key=lambda c: c.get('order_index', 0))

    # Progress (students only)
    is_student = ('user_id' in session and session.get('user_type') == 'student')
    progress_data = db.get_student_progress(session['user_id'], unit_id) if is_student else {}
    progress_data = progress_data or {}

    total_items = 0
    completed_items = 0
    completed_chapters = 0  # NEW: Add this variable
    has_exam_item = False

    # Attach items and compute progress (non-exam only)
    for ch in chapters:
        items = db.get_chapter_items(ch['id']) or []
        items.sort(key=lambda i: i.get('order_index', 0))

        # NEW: Track chapter completion
        chapter_completed = True
        
        for it in items:
            it['completed'] = bool(progress_data.get(it['id'], False))
            if it.get('type') == 'exam':
                has_exam_item = True
            else:
                total_items += 1
                if it['completed']:
                    completed_items += 1
                else:
                    chapter_completed = False  # If any item not completed, chapter not completed

        # NEW: Count completed chapters
        if chapter_completed and len(items) > 0:  # Only count if chapter has items and all are completed
            completed_chapters += 1

        ch['items'] = items

    # If you don't persist an exam item, synthesize one
    if not has_exam_item:
        chapters.append({
            'id': -99999,
            'title': 'Final Examination',
            'items': [{
                'id': -100000,
                'chapter_id': -99999,
                'type': 'exam',
                'title': 'Final Exam',
                'completed': bool(progress_data.get(-100000, False))
            }]
        })

    progress_percentage = int((completed_items / total_items) * 100) if total_items else 0

    # Only students can unlock the exam by progress
    exam_unlocked = (is_student and progress_percentage == 100)

    return render_template(
        'learning_interface.html',
        unit=unit,
        chapters=chapters,
        progress_data=progress_data,
        total_items=total_items,
        completed_items=completed_items,
        completed_chapters=completed_chapters,  # NEW: Add this to template context
        progress_percentage=progress_percentage,
        exam_unlocked=exam_unlocked
    )

@app.route('/update_progress', methods=['POST'])
def update_progress():
    if 'user_id' not in session or session['user_type'] != 'student':
        return jsonify({'success': False, 'error': 'Not logged in as student'})
    
    if request.method == 'POST':
        data = request.get_json()
        unit_id = data.get('unit_id')
        item_id = data.get('item_id')
        completed = data.get('completed')
        
        # Update progress in database
        try:
            success = db.update_student_progress(
                session['user_id'], 
                unit_id, 
                item_id, 
                completed
            )
            if success:
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Database update failed'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

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
    """Allow lecturer or admin to upload course resources."""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        flash('Please login as lecturer or admin to continue', 'warning')
        return redirect(url_for('login'))
    
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('lecturer_dashboard'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        file = request.files.get('file')
        
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            if db.add_resource(unit_id, title, filename):
                flash('Resource uploaded successfully!', 'success')
                return redirect(url_for('unit_detail', unit_id=unit_id))
            else:
                flash('Error uploading resource', 'danger')
    
    # ✅ Corrected template name
    return render_template("upload_resource.html", unit=unit)

# ---------- CURRICULUM JSON APIS (ADD-ONLY) ----------

@app.route('/api/unit/<int:unit_id>/curriculum')
def api_get_curriculum(unit_id):
    """Return chapters + items for a unit (JSON)."""
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        return jsonify({'ok': False, 'error': 'Unit not found'}), 404

    chapters = db.get_unit_chapters(unit_id) or []
    for ch in chapters:
        ch['items'] = db.get_chapter_items(ch['id']) or []
    return jsonify({'ok': True, 'chapters': chapters})


@app.route('/api/unit/<int:unit_id>/chapter', methods=['POST'])
def api_create_chapter(unit_id):
    """Create a chapter; title optional (auto Chapter N)."""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    # compute next order index and default title
    chapters = db.get_unit_chapters(unit_id) or []
    next_idx = (max([c.get('order_index', 0) for c in chapters]) + 1) if chapters else 1

    data = request.form if request.form else request.json or {}
    title = (data.get('title') or f'Chapter {next_idx}').strip()
    description = (data.get('description') or '').strip()

    ch_id = db.add_chapter(unit_id=unit_id, title=title, description=description, order_index=next_idx)
    if not ch_id:
        return jsonify({'ok': False, 'error': 'Failed to create chapter'}), 400

    return jsonify({'ok': True, 'chapter_id': ch_id})


@app.route('/api/unit/<int:unit_id>/item', methods=['POST'])
def api_create_item(unit_id):
    """
    Create lesson/quiz/assignment item under a chapter.
    Accepts multipart/form-data for optional files.
    Required: chapter_id, type, title
    Optional: description, duration, video_url, video_file, instructions, attachment (for quiz/assignment)
    """
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    # Work with form (supports files) or JSON
    data = request.form if request.form else request.json or {}
    chapter_id = int(data.get('chapter_id', 0))
    item_type = (data.get('type') or '').strip().lower()
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    duration = (data.get('duration') or '').strip()
    video_url = (data.get('video_url') or '').strip()
    instructions = (data.get('instructions') or '').strip()

    if not chapter_id or item_type not in ['lesson', 'quiz', 'assignment'] or not title:
        return jsonify({'ok': False, 'error': 'Missing or invalid fields'}), 400

    # Find next order_index inside this chapter
    items = db.get_chapter_items(chapter_id) or []
    next_idx = (max([i.get('order_index', 0) for i in items]) + 1) if items else 1

    # Optional files
    video_filename = None
    notes_filename = None
    attachment_filename = None

    if 'video_file' in request.files and request.files['video_file'].filename:
        vf = request.files['video_file']
        video_filename = secure_filename(vf.filename)
        vf.save(os.path.join(app.config['UPLOAD_FOLDER'], video_filename))

    if 'notes_file' in request.files and request.files['notes_file'].filename:
        nf = request.files['notes_file']
        notes_filename = secure_filename(nf.filename)
        nf.save(os.path.join(app.config['UPLOAD_FOLDER'], notes_filename))

    if 'attachment' in request.files and request.files['attachment'].filename:
        af = request.files['attachment']
        attachment_filename = secure_filename(af.filename)
        af.save(os.path.join(app.config['UPLOAD_FOLDER'], attachment_filename))

    # Persist
    item_id = db.add_chapter_item(
        chapter_id=chapter_id,
        title=title,
        type=item_type,
        content=description,             # reuse 'content' column for lesson body/description
        video_url=video_url,
        video_file=video_filename,
        instructions=instructions or (f'Notes: {notes_filename}' if notes_filename else None),
        duration=duration,
        order_index=next_idx,
        attachment_filename=attachment_filename  # your db helper can ignore if not implemented
    )

    if not item_id:
        return jsonify({'ok': False, 'error': 'Failed to create item'}), 400

    return jsonify({'ok': True, 'item_id': item_id})

# ==================== NEW: LESSON, QUIZ, ASSIGNMENT, EXAM ROUTES ====================

@app.route('/unit/<int:unit_id>/add_lesson')
def add_lesson_page(unit_id):
    """Page for adding a new lesson"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        flash('Please login as lecturer or admin', 'warning')
        return redirect(url_for('login'))
    
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('lecturer_dashboard'))
    
    return render_template('add_lesson.html', unit=unit)

@app.route('/unit/<int:unit_id>/add_quiz')
def add_quiz_page(unit_id):
    """Page for adding a new quiz"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        flash('Please login as lecturer or admin', 'warning')
        return redirect(url_for('login'))
    
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('lecturer_dashboard'))
    
    return render_template('add_quiz.html', unit=unit)

@app.route('/unit/<int:unit_id>/add_assignment')
def add_assignment_page(unit_id):
    """Page for adding a new assignment"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        flash('Please login as lecturer or admin', 'warning')
        return redirect(url_for('login'))
    
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('lecturer_dashboard'))
    
    return render_template('add_assignment.html', unit=unit)

@app.route('/unit/<int:unit_id>/add_exam')
def add_exam_page(unit_id):
    """Page for adding final exam"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        flash('Please login as lecturer or admin', 'warning')
        return redirect(url_for('login'))
    
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('lecturer_dashboard'))
    
    # Check if exam already exists
    existing_exam = db.get_exam_by_unit(unit_id)
    if existing_exam:
        flash('Final exam already exists for this unit', 'info')
        return redirect(url_for('upload_resource', unit_id=unit_id))
    
    # Check if there are enough chapters (10 chapters required)
    chapters = db.get_unit_chapters(unit_id) or []
    can_create = len(chapters) >= 10
    
    return render_template('add_exam.html', unit=unit, can_create=can_create, lesson_count=len(chapters))

# ==================== API ROUTES FOR EXAMS ====================

@app.route('/api/unit/<int:unit_id>/exam', methods=['POST'])
def api_create_exam(unit_id):
    """API endpoint to create exam from popup window"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.form if request.form else request.json or {}
        
        title = data.get('title', 'Final Examination')
        instructions = data.get('instructions', '')
        duration = data.get('duration', '60 minutes')
        total_marks = data.get('total_marks', '100')
        questions = data.get('questions', [])
        
        # Create exam in database
        exam_id, exam_item_id = db.create_exam(
            unit_id=unit_id,
            title=title,
            instructions=instructions,
            duration=duration,
            total_marks=total_marks,
            created_by=session['user_id']
        )
        
        if exam_id and questions:
            db.add_exam_questions(exam_id, questions)
        
        return jsonify({
            'ok': True, 
            'exam_id': exam_id,
            'message': 'Exam created successfully'
        })
        
    except Exception as e:
        print(f"Exam creation error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/api/unit/<int:unit_id>/exams')
def api_get_exams(unit_id):
    """API endpoint to get exams for a unit"""
    exams = []
    try:
        exam_data = db.get_exam_by_unit(unit_id)
        if exam_data:
            exams.append(exam_data)
    except Exception as e:
        print(f"Error fetching exams: {e}")
    
    return jsonify({'ok': True, 'exams': exams})

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
@app.route('/unit/<int:unit_id>/chapter/create', methods=['POST'])
def create_chapter(unit_id):
    """Create a new chapter for a unit"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.form
        title = data.get('title', f'Chapter {db.get_next_chapter_number(unit_id)}')
        description = data.get('description', '')
        
        chapter_id = db.add_chapter(unit_id, title, description)
        if chapter_id:
            return jsonify({'ok': True, 'chapter_id': chapter_id})
        return jsonify({'ok': False, 'error': 'Failed to create chapter'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/unit/<int:unit_id>/item/create', methods=['POST'])
def create_chapter_item(unit_id):
    """Create a lesson, quiz, or assignment item"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403
    
    try:
        chapter_id = request.form.get('chapter_id')
        item_type = request.form.get('type')  # lesson, quiz, assignment
        title = request.form.get('title')
        content = request.form.get('content', '')
        
        if not all([chapter_id, item_type, title]):
            return jsonify({'ok': False, 'error': 'Missing required fields'})
        
        item_id = db.add_chapter_item(
            chapter_id=chapter_id,
            title=title,
            type=item_type,
            content=content,
            video_url=request.form.get('video_url'),
            video_file=request.form.get('video_file'),
            instructions=request.form.get('instructions'),
            duration=request.form.get('duration')
        )
        
        if item_id:
            return jsonify({'ok': True, 'item_id': item_id})
        return jsonify({'ok': False, 'error': 'Failed to create item'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ---------- EXAM: CREATE (lecturer/admin) ----------
@app.route('/unit/<int:unit_id>/exam/create', methods=['GET','POST'])
def exam_create(unit_id):
    if 'user_id' not in session or session.get('user_type') not in ['lecturer','admin']:
        flash('Please log in as lecturer or admin', 'danger')
        return redirect(url_for('login'))

    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger'); return redirect(url_for('home'))

    lesson_count = db.count_lessons_in_unit(unit_id)
    can_create = lesson_count >= 10

    if request.method == 'POST':
        if not can_create:
            flash('Add at least 10 lessons before creating the exam.', 'warning')
            return redirect(url_for('exam_create', unit_id=unit_id))

        title = request.form.get('title','Final Examination').strip()
        instructions = request.form.get('instructions','')
        duration = int(request.form.get('duration', '60') or 60)
        total_marks = int(request.form.get('total_marks','100') or 100)

        try:
            # create exam + item
            exam_id, exam_item_id = db.create_exam(unit_id, title, instructions, duration, total_marks, session['user_id'])

            # parse questions JSON
            questions_json = request.form.get('questions_json','').strip()
            questions = json.loads(questions_json) if questions_json else []
            # normalize
            for i,q in enumerate(questions, start=1):
                q['position'] = q.get('position', i)
                if q.get('qtype') == 'tf' and isinstance(q.get('correct'), bool):
                    q['correct'] = 'true' if q['correct'] else 'false'
            if questions:
                db.add_exam_questions(exam_id, questions)

            flash('Final Exam created successfully!', 'success')
            return redirect(url_for('learning_interface', unit_id=unit_id))
        except Exception as e:
            print('EXAM CREATE ERROR:', e)
            flash('Error creating exam. Check your JSON and try again.', 'danger')

    return render_template('add_exam.html', unit=unit, can_create=can_create, lesson_count=lesson_count)

# ---------- EXAM: LANDING (student) ----------
@app.route('/unit/<int:unit_id>/exam')
def exam_landing(unit_id):
    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger'); return redirect(url_for('home'))

    exam = db.get_exam_by_unit(unit_id)
    if not exam:
        flash('Final Exam not available yet.', 'info')
        return redirect(url_for('learning_interface', unit_id=unit_id))

    # unlocked if 100% progress of non-exam items
    chapters = db.get_unit_chapters(unit_id) or []
    for ch in chapters:
        ch['items'] = db.get_chapter_items(ch['id']) or []
    # compute
    progress_map = {}
    if 'user_id' in session and session.get('user_type') == 'student':
        progress_map = db.get_student_progress(session['user_id'], unit_id) or {}
    total = sum(1 for ch in chapters for it in ch['items'] if it.get('type') != 'exam')
    done = sum(1 for ch in chapters for it in ch['items'] if it.get('type') != 'exam' and progress_map.get(it['id']))
    unlocked = (total>0 and done==total)

    return render_template('exam_landing.html', unit=unit, exam=exam, unlocked=unlocked)

# ---------- EXAM: START (student) ----------
@app.route('/unit/<int:unit_id>/exam/start')
def exam_start(unit_id):
    if 'user_id' not in session or session.get('user_type') != 'student':
        flash('Please log in as a student', 'danger')
        return redirect(url_for('login'))

    unit = db.get_unit_by_id(unit_id)
    exam = db.get_exam_by_unit(unit_id)
    if not unit or not exam:
        flash('Exam not available.', 'danger'); return redirect(url_for('learning_interface', unit_id=unit_id))

    # (Optionally) enforce unlock again
    # ...
    questions = db.get_exam_questions(exam['id'])
    return render_template('exam_take.html', unit=unit, exam=exam, questions=questions)

# ---------- EXAM: SUBMIT (student) ----------
@app.route('/unit/<int:unit_id>/exam/submit', methods=['POST'])
def exam_submit(unit_id):
    if 'user_id' not in session or session.get('user_type') != 'student':
        flash('Please log in as a student', 'danger')
        return redirect(url_for('login'))

    unit = db.get_unit_by_id(unit_id)
    exam = db.get_exam_by_unit(unit_id)
    if not unit or not exam:
        flash('Exam not available.', 'danger'); return redirect(url_for('learning_interface', unit_id=unit_id))

    # collect answers
    answers = {}
    for k,v in request.form.items():
        if k.startswith('q_'):
            qid = k.split('_',1)[1]
            answers[qid] = v

    score, total = db.save_exam_attempt_and_score(exam['id'], session['user_id'], answers)

    # mark progress for the exam item as completed
    try:
        db.update_student_progress(session['user_id'], unit_id, exam['item_id'], True)
    except Exception as e:
        print('Progress mark error (exam):', e)

    return render_template('exam_result.html', unit=unit, exam=exam, score=score, total=total)

# ==================== NEW: LESSON, QUIZ, ASSIGNMENT ROUTES ====================

@app.route('/unit/<int:unit_id>/add-lesson', methods=['GET', 'POST'])
def add_lesson(unit_id):
    """Add a new lesson to a unit"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        flash('Please log in as a lecturer or admin to continue', 'danger')
        return redirect(url_for('login'))

    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        video_file = request.files.get('video_file')
        notes_file = request.files.get('notes_file')

        video_filename = None
        notes_filename = None

        # Handle file uploads
        if video_file and video_file.filename:
            video_filename = secure_filename(video_file.filename)
            video_file.save(os.path.join(app.config['UPLOAD_FOLDER'], video_filename))

        if notes_file and notes_file.filename:
            notes_filename = secure_filename(notes_file.filename)
            notes_file.save(os.path.join(app.config['UPLOAD_FOLDER'], notes_filename))

        # Save to database (you can customize the method name as per your DB)
        try:
            db.add_lesson(unit_id, title, content, video_filename, notes_filename, session.get('user_id'))
            flash('Lesson added successfully!', 'success')
        except Exception as e:
            print(f"Error adding lesson: {e}")
            flash('Error adding lesson', 'danger')

        return redirect(url_for('unit_detail', unit_id=unit_id))

    return render_template('add_lesson.html', unit=unit)


@app.route('/unit/<int:unit_id>/add-quiz', methods=['GET', 'POST'])
def add_quiz(unit_id):
    """Add a new quiz to a unit"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        flash('Please log in as a lecturer or admin to continue', 'danger')
        return redirect(url_for('login'))

    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        duration = request.form.get('duration')  # in minutes
        quiz_file = request.files.get('quiz_file')

        quiz_filename = None
        if quiz_file and quiz_file.filename:
            quiz_filename = secure_filename(quiz_file.filename)
            quiz_file.save(os.path.join(app.config['UPLOAD_FOLDER'], quiz_filename))

        try:
            db.add_quiz(unit_id, title, description, duration, quiz_filename, session.get('user_id'))
            flash('Quiz added successfully!', 'success')
        except Exception as e:
            print(f"Error adding quiz: {e}")
            flash('Error adding quiz', 'danger')

        return redirect(url_for('unit_detail', unit_id=unit_id))

    return render_template('add_quiz.html', unit=unit)


@app.route('/unit/<int:unit_id>/add-assignment', methods=['GET', 'POST'])
def add_assignment(unit_id):
    """Add a new assignment to a unit"""
    if 'user_id' not in session or session.get('user_type') not in ['lecturer', 'admin']:
        flash('Please log in as a lecturer or admin to continue', 'danger')
        return redirect(url_for('login'))

    unit = db.get_unit_by_id(unit_id)
    if not unit:
        flash('Unit not found', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form.get('title')
        instructions = request.form.get('instructions')
        due_date = request.form.get('due_date')
        assignment_file = request.files.get('assignment_file')

        assignment_filename = None
        if assignment_file and assignment_file.filename:
            assignment_filename = secure_filename(assignment_file.filename)
            assignment_file.save(os.path.join(app.config['UPLOAD_FOLDER'], assignment_filename))

        try:
            db.add_assignment(unit_id, title, instructions, due_date, assignment_filename, session.get('user_id'))
            flash('Assignment added successfully!', 'success')
        except Exception as e:
            print(f"Error adding assignment: {e}")
            flash('Error adding assignment', 'danger')

        return redirect(url_for('unit_detail', unit_id=unit_id))

    return render_template('add_assignment.html', unit=unit)


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
    """Initiate Google OAuth flow - ENHANCED FEEDBACK"""
    if 'admin_id' not in session and 'lecturer_id' not in session:
        flash('Please log in to connect Google Classroom', 'error')
        return redirect(url_for('login'))
    
    try:
        # Get user info for personalized feedback
        user_type = 'Admin' if 'admin_id' in session else 'Lecturer'
        user_id = session.get('admin_id') or session.get('lecturer_id')
        
        # Enhanced flash message with user context
        flash(
            f'Google Classroom connection initiated for {user_type}! '
            f'OAuth integration coming soon. '
            f'You will be able to sync courses and manage classroom activities.', 
            'info'
        )
        
        # Log the connection attempt for debugging
        print(f"GOOGLE CONNECT: {user_type} {user_id} attempted OAuth connection")
        
    except Exception as e:
        # If anything goes wrong, still provide basic functionality
        print(f"Google connect info error (non-critical): {e}")
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
                # Generate a 6-digit verification code
                import random
                verification_code = str(random.randint(100000, 999999))
                
                # Store verification code in session
                session['admin_verification'] = {
                    'admin_id': admin['id'],
                    'admin_email': admin['email'],
                    'admin_role': admin.get('role', 'admin'),
                    'verification_code': verification_code,
                    'attempts': 0,
                    'created_at': datetime.now().isoformat()
                }
                
                # Send verification email - FIXED VERSION
                try:
                    from flask_mail import Message  # Import here if needed
                    msg = Message(
                        subject='HBIU Admin Portal - Verification Code',
                        recipients=[admin['email']],
                        body=f'''
Hello Admin,

Your verification code for HBIU Admin Portal is: {verification_code}

This code will expire in 10 minutes.

If you did not request this login, please ignore this email.

Best regards,
HBIU Security Team
                        '''
                    )
                    mail.send(msg)
                    
                    flash('Verification code sent to your email. Please check your inbox.', 'success')
                    return redirect(url_for('admin_verify_code'))
                    
                except Exception as e:
                    print(f"Email sending error: {e}")
                    flash('Error sending verification email. Please try again.', 'error')
            else:
                flash('Invalid email or password', 'error')
        except Exception as e:
            print(f"Admin login error: {e}")
            flash('Login error. Please try again.', 'error')
    
    return render_template('admin_login.html')

@app.route('/update-admin-email')
def update_admin_email():
    """Update existing admin email to hbiuportal@gmail.com"""
    try:
        conn = db.get_db()
        cursor = conn.cursor()
        
        # Update the admin email
        cursor.execute(
            "UPDATE admins SET email = %s WHERE email = %s",
            ('hbiuportal@gmail.com', 'admin@hbi.edu')
        )
        conn.commit()
        conn.close()
        
        return """
        ✅ Admin email updated successfully!
        
        Old: admin@hbi.edu
        New: hbiuportal@gmail.com
        Password: #Ausbildung2025 (unchanged)
        
        You can now login at /admin/login with:
        Email: hbiuportal@gmail.com
        Password: #Ausbildung2025
        """
        
    except Exception as e:
        return f"❌ Error updating admin: {str(e)}"

@app.route('/admin/verify-code', methods=['GET', 'POST'])
def admin_verify_code():
    """Verify email code for admin login - NEW ROUTE"""
    verification_data = session.get('admin_verification')
    
    if not verification_data:
        flash('Session expired. Please login again.', 'error')
        return redirect(url_for('admin_login'))
    
    # Check if code is expired (10 minutes)
    created_at = datetime.fromisoformat(verification_data['created_at'])
    if datetime.now() - created_at > timedelta(minutes=10):
        session.pop('admin_verification', None)
        flash('Verification code has expired. Please login again.', 'error')
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        entered_code = request.form.get('verification_code')
        
        if not entered_code:
            flash('Please enter the verification code', 'error')
            return render_template('admin_verify_code.html')
        
        # Check attempts
        if verification_data['attempts'] >= 3:
            session.pop('admin_verification', None)
            flash('Too many failed attempts. Please login again.', 'error')
            return redirect(url_for('admin_login'))
        
        # Verify code
        if entered_code == verification_data['verification_code']:
            # Code verified, log admin in
            session['admin_id'] = verification_data['admin_id']
            session['admin_email'] = verification_data['admin_email']
            session['user_type'] = 'admin'
            session['admin_role'] = verification_data['admin_role']
            
            # Log the login activity
            db.log_admin_activity(
                verification_data['admin_id'], 
                'LOGIN', 
                'Admin logged in with email 2FA', 
                request.remote_addr
            )
            
            session.pop('admin_verification', None)
            flash('Secure login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            # Increment attempts
            verification_data['attempts'] += 1
            session['admin_verification'] = verification_data
            
            remaining_attempts = 3 - verification_data['attempts']
            flash(f'Invalid verification code. {remaining_attempts} attempts remaining.', 'error')
    
    return render_template('admin_verify_code.html', 
                         email=verification_data['admin_email'])

@app.route('/admin/resend-code')
def admin_resend_code():
    """Resend verification code - NEW ROUTE"""
    verification_data = session.get('admin_verification')
    
    if not verification_data:
        flash('Session expired. Please login again.', 'error')
        return redirect(url_for('admin_login'))
    
    # Generate new code
    import random
    new_code = str(random.randint(100000, 999999))
    
    # Update session
    verification_data['verification_code'] = new_code
    verification_data['attempts'] = 0
    verification_data['created_at'] = datetime.now().isoformat()
    session['admin_verification'] = verification_data
    
    # Send new verification email - FIXED VERSION
    try:
        from flask_mail import Message  # Import here if needed
        msg = Message(
            subject='HBIU Admin Portal - New Verification Code',
            recipients=[verification_data['admin_email']],
            body=f'''
Hello Admin,

Your new verification code for HBIU Admin Portal is: {new_code}

This code will expire in 10 minutes.

If you did not request this login, please ignore this email.

Best regards,
HBIU Security Team
            '''
        )
        mail.send(msg)
        flash('New verification code sent to your email.', 'success')
    except Exception as e:
        print(f"Email resend error: {e}")
        flash('Error sending verification email. Please try again.', 'error')
    
    return redirect(url_for('admin_verify_code'))

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
            college = request.form['college']  # NEW: Get college from form
            if db.create_student(name, email, admission_no, password, college):  # UPDATED: Pass college parameter
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
@app.route('/admin/reset_password', methods=['GET', 'POST'])
@admin_required
def admin_reset_password():
    try:
        if request.method == 'POST':
            user_email = request.form.get('email')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            print(f"DEBUG: Reset password attempt for {user_email}")
            
            # Validate input
            if not all([user_email, new_password, confirm_password]):
                flash('Please fill in all fields', 'error')
                return redirect(url_for('admin_reset_password'))
            
            if new_password != confirm_password:
                flash('Passwords do not match.', 'error')
                return redirect(url_for('admin_reset_password'))
            
            if len(new_password) < 6:
                flash('Password must be at least 6 characters.', 'error')
                return redirect(url_for('admin_reset_password'))
            
            # Find user - use existing database functions
            student = None
            lecturer = None
            
            # Get all students and lecturers, then filter by email
            try:
                all_students = db.get_all_students()
                student = next((s for s in all_students if s['email'] == user_email), None)
                print(f"DEBUG: Student lookup result: {student is not None}")
            except Exception as e:
                print(f"DEBUG: Student lookup error: {e}")
            
            try:
                all_lecturers = db.get_all_lecturers()
                lecturer = next((l for l in all_lecturers if l['email'] == user_email), None)
                print(f"DEBUG: Lecturer lookup result: {lecturer is not None}")
            except Exception as e:
                print(f"DEBUG: Lecturer lookup error: {e}")
            
            if not student and not lecturer:
                flash('User not found.', 'error')
                return redirect(url_for('admin_reset_password'))
            
            # Reset password based on user type
            success = False
            user_type = ""
            user_name = ""
            
            if student:
                print(f"DEBUG: Attempting to reset student password for ID: {student['id']}")
                success = db.update_student_password(student['id'], new_password)
                user_type = 'student'
                user_name = student['name']
                print(f"DEBUG: Student password reset result: {success}")
            else:
                print(f"DEBUG: Attempting to reset lecturer password for ID: {lecturer['id']}")
                success = db.update_lecturer_password(lecturer['id'], new_password)
                user_type = 'lecturer'
                user_name = lecturer['name']
                print(f"DEBUG: Lecturer password reset result: {success}")
            
            if success:
                # Log the admin activity
                try:
                    db.log_admin_activity(
                        session['admin_id'], 
                        'reset_password', 
                        f'Reset password for {user_type}: {user_email}'
                    )
                    print("DEBUG: Admin activity logged successfully")
                except Exception as e:
                    print(f"DEBUG: Error logging admin activity: {e}")
                
                flash(f'Password reset successfully for {user_name} ({user_email}).', 'success')
            else:
                flash('Error resetting password. Please try again.', 'error')
            
            return redirect(url_for('admin_reset_password'))
        
        return render_template('admin_reset_password.html')
        
    except Exception as e:
        print(f"CRITICAL ERROR in admin_reset_password: {e}")
        import traceback
        traceback.print_exc()
        flash('Server error occurred. Please check the logs.', 'error')
        return redirect(url_for('admin_reset_password'))

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

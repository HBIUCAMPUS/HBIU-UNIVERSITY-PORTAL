from flask import render_template, session, redirect, url_for, request, flash
import pyotp
import qrcode
import io
import base64
import os
from database import get_student_by_google_id, get_student_by_email, update_student_google_id, create_student, update_totp_secret, get_totp_secret
from werkzeug.security import generate_password_hash

def init_auth_routes(app, google_oauth):
    @app.route('/login/google')
    def google_login():
        """Initiate Google OAuth login"""
        redirect_uri = url_for('google_callback', _external=True)
        return google_oauth.authorize_redirect(redirect_uri)

    @app.route('/login/google/callback')
    def google_callback():
        """Google OAuth callback"""
        try:
            token = google_oauth.authorize_access_token()
            user_info = token.get('userinfo')
            
            if user_info:
                # Check if user exists in database
                student = get_student_by_google_id(user_info['sub'])
                if not student:
                    # Check by email
                    student = get_student_by_email(user_info['email'])
                    if student:
                        # Link Google account to existing student
                        update_student_google_id(student['id'], user_info['sub'])
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
                    return redirect(url_for('student_dashboard'))
        
        except Exception as e:
            print(f"Google OAuth error: {e}")
            flash('Google login failed. Please try again.', 'error')
        
        return redirect(url_for('login'))

    @app.route('/register/google')
    def google_register():
        """Registration page for Google OAuth users"""
        google_user = session.get('google_user')
        if not google_user:
            return redirect(url_for('login'))
        return render_template('google_register.html', google_user=google_user)

    @app.route('/register/google/complete', methods=['POST'])
    def complete_google_registration():
        """Complete Google OAuth registration"""
        google_user = session.get('google_user')
        if not google_user:
            return redirect(url_for('login'))
        
        admission_no = request.form.get('admission_no')
        college = request.form.get('college')
        
        # Create student account with random password
        if create_student(
            name=google_user['name'],
            email=google_user['email'],
            admission_no=admission_no,
            password=generate_password_hash(os.urandom(24).hex()),
            college=college
        ):
            # Link Google account
            student = get_student_by_email(google_user['email'])
            update_student_google_id(student['id'], google_user['sub'])
            
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
        """Setup 2FA for user"""
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
        """Verify 2FA setup"""
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
            update_totp_secret(session['user_type'], session['user_id'], totp_secret)
            session.pop('pending_totp_secret', None)
            flash('2FA setup successful! Your account is now more secure.', 'success')
            return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid code. Please try again.', 'error')
            return redirect(url_for('setup_2fa'))

    @app.route('/verify-2fa', methods=['GET', 'POST'])
    def verify_2fa():
        """Verify 2FA code for login"""
        if request.method == 'GET':
            return render_template('verify_2fa.html')
        
        # POST request - verify code
        totp_code = request.form.get('totp_code')
        pre_2fa_user = session.get('pre_2fa_user')
        
        if not pre_2fa_user:
            flash('Session expired. Please login again.', 'error')
            return redirect(url_for('login'))
        
        # Get TOTP secret from database
        totp_secret = get_totp_secret(pre_2fa_user['type'], pre_2fa_user['id'])
        
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

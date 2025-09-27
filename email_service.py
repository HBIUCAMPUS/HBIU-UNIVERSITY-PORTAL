# email_service.py (Simplified for Render)
import os
import requests

def send_email(to_email, subject, body):
    """Send email using SendGrid (perfect for Render)"""
    
    # Use SendGrid if API key is available
    sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
    if sendgrid_api_key:
        return send_sendgrid_email(to_email, subject, body, sendgrid_api_key)
    else:
        # Fallback to SMTP (for development)
        return send_smtp_email(to_email, subject, body)

def send_sendgrid_email(to_email, subject, body, api_key):
    """Send email via SendGrid API (Render's recommended method)"""
    try:
        url = "https://api.sendgrid.com/v3/mail/send"
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            "personalizations": [{
                "to": [{"email": to_email}],
                "subject": subject
            }],
            "from": {
                "email": os.environ.get('FROM_EMAIL', 'noreply@hbi.edu'),
                "name": "HBI Virtual Campus"
            },
            "content": [{
                "type": "text/html",
                "value": body
            }]
        }
        
        response = requests.post(url, json=data, headers=headers)
        return response.status_code == 202
    except Exception as e:
        print(f"SendGrid error: {e}")
        return False

def send_smtp_email(to_email, subject, body):
    """Fallback SMTP for development"""
    try:
        # Your existing SMTP code (for local testing)
        import smtplib
        from email.mime.text import MimeText
        from email.mime.multipart import MimeMultipart
        
        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', 587))
        smtp_username = os.environ.get('SMTP_USERNAME')
        smtp_password = os.environ.get('SMTP_PASSWORD')
        
        if not all([smtp_username, smtp_password]):
            print("SMTP not configured - email not sent")
            return False
        
        msg = MimeMultipart()
        msg['From'] = smtp_username
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MimeText(body, 'html'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"SMTP error: {e}")
        return False

def send_password_reset_email(email, reset_token):
    """Send password reset email"""
    app_url = os.environ.get('APP_URL', 'https://your-render-app.onrender.com')
    reset_url = f"{app_url}/reset-password/{reset_token}"
    
    subject = "HBI Virtual Campus - Password Reset Request"
    body = f"""
    <h3>Password Reset Request</h3>
    <p>You requested a password reset for your HBI Virtual Campus account.</p>
    <p>Click the link below to reset your password:</p>
    <a href="{reset_url}" style="background: #0f1b2d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Reset Password</a>
    <p><small>This link will expire in 1 hour.</small></p>
    <p>If you didn't request this, please ignore this email.</p>
    """
    
    return send_email(email, subject, body)

def send_welcome_email(email, name, user_type):
    """Send welcome email to new users"""
    subject = "Welcome to HBI Virtual Campus!"
    body = f"""
    <h3>Welcome to HBI Virtual Campus, {name}!</h3>
    <p>Your {user_type} account has been successfully created.</p>
    <p>You can now login to access the virtual campus portal.</p>
    <p><strong>Login URL:</strong> {os.environ.get('APP_URL', 'https://your-render-app.onrender.com')}/login</p>
    <p>Thank you for joining HBI University!</p>
    """
    
    return send_email(email, subject, body)
import os
import pickle
import json
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import session, url_for, current_app
import database as db

# Google Classroom API scopes
SCOPES = [
    'https://www.googleapis.com/auth/classroom.courses',
    'https://www.googleapis.com/auth/classroom.rosters',
    'https://www.googleapis.com/auth/classroom.coursework.students',
    'https://www.googleapis.com/auth/classroom.coursework.me',
    'https://www.googleapis.com/auth/classroom.profile.emails',
    'https://www.googleapis.com/auth/classroom.topics',
    'https://www.googleapis.com/auth/classroom.announcements'
]

class GoogleClassroomService:
    def __init__(self):
        self.creds = None
        self.service = None
        
    def get_credentials(self, user_id=None):
        """Get or create Google API credentials for a user"""
        token_file = f'tokens/token_{user_id}.pickle' if user_id else 'token.pickle'
        os.makedirs('tokens', exist_ok=True)
        
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                self.creds = pickle.load(token)
        
        # If credentials are invalid or expired, refresh them
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                return self.get_authorization_url(user_id)
        
        # Save credentials for next run
        with open(token_file, 'wb') as token:
            pickle.dump(self.creds, token)
        
        self.service = build('classroom', 'v1', credentials=self.creds)
        return None
    
    def get_authorization_url(self, user_id=None):
        """Get authorization URL for OAuth flow"""
        flow = Flow.from_client_secrets_file(
            'credentials.json', 
            SCOPES,
            redirect_uri=url_for('google_auth_callback', _external=True)
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        session['google_auth_state'] = state
        session['google_auth_user'] = user_id
        return authorization_url
    
    def save_credentials_from_flow(self, authorization_response, user_id=None):
        """Save credentials from authorization flow"""
        flow = Flow.from_client_secrets_file(
            'credentials.json',
            SCOPES,
            state=session.get('google_auth_state'),
            redirect_uri=url_for('google_auth_callback', _external=True)
        )
        
        flow.fetch_token(authorization_response=authorization_response)
        self.creds = flow.credentials
        
        token_file = f'tokens/token_{user_id}.pickle' if user_id else 'token.pickle'
        with open(token_file, 'wb') as token:
            pickle.dump(self.creds, token)
        
        self.service = build('classroom', 'v1', credentials=self.creds)
        return True

# Global service instance
classroom_service = GoogleClassroomService()

def get_user_courses(user_id=None):
    """Get all courses for the authenticated user"""
    auth_url = classroom_service.get_credentials(user_id)
    if auth_url:
        return [], auth_url
    
    try:
        courses = []
        page_token = None
        
        while True:
            results = classroom_service.service.courses().list(
                pageToken=page_token,
                pageSize=100
            ).execute()
            
            courses.extend(results.get('courses', []))
            page_token = results.get('nextPageToken')
            if not page_token:
                break
                
        return courses, None
    except HttpError as error:
        print(f"An error occurred: {error}")
        return [], str(error)

def create_course(course_title, course_description, section=None, owner_id='me'):
    """Create a new Google Classroom course"""
    auth_url = classroom_service.get_credentials()
    if auth_url:
        return None, auth_url
    
    try:
        course = {
            'name': course_title,
            'description': course_description,
            'section': section or '',
            'ownerId': owner_id,
            'courseState': 'PROVISIONED'
        }
        
        course = classroom_service.service.courses().create(body=course).execute()
        return course, None
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None, str(error)

def get_course_students(course_id):
    """Get all students in a course"""
    auth_url = classroom_service.get_credentials()
    if auth_url:
        return [], auth_url
    
    try:
        students = []
        page_token = None
        
        while True:
            results = classroom_service.service.courses().students().list(
                courseId=course_id,
                pageToken=page_token,
                pageSize=100
            ).execute()
            
            students.extend(results.get('students', []))
            page_token = results.get('nextPageToken')
            if not page_token:
                break
                
        return students, None
    except HttpError as error:
        print(f"An error occurred: {error}")
        return [], str(error)

def invite_student_to_course(course_id, student_email):
    """Invite a student to a course"""
    auth_url = classroom_service.get_credentials()
    if auth_url:
        return False, auth_url
    
    try:
        student = {'userId': student_email}
        classroom_service.service.courses().students().create(
            courseId=course_id,
            enrollmentCode=None,
            body=student
        ).execute()
        return True, None
    except HttpError as error:
        print(f"An error occurred: {error}")
        return False, str(error)
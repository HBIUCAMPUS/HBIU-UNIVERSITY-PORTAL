import os
import requests
import json
from datetime import datetime
from flask import current_app

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
    
    def create_form(self, form_data):
        """Create a new form in JotForm"""
        try:
            url = f"{self.base_url}/form"
            response = requests.post(url, headers=self.headers, json=form_data)
            response.raise_for_status()
            
            return response.json().get('content', {})
        except Exception as e:
            print(f"Error creating form: {e}")
            return {}
    
    def create_course_registration_form(self, course_name, course_code, instructor_email):
        """Create a customized course registration form"""
        form_template = {
            "questions": [
                {
                    "type": "control_head",
                    "text": f"Course Registration: {course_name}",
                    "order": "1",
                    "name": "header"
                },
                {
                    "type": "control_textbox",
                    "text": "Student ID",
                    "order": "2",
                    "name": "studentId",
                    "required": "Yes",
                    "validation": "None"
                },
                {
                    "type": "control_textbox",
                    "text": "Full Name",
                    "order": "3",
                    "name": "fullName",
                    "required": "Yes"
                },
                {
                    "type": "control_email",
                    "text": "Email Address",
                    "order": "4",
                    "name": "email",
                    "required": "Yes"
                },
                {
                    "type": "control_dropdown",
                    "text": "Year of Study",
                    "order": "5",
                    "name": "yearOfStudy",
                    "options": "First Year|Second Year|Third Year|Fourth Year|Postgraduate",
                    "required": "Yes"
                },
                {
                    "type": "control_textarea",
                    "text": "Why do you want to take this course?",
                    "order": "6",
                    "name": "motivation",
                    "required": "No"
                }
            ],
            "properties": {
                "title": f"Registration: {course_code} - {course_name}",
                "height": "600",
                "thankYouPage": "https://your-university.edu/thank-you"
            }
        }
        
        return self.create_form(form_template)
    
    def create_assignment_submission_form(self, assignment_title, due_date, max_points=100):
        """Create an assignment submission form"""
        form_template = {
            "questions": [
                {
                    "type": "control_head",
                    "text": f"Assignment Submission: {assignment_title}",
                    "order": "1",
                    "name": "header"
                },
                {
                    "type": "control_textbox",
                    "text": "Student ID",
                    "order": "2",
                    "name": "studentId",
                    "required": "Yes"
                },
                {
                    "type": "control_textbox",
                    "text": "Full Name",
                    "order": "3",
                    "name": "fullName",
                    "required": "Yes"
                },
                {
                    "type": "control_fileupload",
                    "text": "Upload Assignment File",
                    "order": "4",
                    "name": "assignmentFile",
                    "required": "Yes",
                    "allowedTypes": "pdf,doc,docx,ppt,pptx,txt"
                },
                {
                    "type": "control_textarea",
                    "text": "Additional Comments",
                    "order": "5",
                    "name": "comments",
                    "required": "No"
                }
            ],
            "properties": {
                "title": f"Assignment: {assignment_title}",
                "height": "700",
                "expirationDate": due_date.strftime('%Y-%m-%d %H:%M:%S') if due_date else None
            }
        }
        
        return self.create_form(form_template)
    
    def sync_submission_to_database(self, form_id, submission_id):
        """Sync a JotForm submission to your database"""
        try:
            # Get submission details
            url = f"{self.base_url}/submission/{submission_id}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            submission_data = response.json().get('content', {})
            
            # Process submission based on form type
            self._process_submission(form_id, submission_data)
            
            return True
        except Exception as e:
            print(f"Error syncing submission {submission_id}: {e}")
            return False
    
    def _process_submission(self, form_id, submission_data):
        """Process submission data and store in database"""
        answers = submission_data.get('answers', {})
        
        # Extract common fields
        student_id = self._get_answer_value(answers, 'studentId')
        full_name = self._get_answer_value(answers, 'fullName')
        email = self._get_answer_value(answers, 'email')
        
        # Determine form type and process accordingly
        form_title = submission_data.get('form_title', '').lower()
        
        if 'registration' in form_title:
            self._process_course_registration(form_id, submission_data, 
                                            student_id, full_name, email)
        elif 'assignment' in form_title:
            self._process_assignment_submission(form_id, submission_data,
                                              student_id, full_name, email)
        elif 'feedback' in form_title:
            self._process_feedback_submission(form_id, submission_data,
                                            student_id, full_name, email)
    
    def _get_answer_value(self, answers, field_name):
        """Extract value from JotForm answers object"""
        for key, answer in answers.items():
            if answer.get('name') == field_name:
                return answer.get('answer', '')
        return ''
    
    def _process_course_registration(self, form_id, submission_data, student_id, full_name, email):
        """Process course registration submission"""
        from database import create_student_unit, get_student_by_email, create_student
        
        try:
            # Check if student exists, create if not
            student = get_student_by_email(email)
            if not student:
                # Extract course code from form title
                form_title = submission_data.get('form_title', '')
                course_code = self._extract_course_code(form_title)
                
                # You might want to create the student first
                # create_student(full_name, email, student_id, "temporary_password")
                
                print(f"Course registration: {full_name} ({student_id}) for course {course_code}")
            
            # Log the registration
            self._log_submission('course_registration', form_id, submission_data)
            
        except Exception as e:
            print(f"Error processing course registration: {e}")
    
    def _process_assignment_submission(self, form_id, submission_data, student_id, full_name, email):
        """Process assignment submission"""
        try:
            answers = submission_data.get('answers', {})
            assignment_file = self._get_answer_value(answers, 'assignmentFile')
            comments = self._get_answer_value(answers, 'comments')
            
            print(f"Assignment submission: {full_name} uploaded {assignment_file}")
            
            # Log the submission
            self._log_submission('assignment_submission', form_id, submission_data)
            
        except Exception as e:
            print(f"Error processing assignment submission: {e}")
    
    def _process_feedback_submission(self, form_id, submission_data, student_id, full_name, email):
        """Process feedback submission"""
        try:
            answers = submission_data.get('answers', {})
            feedback_text = self._get_answer_value(answers, 'feedback')
            rating = self._get_answer_value(answers, 'rating')
            
            print(f"Feedback from {full_name}: {rating} stars")
            
            # Log the feedback
            self._log_submission('feedback', form_id, submission_data)
            
        except Exception as e:
            print(f"Error processing feedback: {e}")
    
    def _extract_course_code(self, form_title):
        """Extract course code from form title"""
        import re
        match = re.search(r'([A-Z]{3,4}\d{3,4})', form_title)
        return match.group(1) if match else "UNKNOWN"
    
    def _log_submission(self, submission_type, form_id, submission_data):
        """Log submission to database"""
        from database import log_jotform_submission
        log_jotform_submission(
            submission_type=submission_type,
            form_id=form_id,
            submission_id=submission_data.get('id'),
            submission_data=json.dumps(submission_data)
        )

# Global JotForm service instance
jotform_service = JotFormService()
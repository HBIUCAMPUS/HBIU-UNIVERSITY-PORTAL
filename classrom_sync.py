import os
from datetime import datetime
from google_classroom import classroom_service, create_course, get_course_students, invite_student_to_course
from database import link_google_course, get_google_course_by_unit, get_unit_students, log_sync_activity
from googleapiclient.errors import HttpError

class ClassroomSyncManager:
    def __init__(self):
        self.service = classroom_service
    
    def sync_unit_to_classroom(self, unit_id, unit_title, unit_code, lecturer_email=None):
        """Sync a university unit to Google Classroom"""
        try:
            # Check if already synced
            existing_course = get_google_course_by_unit(unit_id)
            if existing_course:
                return existing_course['google_course_id'], "Course already synced"
            
            # Create Google Classroom course
            course_title = f"{unit_code} - {unit_title}"
            course_description = f"University Course Unit: {unit_title}"
            
            course, error = create_course(course_title, course_description, f"Unit {unit_code}")
            if error:
                log_sync_activity('course_creation', unit_id, 'failed', error)
                return None, error
            
            # Link course in database
            link_google_course(unit_id, course['id'], course['name'])
            log_sync_activity('course_creation', unit_id, 'success', f"Created course: {course['name']}")
            
            # Sync students if available
            if lecturer_email:
                self.sync_course_students(course['id'], unit_id, lecturer_email)
            
            return course['id'], "Course synced successfully"
            
        except Exception as e:
            log_sync_activity('course_creation', unit_id, 'failed', str(e))
            return None, str(e)
    
    def sync_course_students(self, google_course_id, unit_id, lecturer_email):
        """Sync students from university portal to Google Classroom"""
        try:
            # Get students enrolled in the unit
            students = get_unit_students(unit_id)
            
            # Invite lecturer as teacher (optional)
            # self.invite_teacher_to_course(google_course_id, lecturer_email)
            
            # Invite students
            for student in students:
                student_email = student['email']
                success, error = invite_student_to_course(google_course_id, student_email)
                
                if success:
                    log_sync_activity('student_sync', unit_id, 'success', 
                                    f"Invited student: {student_email}")
                else:
                    log_sync_activity('student_sync', unit_id, 'failed', 
                                    f"Failed to invite {student_email}: {error}")
            
            return True, "Student sync completed"
            
        except Exception as e:
            log_sync_activity('student_sync', unit_id, 'failed', str(e))
            return False, str(e)
    
    def create_classroom_assignment(self, google_course_id, assignment_title, 
                                  assignment_description, due_date=None, max_points=100):
        """Create an assignment in Google Classroom"""
        auth_url = self.service.get_credentials()
        if auth_url:
            return None, auth_url
        
        try:
            coursework = {
                'title': assignment_title,
                'description': assignment_description,
                'workType': 'ASSIGNMENT',
                'state': 'PUBLISHED',
                'maxPoints': max_points
            }
            
            if due_date:
                coursework['dueDate'] = {
                    'year': due_date.year,
                    'month': due_date.month,
                    'day': due_date.day
                }
                coursework['dueTime'] = {
                    'hours': 23,
                    'minutes': 59
                }
            
            assignment = self.service.service.courses().courseWork().create(
                courseId=google_course_id,
                body=coursework
            ).execute()
            
            return assignment, None
            
        except HttpError as error:
            return None, str(error)
    
    def sync_activity_to_assignment(self, unit_id, activity_title, activity_description, due_date):
        """Sync a university activity to Google Classroom assignment"""
        try:
            # Get Google Classroom course ID
            google_course = get_google_course_by_unit(unit_id)
            if not google_course:
                return None, "Course not synced to Google Classroom"
            
            # Create assignment
            assignment, error = self.create_classroom_assignment(
                google_course['google_course_id'],
                activity_title,
                activity_description,
                due_date
            )
            
            if error:
                log_sync_activity('assignment_sync', unit_id, 'failed', error)
                return None, error
            
            log_sync_activity('assignment_sync', unit_id, 'success', 
                            f"Created assignment: {activity_title}")
            return assignment, None
            
        except Exception as e:
            log_sync_activity('assignment_sync', unit_id, 'failed', str(e))
            return None, str(e)
    
    def get_course_assignments(self, google_course_id):
        """Get all assignments for a course"""
        auth_url = self.service.get_credentials()
        if auth_url:
            return [], auth_url
        
        try:
            assignments = []
            page_token = None
            
            while True:
                results = self.service.service.courses().courseWork().list(
                    courseId=google_course_id,
                    pageToken=page_token,
                    pageSize=100
                ).execute()
                
                assignments.extend(results.get('courseWork', []))
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            return assignments, None
            
        except HttpError as error:
            return [], str(error)

# Global sync manager instance
sync_manager = ClassroomSyncManager()
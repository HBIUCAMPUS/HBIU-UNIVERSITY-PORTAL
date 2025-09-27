from flask import request, jsonify
from jotform_integration import jotform_service
import database as db
import json

def handle_jotform_webhook():
    """Handle JotForm webhook notifications"""
    try:
        # Get webhook data
        webhook_data = request.get_json()
        
        if not webhook_data:
            return jsonify({'error': 'No data received'}), 400
        
        # Log webhook
        db.log_jotform_webhook('submission', json.dumps(webhook_data))
        
        # Process based on event type
        event_type = webhook_data.get('eventType')
        
        if event_type == 'formSubmission':
            return _handle_submission_webhook(webhook_data)
        elif event_type == 'formUpdate':
            return _handle_form_update_webhook(webhook_data)
        else:
            return jsonify({'status': 'ignored', 'event_type': event_type})
            
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500

def _handle_submission_webhook(webhook_data):
    """Handle form submission webhook"""
    try:
        form_id = webhook_data.get('formID')
        submission_id = webhook_data.get('submissionID')
        
        if not form_id or not submission_id:
            return jsonify({'error': 'Missing formID or submissionID'}), 400
        
        # Sync submission to database
        success = jotform_service.sync_submission_to_database(form_id, submission_id)
        
        if success:
            return jsonify({'status': 'processed', 'form_id': form_id, 'submission_id': submission_id})
        else:
            return jsonify({'status': 'failed', 'form_id': form_id, 'submission_id': submission_id}), 500
            
    except Exception as e:
        print(f"Submission webhook error: {e}")
        return jsonify({'error': str(e)}), 500

def _handle_form_update_webhook(webhook_data):
    """Handle form update webhook"""
    try:
        form_id = webhook_data.get('formID')
        # Update form details in database if needed
        return jsonify({'status': 'processed', 'form_id': form_id})
    except Exception as e:
        print(f"Form update webhook error: {e}")
        return jsonify({'error': str(e)}), 500

# Add this function to database.py
def log_jotform_webhook(webhook_type, payload):
    """Log JotForm webhook to database"""
    conn = db.get_db()
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
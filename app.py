"""
Flask Application - AI Quotation Builder (Integrated)
Main application file with routes for:
  - Auth (login / register / logout)  [Supabase]
  - Upload → Quotation generation      [existing, unchanged]
  - Chatbot → Quotation generation     [new]
  - Admin dashboard                    [new]
"""

from flask import (
    Flask, render_template, request, jsonify,
    send_file, session, redirect, url_for
)
import os
import sys
from functools import wraps
from werkzeug.utils import secure_filename
from datetime import datetime

from config import Config
from modules.document_parser import DocumentParser, allowed_file
from modules.llm_handler import LLMHandler
from modules.document_generator import DocumentGenerator
from auth_service import (
    login_user, register_user, is_admin,
    list_histories, save_history, load_history_file,
    delete_history_file, make_title,
    list_all_users, admin_delete_session
)
from chatbot_service import (
    get_greeting, send_message, expand_to_requirements,
    AVAILABLE_MODELS, DEFAULT_MODEL
)
from voice_service import synthesize_tts, call_stt
import base64

app = Flask(__name__)
app.config.from_object(Config)
Config.init_app(app)

# Initialize modules
doc_parser = DocumentParser()
doc_generator = DocumentGenerator(output_folder=app.config['OUTPUT_FOLDER'])


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(f):
    """Redirect to login if user not in session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Redirect to home if user is not admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        if not is_admin(session['user']):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════════════════════════════
# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if 'user' in session:
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        company = request.form.get('company', '').strip()
        password = request.form.get('password', '').strip()
        if not company or not password:
            error = 'Please fill in both fields.'
        else:
            ok, msg, user = login_user(company, password)
            if ok:
                session['user'] = user
                if is_admin(user):
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('index'))
            else:
                error = msg
    return render_template('auth.html', tab='login', error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register page."""
    if 'user' in session:
        return redirect(url_for('index'))
    error = None
    success = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        company = request.form.get('company', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm', '').strip()
        if not all([name, company, email, phone, password]):
            error = 'All fields are required.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif password != confirm:
            error = "Passwords don't match."
        else:
            ok, result = register_user(name, company, phone, email, password)
            if ok:
                success = f'Account created! Sign in with company name: {company}'
            else:
                error = result
    return render_template('auth.html', tab='register', error=error, success=success)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ══════════════════════════════════════════════════════════════════════════════
# ─── MAIN / UPLOAD ROUTES  (existing logic — unchanged) ──────────────────────
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
@login_required
def index():
    """Render main page"""
    return render_template('index.html', user=session.get('user'))


@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """Handle file upload and parsing"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'})
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        if not allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS']):
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload Word, PDF, Excel, or image files.'})
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        parsed_data = doc_parser.parse_document(filepath)
        if not parsed_data.get('success'):
            return jsonify({'success': False, 'error': f"Failed to parse document: {parsed_data.get('error')}"})
        requirements = doc_parser.extract_requirements(parsed_data)
        response = {
            'success': True, 'filename': filename, 'filepath': filepath,
            'requirements': requirements, 'file_type': parsed_data.get('file_type')
        }
        if parsed_data.get('structured_data'):
            response['structured_data'] = parsed_data.get('structured_data')
        if parsed_data.get('method') == 'ocr':
            response['ocr_used'] = True
            response['ocr_confidence'] = parsed_data.get('ocr_confidence', 0)
        if parsed_data.get('sections'):
            response['sections'] = parsed_data.get('sections')
        return jsonify(response)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/generate', methods=['POST'])
@login_required
def generate_quotation():
    """Generate quotation using LLM"""
    try:
        data = request.get_json()
        print("=" * 50)
        print("GENERATE QUOTATION REQUEST")
        print("=" * 50)
        requirements = data.get('requirements')
        template_type = data.get('template_type', 'type1')
        api_key = data.get('api_key')
        print(f"Requirements length: {len(requirements) if requirements else 0}")
        print(f"Template type: {template_type}")
        print(f"API key provided: {bool(api_key)}")
        if not requirements:
            return jsonify({'success': False, 'error': 'No requirements provided'})
        if not api_key:
            return jsonify({'success': False, 'error': 'API key is required'})
        llm_handler = LLMHandler(api_key=api_key)
        quotation_data = llm_handler.generate_quotation(
            requirements=requirements,
            template_type=template_type
        )
        print(f"LLM Response success: {quotation_data.get('success')}")
        if not quotation_data.get('success'):
            error_msg = quotation_data.get('error', 'Unknown error')
            return jsonify({'success': False, 'error': f"Failed to generate quotation: {error_msg}"})
        return jsonify({'success': True, 'quotation_data': quotation_data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/download/pdf', methods=['POST'])
@login_required
def download_pdf():
    """Generate and download PDF"""
    try:
        data = request.get_json()
        quotation_data = data.get('quotation_data')
        template_type = data.get('template_type', 'type1')
        if not quotation_data:
            return jsonify({'success': False, 'error': 'No quotation data provided'})
        pdf_path = doc_generator.generate_pdf(quotation_data, template_type)
        return jsonify({'success': True, 'filename': os.path.basename(pdf_path), 'filepath': pdf_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/download/word', methods=['POST'])
@login_required
def download_word():
    """Generate and download Word document"""
    try:
        data = request.get_json()
        quotation_data = data.get('quotation_data')
        template_type = data.get('template_type', 'type1')
        if not quotation_data:
            return jsonify({'success': False, 'error': 'No quotation data provided'})
        word_path = doc_generator.generate_word(quotation_data, template_type)
        return jsonify({'success': True, 'filename': os.path.basename(word_path), 'filepath': word_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/download/file/<path:filename>')
@login_required
def download_file(filename):
    """Serve generated file for download"""
    try:
        filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ─── CHAT ROUTES ──────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/chat')
@login_required
def chat():
    """Render chatbot UI."""
    user = session['user']
    histories = list_histories(user['key'])
    return render_template(
        'chat.html',
        user=user,
        models=AVAILABLE_MODELS,
        default_model=DEFAULT_MODEL,
        histories=histories,
    )


@app.route('/chat/message', methods=['POST'])
@login_required
def chat_message():
    """
    Process one chat turn.
    Body: { api_key, model, history: [{role,content},...], message, session_id }
    Returns: { reply, history, summary_ready, session_id }
    """
    try:
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        model = data.get('model', DEFAULT_MODEL)
        history = data.get('history', [])
        user_msg = data.get('message', '').strip()
        sid = data.get('session_id') or datetime.now().strftime('%Y%m%d_%H%M%S')

        if not user_msg:
            return jsonify({'success': False, 'error': 'Empty message'})

        result = send_message(api_key, model, history, user_msg)
        updated_history = result['history']

        # Auto-save to Supabase
        user = session['user']
        title = make_title(updated_history)
        save_history(user['key'], sid, updated_history, title)

        return jsonify({
            'success': True,
            'reply': result['reply'],
            'history': updated_history,
            'summary_ready': result['summary_ready'],
            'session_id': sid,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/chat/greet', methods=['POST'])
@login_required
def chat_greet():
    """Get the initial AI greeting."""
    try:
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        model = data.get('model', DEFAULT_MODEL)
        greeting = get_greeting(api_key, model)
        return jsonify({'success': True, 'greeting': greeting})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/chat/generate', methods=['POST'])
@login_required
def chat_generate():
    """
    2-step chat→quotation handoff:
      Step 1: Expand chat summary into a detailed requirements document (Groq)
      Step 2: Pass to LLMHandler.generate_quotation() (same as upload path)
    Body: { api_key, model, history, template_type }
    """
    try:
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        model = data.get('model', DEFAULT_MODEL)
        history = data.get('history', [])
        template_type = data.get('template_type', 'type1')

        if not api_key:
            return jsonify({'success': False, 'error': 'API key is required'})
        if not history:
            return jsonify({'success': False, 'error': 'No conversation history provided'})

        # Step 1 — Expand Q&A into a detailed requirements document
        print("=" * 50)
        print("CHAT → QUOTATION: Step 1 — Expanding requirements")
        requirements_text = expand_to_requirements(api_key, model, history)
        print(f"Expanded requirements length: {len(requirements_text)}")

        # Step 2 — Generate quotation (same engine as upload path)
        print("CHAT → QUOTATION: Step 2 — Generating quotation")
        llm_handler = LLMHandler(api_key=api_key)
        quotation_data = llm_handler.generate_quotation(
            requirements=requirements_text,
            template_type=template_type,
        )
        print(f"Quotation generation success: {quotation_data.get('success')}")
        print("=" * 50)

        if not quotation_data.get('success'):
            return jsonify({'success': False, 'error': quotation_data.get('error', 'Generation failed')})

        return jsonify({'success': True, 'quotation_data': quotation_data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/chat/history/<session_id>', methods=['GET'])
@login_required
def chat_history(session_id):
    """Load a previous chat session."""
    try:
        user = session['user']
        data = load_history_file(user['key'], f"{session_id}.json")
        return jsonify({'success': True, 'messages': data['messages'], 'title': data['title']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/chat/history/<session_id>/delete', methods=['POST'])
@login_required
def chat_delete_history(session_id):
    """Delete a chat session."""
    try:
        user = session['user']
        delete_history_file(user['key'], f"{session_id}.json")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/chat/stt', methods=['POST'])
@login_required
def chat_stt():
    """
    Speech-to-Text endpoint for the automated voice loop.
    Receives base64-encoded WebM audio, calls Groq Whisper, returns text.
    """
    try:
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        audio_b64 = data.get('audio_b64', '')
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key required for speech recognition'})
        if not audio_b64:
            return jsonify({'success': False, 'error': 'No audio data received'})
            
        audio_bytes = base64.b64decode(audio_b64)
        transcript = call_stt(api_key, audio_bytes)
        
        if transcript.startswith("[Transcription error"):
            return jsonify({'success': False, 'error': transcript})
            
        return jsonify({'success': True, 'text': transcript})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/chat/tts', methods=['POST'])
@login_required
def chat_tts():
    """
    Text-to-Speech endpoint for the automated voice loop.
    Receives text, calls Edge-TTS, returns base64-encoded MP3 audio.
    """
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'})
            
        audio_bytes = synthesize_tts(text)
        if not audio_bytes:
            return jsonify({'success': False, 'error': 'Failed to synthesize speech'})
            
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        return jsonify({'success': True, 'audio_b64': audio_b64})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# ─── ADMIN ROUTES ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard page."""
    return render_template('admin.html', user=session['user'])


@app.route('/admin/users', methods=['GET'])
@admin_required
def admin_users():
    """Return all users as JSON."""
    try:
        users = list_all_users()
        non_admin = [u for u in users if u.get('role') != 'admin']
        # Enrich each user with chat count
        for u in non_admin:
            histories = list_histories(u['key'])
            u['chat_count'] = len(histories)
        return jsonify({'success': True, 'users': non_admin})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/user/<user_key>/chats', methods=['GET'])
@admin_required
def admin_user_chats(user_key):
    """Return chat sessions for a user."""
    try:
        histories = list_histories(user_key)
        sessions = [
            {
                'session_id': fname.replace('.json', ''),
                'title': meta.get('title', 'Untitled'),
                'saved_at': meta.get('saved_at', 0),
                'message_count': len(meta.get('messages', [])),
            }
            for fname, meta in histories
        ]
        return jsonify({'success': True, 'sessions': sessions})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/user/<user_key>/chat/<session_id>', methods=['GET'])
@admin_required
def admin_load_chat(user_key, session_id):
    """Load a specific chat session for admin view."""
    try:
        data = load_history_file(user_key, f"{session_id}.json")
        return jsonify({'success': True, 'messages': data['messages'], 'title': data['title']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/user/<user_key>/chat/<session_id>/delete', methods=['POST'])
@admin_required
def admin_delete_chat(user_key, session_id):
    """Delete a chat session as admin."""
    try:
        admin_delete_session(user_key, session_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

import os
import re
import uuid
import sqlite3
import hashlib
import urllib.parse
import json
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from media_engine import (
    generate_audio,
    generate_video_with_audio,
    check_video_clarification,
    check_video_safety,
    apply_video_refinement,
)

# Optional imports - gracefully handle missing packages
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import urllib.request
    import urllib.error
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

# Load environment variables
load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'lobo-x-robo-secret-key-2026')

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'taskbot.db')
GENERATED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'generated')
os.makedirs(GENERATED_DIR, exist_ok=True)

# ----------------- Database Setup -----------------

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA busy_timeout=30000;')
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Conversations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')

    # Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            image_url TEXT,
            audio_url TEXT,
            video_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    ''')

    # Migrate older DBs to include audio_url and video_url columns
    cursor.execute('PRAGMA table_info(messages)')
    existing_cols = {row[1] for row in cursor.fetchall()}
    if 'audio_url' not in existing_cols:
        cursor.execute('ALTER TABLE messages ADD COLUMN audio_url TEXT')
    if 'video_url' not in existing_cols:
        cursor.execute('ALTER TABLE messages ADD COLUMN video_url TEXT')

    # Ensure a default demo user exists for quick login
    cursor.execute('SELECT id FROM users WHERE username = ?', ('demo',))
    if not cursor.fetchone():
        demo_pass_hash = hashlib.sha256('demo123'.encode()).hexdigest()
        cursor.execute(
            'INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)',
            ('demo', demo_pass_hash, 'Demo User')
        )

    conn.commit()
    conn.close()

init_db()

# ----------------- Auth Helpers -----------------

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized. Please log in.'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def is_placeholder(key):
    if not key:
        return True
    key_lower = key.lower().strip()
    placeholders = ['paste-', 'your-', 'xxxx', 'key-here', 'your_api_key', 'api_key']
    return any(p in key_lower for p in placeholders) or len(key.strip()) < 15

# ----------------- AI Engine Callers -----------------

def call_gemini_chat(prompt, history=None):
    """Call Google Gemini API for intelligent AI responses."""
    load_dotenv(override=True)
    api_key = (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or '').strip()
    if not api_key or is_placeholder(api_key):
        return None

    # Build strictly alternating conversation contents starting with 'user'
    contents = []
    if history:
        for h in history:
            text = (h.get('content') or '').strip()
            if not text:
                continue
            role = 'user' if h.get('role') == 'user' else 'model'
            if not contents and role != 'user':
                continue
            if contents and contents[-1]['role'] == role:
                contents[-1]['parts'][0]['text'] += '\n\n' + text
            else:
                contents.append({'role': role, 'parts': [{'text': text}]})

    if contents and contents[-1]['role'] == 'user':
        contents[-1]['parts'][0]['text'] += '\n\n' + prompt
    else:
        contents.append({'role': 'user', 'parts': [{'text': prompt}]})

    payload = json.dumps({
        'contents': contents,
        'systemInstruction': {
            'parts': [{
                'text': (
                    'You are LOBO X ROBO, a helpful AI assistant. Provide detailed, '
                    'well-structured answers with markdown formatting. For code questions, '
                    'always provide complete, working code with explanations. Never say you '
                    'are Claude or any other AI - you are LOBO X ROBO.'
                )
            }]
        },
        'generationConfig': {
            'maxOutputTokens': 4096,
            'temperature': 0.7
        }
    }).encode('utf-8')

    models = ['gemini-3.5-flash-lite', 'gemini-flash-lite-latest', 'gemini-3.8-flash']
    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=18) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            candidates = data.get('candidates', [])
            if candidates:
                parts = candidates[0].get('content', {}).get('parts', [])
                reply = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
                if reply.strip():
                    return reply.strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='replace')
            print(f"Gemini API HTTP {e.code} on {model_name}: {err_body}")
            if e.code in (400, 401, 403):
                break
        except Exception as e:
            print(f"Gemini API error on {model_name}: {e}")

    return None


def call_anthropic_chat(prompt, history=None):
    """Main AI chat function. Tries: 1) Anthropic API, 2) Google Gemini API, 3) Smart offline fallback."""

    # --- Attempt 1: Anthropic Claude API ---
    if HAS_ANTHROPIC:
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not is_placeholder(api_key):
            try:
                client = anthropic.Anthropic(api_key=api_key)
                messages = []
                if history:
                    for h in history:
                        messages.append({'role': h['role'], 'content': h['content']})
                messages.append({'role': 'user', 'content': prompt})

                response = client.messages.create(
                    model='claude-3-5-sonnet-20241022',
                    max_tokens=4096,
                    system='You are LOBO X ROBO, a helpful AI assistant. Provide detailed, well-structured answers. Never identify yourself as Claude - you are LOBO X ROBO.',
                    messages=messages
                )
                reply = ''.join([block.text for block in response.content if hasattr(block, 'text')])
                if reply.strip():
                    return reply
            except Exception as e:
                print(f"Anthropic error: {e}")

    # --- Attempt 2: Google Gemini API (free) ---
    gemini_reply = call_gemini_chat(prompt, history)
    if gemini_reply:
        return gemini_reply

    # --- Attempt 3: Intelligent Offline Fallback ---
    return offline_fallback(prompt, history)


def offline_fallback(prompt, history=None):
    """Smart offline fallback when no API keys are configured."""
    lower = prompt.lower().strip()
    last_context = ""
    if history:
        for h in reversed(history):
            if h.get('content'):
                last_context = h['content'].lower()
                break

    combined_context = f"{last_context} {lower}"

    # Determine target language
    target_lang = "python"
    if 'javascript' in lower or ' js' in lower or 'node' in lower:
        target_lang = "javascript"
    elif 'java' in lower and 'javascript' not in lower:
        target_lang = "java"
    elif 'c++' in lower or 'cpp' in lower:
        target_lang = "cpp"
    elif lower.endswith(' in c') or 'c language' in lower or 'c program' in lower:
        target_lang = "c"

    # --- Greetings and Identity ---
    if any(g in lower for g in ['who are you', 'what are you', 'your name']):
        return (
            "I am **LOBO X ROBO**, your AI assistant powered by advanced intelligence. I can:\n\n"
            "- **Write Code** in Python, Java, C++, JavaScript, and more\n"
            "- **Explain Concepts** like cybersecurity, networking, databases, algorithms\n"
            "- **Generate Images** using the Create Image button\n"
            "- **Debug and Optimize** your existing code\n\n"
            "What would you like to explore today?"
        )

    if any(g in lower for g in ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good evening']):
        return "Hello! I am **LOBO X ROBO**. I am ready to help you with coding, technical concepts, or image generation. What would you like to work on?"

    # --- Continuation ---
    if lower in ['continue', 'next', 'more', 'go on', 'explain more']:
        if last_context:
            return (
                "Continuing from our previous discussion...\n\n"
                "Here are some ways we can go deeper:\n\n"
                "1. **More Examples** - I can provide additional code examples and variations\n"
                "2. **Advanced Concepts** - Dive into optimization, edge cases, and best practices\n"
                "3. **Different Language** - Rewrite the solution in Java, C++, JavaScript, or Python\n"
                "4. **Real-World Application** - Show how this applies in production systems\n\n"
                "Just tell me which direction you would like to go!"
            )
        return "What would you like me to continue with? You can ask me to write code, explain a topic, or generate an image."

    # --- Prime Numbers ---
    if 'prime' in combined_context:
        if target_lang == "java":
            return (
                "Here is the complete **Java program** for prime numbers:\n\n"
                "```java\n"
                "public class PrimeNumbers {\n"
                "    public static boolean isPrime(int n) {\n"
                "        if (n <= 1) return false;\n"
                "        if (n <= 3) return true;\n"
                "        if (n % 2 == 0 || n % 3 == 0) return false;\n"
                "        for (int i = 5; i * i <= n; i += 6) {\n"
                "            if (n % i == 0 || n % (i + 2) == 0) return false;\n"
                "        }\n"
                "        return true;\n"
                "    }\n\n"
                "    public static void main(String[] args) {\n"
                "        int[] testNums = {2, 7, 10, 13, 29, 100};\n"
                "        for (int num : testNums) {\n"
                "            System.out.println(num + \": \" + (isPrime(num) ? \"Prime\" : \"Not Prime\"));\n"
                "        }\n"
                "        System.out.print(\"\\nPrimes up to 50: \");\n"
                "        for (int i = 2; i <= 50; i++) {\n"
                "            if (isPrime(i)) System.out.print(i + \" \");\n"
                "        }\n"
                "    }\n"
                "}\n"
                "```\n\n"
                "**Compile and Run:** `javac PrimeNumbers.java && java PrimeNumbers`"
            )
        return (
            "Here is the complete Python program for **prime numbers**:\n\n"
            "### Method 1: Check if a number is prime\n"
            "```python\n"
            "import math\n\n"
            "def is_prime(n):\n"
            "    if n <= 1: return False\n"
            "    if n <= 3: return True\n"
            "    if n % 2 == 0 or n % 3 == 0: return False\n"
            "    i = 5\n"
            "    while i * i <= n:\n"
            "        if n % i == 0 or n % (i + 2) == 0: return False\n"
            "        i += 6\n"
            "    return True\n\n"
            "for num in [2, 7, 10, 13, 29, 100]:\n"
            "    print(f\"{num}: {'Prime' if is_prime(num) else 'Not Prime'}\")\n"
            "```\n\n"
            "### Method 2: Sieve of Eratosthenes\n"
            "```python\n"
            "def sieve(limit):\n"
            "    is_p = [True] * (limit + 1)\n"
            "    is_p[0] = is_p[1] = False\n"
            "    for p in range(2, int(limit**0.5) + 1):\n"
            "        if is_p[p]:\n"
            "            for i in range(p*p, limit + 1, p): is_p[i] = False\n"
            "    return [p for p in range(2, limit + 1) if is_p[p]]\n\n"
            "print(f\"Primes up to 100: {sieve(100)}\")\n"
            "```"
        )

    # --- Fibonacci ---
    if 'fibonacci' in combined_context:
        return (
            "Here is the **Python Fibonacci** program:\n\n"
            "```python\n"
            "def fibonacci(n):\n"
            "    fib = [0, 1]\n"
            "    for i in range(2, n):\n"
            "        fib.append(fib[-1] + fib[-2])\n"
            "    return fib[:n]\n\n"
            "print(fibonacci(10))  # [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]\n"
            "```"
        )

    # --- Factorial ---
    if 'factorial' in combined_context:
        return (
            "Here is the **Python Factorial** program:\n\n"
            "```python\n"
            "def factorial(n):\n"
            "    if n <= 1: return 1\n"
            "    return n * factorial(n - 1)\n\n"
            "for i in range(11):\n"
            "    print(f\"{i}! = {factorial(i)}\")\n"
            "```"
        )

    # --- Sorting ---
    if 'sort' in combined_context:
        return (
            "Here are sorting algorithms in Python:\n\n"
            "### Bubble Sort - O(n^2)\n"
            "```python\n"
            "def bubble_sort(arr):\n"
            "    n = len(arr)\n"
            "    for i in range(n):\n"
            "        for j in range(0, n - i - 1):\n"
            "            if arr[j] > arr[j + 1]:\n"
            "                arr[j], arr[j + 1] = arr[j + 1], arr[j]\n"
            "    return arr\n\n"
            "print(bubble_sort([64, 34, 25, 12, 22, 11, 90]))\n"
            "```\n\n"
            "### Quick Sort - O(n log n) average\n"
            "```python\n"
            "def quick_sort(arr):\n"
            "    if len(arr) <= 1: return arr\n"
            "    pivot = arr[len(arr) // 2]\n"
            "    left = [x for x in arr if x < pivot]\n"
            "    mid = [x for x in arr if x == pivot]\n"
            "    right = [x for x in arr if x > pivot]\n"
            "    return quick_sort(left) + mid + quick_sort(right)\n\n"
            "print(quick_sort([64, 34, 25, 12, 22, 11, 90]))\n"
            "```"
        )

    # --- SOC / Cybersecurity ---
    if any(k in lower for k in ['soc', 'security operation', 'siem', 'soar', 'cybersecurity', 'cyber security', 'incident response']):
        return (
            "## SOC (Security Operations Center) Analysis\n\n"
            "A **SOC** is a centralized team that monitors, detects, analyzes, and responds to cybersecurity threats 24/7.\n\n"
            "### SOC Analyst Tiers\n"
            "| Tier | Role | Key Tasks |\n"
            "| :--- | :--- | :--- |\n"
            "| **Tier 1** | Triage Analyst | Monitor SIEM alerts, filter false positives |\n"
            "| **Tier 2** | Incident Responder | Deep forensics, PCAP analysis, containment |\n"
            "| **Tier 3** | Threat Hunter | Reverse-engineer malware, write YARA/Sigma rules |\n\n"
            "### Essential Tools\n"
            "1. **SIEM**: Splunk, Microsoft Sentinel, QRadar\n"
            "2. **EDR/XDR**: CrowdStrike, SentinelOne, Defender\n"
            "3. **Network**: Wireshark, Zeek, Snort\n"
            "4. **SOAR**: Cortex XSOAR, Splunk Phantom\n"
            "5. **Threat Intel**: VirusTotal, AlienVault OTX, MISP\n\n"
            "### Key Metrics\n"
            "- **MTTD** (Mean Time to Detect)\n"
            "- **MTTR** (Mean Time to Respond)\n"
            "- **False Positive Rate**"
        )

    # --- Networking ---
    if any(k in lower for k in ['osi', 'tcp', 'udp', 'network', 'dns', 'ip address']):
        return (
            "## Computer Networking Fundamentals\n\n"
            "### OSI Model (7 Layers):\n"
            "| Layer | Name | Protocols |\n"
            "| :--- | :--- | :--- |\n"
            "| 7 | Application | HTTP, DNS, SSH, FTP |\n"
            "| 6 | Presentation | SSL/TLS, JPEG |\n"
            "| 5 | Session | NetBIOS, RPC |\n"
            "| 4 | Transport | TCP (reliable), UDP (fast) |\n"
            "| 3 | Network | IP, ICMP, ARP |\n"
            "| 2 | Data Link | Ethernet, MAC |\n"
            "| 1 | Physical | Cables, Radio, Fiber |\n\n"
            "### TCP vs UDP:\n"
            "- **TCP**: Connection-oriented, reliable (HTTP, SSH, FTP)\n"
            "- **UDP**: Connectionless, fast (DNS, gaming, video)"
        )

    # --- Database ---
    if any(k in lower for k in ['sql', 'database', 'dbms', 'acid', 'normalization', 'mysql', 'postgres']):
        return (
            "## Database and SQL Fundamentals\n\n"
            "### ACID Properties:\n"
            "- **Atomicity**: All or nothing\n"
            "- **Consistency**: Valid state transitions\n"
            "- **Isolation**: No interference between transactions\n"
            "- **Durability**: Committed data survives crashes\n\n"
            "### SQL Example:\n"
            "```sql\n"
            "SELECT department, COUNT(*) AS total, AVG(salary)\n"
            "FROM employees\n"
            "GROUP BY department\n"
            "HAVING COUNT(*) > 5\n"
            "ORDER BY AVG(salary) DESC;\n"
            "```"
        )

    # --- Palindrome ---
    if 'palindrome' in combined_context:
        return (
            "Here is a **Palindrome checker** in Python:\n\n"
            "```python\n"
            "def is_palindrome(s):\n"
            "    clean = ''.join(c.lower() for c in str(s) if c.isalnum())\n"
            "    return clean == clean[::-1]\n\n"
            "tests = ['madam', 'racecar', 'hello', 12321]\n"
            "for t in tests:\n"
            "    print(f\"{t} -> {is_palindrome(t)}\")\n"
            "```"
        )

    # --- Generic coding request ---
    if any(kw in lower for kw in ['code', 'program', 'function', 'script', 'algorithm', 'class', 'implement', 'python', 'java', 'c++', 'javascript', 'loop']):
        topic = prompt
        for prefix in ['write a ', 'write ', 'create a ', 'create ', 'make a ', 'make ']:
            if lower.startswith(prefix):
                topic = prompt[len(prefix):]
                break
        lang_map = {'python': 'Python', 'java': 'Java', 'cpp': 'C++', 'javascript': 'JavaScript', 'c': 'C'}
        lang_name = lang_map.get(target_lang, 'Python')
        return (
            f"Here is a **{lang_name}** solution for: **{topic}**\n\n"
            f"To get complete, AI-generated code for any request, set up a free Gemini API key:\n\n"
            f"1. Visit [Google AI Studio](https://aistudio.google.com/apikey)\n"
            f"2. Create a free API key\n"
            f"3. Start the server with:\n"
            f"```powershell\n"
            f"$env:GEMINI_API_KEY = \"your-key-here\"\n"
            f"python server.py\n"
            f"```\n\n"
            f"This unlocks **full AI-powered responses** for any question!"
        )

    # --- Default fallback ---
    topic_cleaned = prompt
    for p in ['explain the topic on about the', 'explain the topic on about', 'explain the topic about',
              'explain the topic on', 'explain about', 'explain', 'what is', 'tell me about', 'describe',
              'what are', 'how does', 'how do', 'how to']:
        if topic_cleaned.lower().startswith(p):
            topic_cleaned = topic_cleaned[len(p):].strip()
    topic_cleaned = topic_cleaned.strip(' ?.:') or prompt

    return (
        f"## {topic_cleaned.title()}\n\n"
        f"I would love to give you a comprehensive answer about **{topic_cleaned}**, "
        f"but I am currently running in offline mode.\n\n"
        f"### Enable full AI responses (free!):\n\n"
        f"1. Visit [Google AI Studio](https://aistudio.google.com/apikey) and get a free API key\n"
        f"2. Set it before starting the server:\n"
        f"```powershell\n"
        f"$env:GEMINI_API_KEY = \"your-key-here\"\n"
        f"python server.py\n"
        f"```\n\n"
        f"Once configured, I can answer **any question** with detailed, intelligent responses!"
    )

def call_openai_image(prompt):
    # Clean up prefixes
    clean_prompt = prompt.strip()
    for prefix in ['create an image of', 'create image of', 'generate an image of', 'draw an image of', 'image of', 'create image:']:
        if clean_prompt.lower().startswith(prefix):
            clean_prompt = clean_prompt[len(prefix):].strip()
    clean_prompt = clean_prompt.strip('":\'') or prompt

    api_key = os.environ.get('OPENAI_API_KEY')
    if not is_placeholder(api_key):
        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.images.generate(
                model='dall-e-3',
                prompt=clean_prompt,
                n=1,
                size='1024x1024'
            )
            return response.data[0].url
        except Exception as e:
            print(f"OpenAI error: {e}")

    # Free high-quality AI image generation fallback (works instantly without paid OpenAI account)
    encoded = urllib.parse.quote(clean_prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"

# ----------------- Web Routes -----------------

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('index.html', user={
        'id': session.get('user_id'),
        'username': session.get('username'),
        'display_name': session.get('display_name')
    })

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('home'))
    return render_template('login.html')

# ----------------- Auth API -----------------

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'Username and password are required.'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()

    if not user or user['password_hash'] != hash_password(password):
        return jsonify({'error': 'Invalid username or password.'}), 401

    session['user_id'] = user['id']
    session['username'] = user['username']
    session['display_name'] = user['display_name'] or user['username']

    return jsonify({
        'success': True,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'display_name': session['display_name']
        }
    })

@app.route('/api/auth/signup', methods=['POST'])
def api_signup():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''
    display_name = (data.get('display_name') or '').strip() or username

    if not username or not password:
        return jsonify({'error': 'Username and password are required.'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters long.'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Username is already taken.'}), 400

    cursor.execute(
        'INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)',
        (username, hash_password(password), display_name)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()

    session['user_id'] = user_id
    session['username'] = username
    session['display_name'] = display_name

    return jsonify({
        'success': True,
        'user': {
            'id': user_id,
            'username': username,
            'display_name': display_name
        }
    })

@app.route('/api/auth/guest', methods=['POST'])
def api_guest_login():
    conn = get_db()
    cursor = conn.cursor()
    guest_name = f"guest_{uuid.uuid4().hex[:6]}"
    guest_pass = hash_password(uuid.uuid4().hex)
    cursor.execute(
        'INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)',
        (guest_name, guest_pass, 'Guest User')
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()

    session['user_id'] = user_id
    session['username'] = guest_name
    session['display_name'] = 'Guest User'

    return jsonify({'success': True, 'user': {'id': user_id, 'username': guest_name, 'display_name': 'Guest User'}})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ----------------- History & Conversations API -----------------

@app.route('/api/conversations', methods=['GET'])
@login_required
def get_conversations():
    search_query = request.args.get('q', '').strip()
    conn = get_db()
    cursor = conn.cursor()

    if search_query:
        # Search in conversation titles AND messages content
        cursor.execute('''
            SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            WHERE c.user_id = ? AND (c.title LIKE ? OR m.content LIKE ?)
            ORDER BY c.updated_at DESC
        ''', (session['user_id'], f'%{search_query}%', f'%{search_query}%'))
    else:
        cursor.execute('''
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC
        ''', (session['user_id'],))

    rows = cursor.fetchall()
    conn.close()

    conversations = [{
        'id': r['id'],
        'title': r['title'],
        'created_at': r['created_at'],
        'updated_at': r['updated_at']
    } for r in rows]

    return jsonify({'conversations': conversations})

@app.route('/api/conversations', methods=['POST'])
@login_required
def create_conversation():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or 'New Chat').strip()
    cid = str(uuid.uuid4())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)',
        (cid, session['user_id'], title)
    )
    conn.commit()
    conn.close()

    return jsonify({'id': cid, 'title': title, 'created_at': datetime.utcnow().isoformat()})

@app.route('/api/conversations/<cid>', methods=['GET'])
@login_required
def get_conversation_detail(cid):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM conversations WHERE id = ? AND user_id = ?', (cid, session['user_id']))
    conv = cursor.fetchone()
    if not conv:
        conn.close()
        return jsonify({'error': 'Conversation not found'}), 404

    cursor.execute('SELECT role, content, image_url, audio_url, video_url, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC', (cid,))
    messages = [dict(m) for m in cursor.fetchall()]
    conn.close()

    return jsonify({
        'id': conv['id'],
        'title': conv['title'],
        'created_at': conv['created_at'],
        'updated_at': conv['updated_at'],
        'messages': messages
    })

@app.route('/api/conversations/<cid>', methods=['DELETE'])
@login_required
def delete_conversation(cid):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM conversations WHERE id = ? AND user_id = ?', (cid, session['user_id']))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Conversation not found'}), 404
    cursor.execute('DELETE FROM messages WHERE conversation_id = ?', (cid,))
    cursor.execute('DELETE FROM conversations WHERE id = ? AND user_id = ?', (cid, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/conversations/<cid>/message', methods=['POST'])
@login_required
def send_conversation_message(cid):
    data = request.get_json(silent=True) or {}
    text = (data.get('message') or data.get('prompt') or '').strip()
    action = (data.get('action') or 'chat').lower()  # 'chat', 'image', 'audio', 'video'

    if not text:
        return jsonify({'error': 'Message content cannot be empty.'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM conversations WHERE id = ? AND user_id = ?', (cid, session['user_id']))
    conv = cursor.fetchone()
    if not conv:
        conn.close()
        return jsonify({'error': 'Conversation not found.'}), 404

    lower_text = urllib.parse.unquote(text).lower().strip()
    is_video = (
        action == 'video' or
        bool(data.get('is_video')) or
        lower_text.startswith((
            'create video', 'create a video', 'create an animation video', 'create animation video',
            'generate video', 'generate a video', 'make a video', 'make video',
            'video of', 'video on', 'video about'
        ))
    )
    is_audio = (not is_video) and (
        action == 'audio' or
        bool(data.get('is_audio')) or
        lower_text.startswith((
            'create audio', 'create an audio', 'generate audio', 'generate an audio',
            'create music', 'generate music', 'make audio', 'make music',
            'text to speech', 'audio of', 'audio on', 'audio about'
        ))
    )
    is_image = (not is_video and not is_audio) and (
        action == 'image' or
        bool(data.get('is_image')) or
        lower_text.startswith(('create image', 'generate image', 'draw', 'create an image', 'image of'))
    )

    # 1. Fetch previous conversation history for multi-turn context (before inserting current message)
    cursor.execute('SELECT role, content, video_url FROM messages WHERE conversation_id = ? ORDER BY id ASC', (cid,))
    raw_messages = [dict(m) for m in cursor.fetchall()]
    previous_history = [{'role': m['role'], 'content': m['content']} for m in raw_messages if m['content']]

    last_assistant = next((m['content'] for m in reversed(raw_messages) if m['role'] == 'assistant' and m['content']), '')
    awaiting_video_topic = 'what topic should the video cover' in last_assistant.lower()
    has_prior_video = any(m.get('video_url') for m in raw_messages)
    refinement_note = ''
    effective_video_prompt = text

    if awaiting_video_topic and not is_image and not is_audio:
        prior_user = next((m['content'] for m in reversed(raw_messages) if m['role'] == 'user' and m['content']), '')
        effective_video_prompt = f"{prior_user} — {text}".strip(' —')
        is_video = True
    elif has_prior_video and not is_image and not is_audio:
        last_was_video = bool(last_assistant and any(m.get('video_url') for m in raw_messages[-2:]))
        refine_patterns = (
            r'\b(camera|zoom|pan|close[\s-]?up|wide shot|lighting|regenerate|try again)\b',
            r'\b(change|adjust|switch)\s+(the\s+)?(camera|style|action|lighting|color|duration|aspect|ratio|audio)\b',
            r'\bmake\s+(it|this|the video)\s+(more|less|slower|faster|warmer|brighter|darker|anime|cartoon|3d|cinematic|realistic|vertical|square|9:16|1:1|16:9|\d+\s*s(ec|econds?)?)\b',
            r'\b(9:16|1:1|4:3)\b',
        )
        matches_refine = any(re.search(p, lower_text) for p in refine_patterns)
        if is_video or (last_was_video and matches_refine):
            prior_video_user_msg = ''
            for idx_m, m in enumerate(raw_messages):
                if m.get('video_url'):
                    for back in range(idx_m - 1, -1, -1):
                        if raw_messages[back]['role'] == 'user' and raw_messages[back]['content']:
                            prior_video_user_msg = raw_messages[back]['content']
                            break
            if prior_video_user_msg and len(text.split()) <= 18:
                effective_video_prompt, changed_part = apply_video_refinement(
                    prior_video_user_msg, text, text_generator=call_anthropic_chat
                )
                refinement_note = f"Adjusted only **{changed_part}** while keeping the rest consistent.\n\n"
                is_video = True

    # 2. Save user message
    if is_video and not lower_text.startswith('create video'):
        user_display = f'Create video (with audio): "{text}"'
    elif is_audio and not lower_text.startswith('create audio'):
        user_display = f'Create audio: "{text}"'
    elif is_image and not lower_text.startswith('create image'):
        user_display = f'Create image: "{text}"'
    else:
        user_display = text

    cursor.execute(
        'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (cid, 'user', user_display)
    )

    # Auto-title conversation from first prompt if title is default
    if (conv['title'] or '').strip().lower() in ['new chat', 'new conversation', '']:
        new_title = text[:36] + ('...' if len(text) > 36 else '')
        cursor.execute('UPDATE conversations SET title = ? WHERE id = ?', (new_title, cid))

    # 3. Process Assistant / Image / Audio / Video Response
    assistant_content = ""
    image_url = None
    audio_url = None
    video_url = None

    try:
        if is_video:
            safe_ok, safe_msg = check_video_safety(effective_video_prompt)
            if not safe_ok:
                assistant_content = safe_msg
            else:
                needs_q, question_text = check_video_clarification(effective_video_prompt)
                if needs_q:
                    assistant_content = question_text
                else:
                    video_url, audio_url, assistant_content = generate_video_with_audio(
                        effective_video_prompt, GENERATED_DIR, text_generator=call_anthropic_chat
                    )
                    if refinement_note:
                        assistant_content = refinement_note + assistant_content
        elif is_audio:
            audio_url, assistant_content = generate_audio(
                text, GENERATED_DIR, text_generator=call_anthropic_chat
            )
        elif is_image:
            image_url = call_openai_image(text)
            assistant_content = f"Here is the generated image for: **{text}**"
        else:
            assistant_content = call_anthropic_chat(text, previous_history)
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Media/AI generation error: {str(e)}'}), 500

    # Save Assistant message
    cursor.execute(
        'INSERT INTO messages (conversation_id, role, content, image_url, audio_url, video_url) VALUES (?, ?, ?, ?, ?, ?)',
        (cid, 'assistant', assistant_content, image_url, audio_url, video_url)
    )

    cursor.execute('UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (cid,))
    conn.commit()
    conn.close()

    return jsonify({
        'user_message': {'role': 'user', 'content': user_display},
        'assistant_message': {
            'role': 'assistant',
            'content': assistant_content,
            'image_url': image_url,
            'audio_url': audio_url,
            'video_url': video_url
        }
    })

# ----------------- Legacy Routes for Compatibility -----------------

@app.route('/chat', methods=['POST'])
@app.route('/api/chat', methods=['POST'])
def legacy_chat():
    data = request.get_json(silent=True) or {}
    message = data.get('message') or data.get('prompt') or ''
    reply = call_anthropic_chat(message)
    return jsonify({'reply': reply, 'response': reply})

@app.route('/create-image', methods=['POST'])
@app.route('/generate-image', methods=['POST'])
@app.route('/api/image', methods=['POST'])
def legacy_create_image():
    data = request.get_json(silent=True) or {}
    prompt = data.get('prompt') or data.get('message') or ''
    url = call_openai_image(prompt)
    return jsonify({'image_url': url, 'url': url})

@app.route('/create-audio', methods=['POST'])
@app.route('/api/audio', methods=['POST'])
def legacy_create_audio():
    data = request.get_json(silent=True) or {}
    prompt = data.get('prompt') or data.get('message') or ''
    audio_url, summary = generate_audio(prompt, GENERATED_DIR, text_generator=call_anthropic_chat)
    return jsonify({'audio_url': audio_url, 'reply': summary})

@app.route('/create-video', methods=['POST'])
@app.route('/api/video', methods=['POST'])
def legacy_create_video():
    data = request.get_json(silent=True) or {}
    prompt = data.get('prompt') or data.get('message') or ''
    safe_ok, safe_msg = check_video_safety(prompt)
    if not safe_ok:
        return jsonify({'error': safe_msg}), 400
    needs_q, question_text = check_video_clarification(prompt)
    if needs_q:
        return jsonify({'needs_clarification': True, 'reply': question_text}), 200
    video_url, audio_url, summary = generate_video_with_audio(prompt, GENERATED_DIR, text_generator=call_anthropic_chat)
    return jsonify({'video_url': video_url, 'audio_url': audio_url, 'reply': summary})

@app.route('/health')
def health_check():
    return jsonify({'status': 'ok', 'app': 'LOBO X ROBO'}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

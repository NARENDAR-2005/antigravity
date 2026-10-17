# AI Job-Search Agent & Career Portal

A full-stack, autonomous AI job-search web application built for **Fresh Graduates** (featuring a neutral **Sample Fresher** demo profile).

The application features:
* **26 Curated & Verified Active Job Openings** across India (Accenture, TCS, Cognizant, Infosys, Cisco, Zoho, Bosch, PhonePe, Razorpay, etc.) with verified official career portal application links.
* **Fit Score Engine (0-100)**: Evaluates candidate technical capabilities (Python, ML/CV, Cyber Security, SQL, Flask) against real job specifications.
* **Application Kanban Tracker**: Persistent pipeline tracking for *Saved*, *Applied*, *Interviewing*, and *Offer* stages with custom notes.
* **AI Resume Auditor & Live JD Matcher**: Evaluates resumes on ATS criteria, highlights quantified XYZ metrics, detects missing keywords, and benchmarks against any pasted job description.
* **Recruiter Outreach Studio**: Generates customized LinkedIn connection notes (<300 characters strictly) and detailed InMail / direct email pitches with 1-click clipboard copying.

---

## 🚀 Quick Launch

### Option 1: One-Click Windows Launcher
Double-click `run_app.bat` in this folder. It will start the server and open `http://127.0.0.1:8000` directly in your browser.

### Option 2: Python Command Line
```bash
python run_app.py
```
Or with Uvicorn directly:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 📂 Project Architecture

```
Ai agent/
├── app/
│   ├── main.py                  # FastAPI application & REST endpoints
│   ├── models.py                # Pydantic request & response schemas
│   ├── resume_engine.py         # ATS scoring, file text extraction, keyword analysis
│   └── outreach_engine.py       # Personalized recruiter outreach generator
├── data/
│   ├── jobs.json                # Verified dataset of 26 active positions
│   ├── profile.json             # Sample Fresher analyzed profile & 5 target roles
│   └── tracker.json             # Application tracking state (Saved, Applied, Notes)
├── static/
│   ├── css/
│   │   └── style.css            # Custom styles & badge definitions
│   └── js/
│       └── app.js               # Client-side API client, reactive UI & modal logic
├── templates/
│   └── index.html               # Responsive single-page application dashboard
├── Sample_Fresher_ATS_Resume.md # Optimized ATS-ready Markdown resume
├── job_search_dashboard.html    # Standalone, portable offline HTML dashboard
├── run_app.py                   # Python server launcher with auto-browser opening
├── run_app.bat                  # 1-click Windows batch file
└── README.md                    # Documentation
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves the interactive application UI |
| `GET` | `/docs` | Interactive Swagger API documentation |
| `GET` | `/api/jobs` | Get jobs with query, category, track, location, and sorting filters |
| `GET` | `/api/jobs/{id}` | Get detailed single job match analysis |
| `POST` | `/api/jobs/{id}/status` | Update application stage (`saved`, `applied`, `interviewing`, `offers`) |
| `POST` | `/api/jobs/{id}/note` | Save personal application notes |
| `GET` | `/api/tracker` | Retrieve full application pipeline status |
| `GET` | `/api/profile` | Retrieve candidate profile and 5 target roles |
| `POST` | `/api/resume/audit-existing` | Run ATS audit on candidate's optimized resume |
| `POST` | `/api/resume/upload` | Upload & audit any PDF, DOCX, or TXT resume |
| `POST` | `/api/resume/match-jd` | Match candidate resume against any pasted Job Description |
| `POST` | `/api/outreach/generate` | Generate custom LinkedIn connection note & InMail |
| `GET` | `/api/resume/download-ats` | Download clean ATS-formatted resume (.md) |

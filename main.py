import os
import json
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.models import StatusUpdateRequest, NoteUpdateRequest, CustomOutreachRequest, JobDescriptionAuditRequest
from app.resume_engine import (
    extract_text_from_file,
    audit_resume_text,
    compare_resume_with_job,
    parse_candidate_profile,
    rank_and_score_jobs_for_resume
)
from app.outreach_engine import generate_personalized_outreach

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
JOBS_PATH = os.path.join(DATA_DIR, "jobs.json")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")
TRACKER_PATH = os.path.join(DATA_DIR, "tracker.json")
ATS_RESUME_PATH = os.path.join(BASE_DIR, "Sample_Fresher_ATS_Resume.md")

app = FastAPI(
    title="AI Job Search Agent & Career Engine",
    description="Full-stack AI Job-Search application for Sample Fresher featuring 26 verified active tech jobs, ATS scoring, and recruiter outreach.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = os.path.join(BASE_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def load_json(path: str, default: Any = None) -> Any:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path: str, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    template_path = os.path.join(BASE_DIR, "templates", "index.html")
    no_cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), headers=no_cache_headers)
    return HTMLResponse("<h1>AI Job Search Agent Backend Running</h1><p>Template loading...</p>", headers=no_cache_headers)


@app.get("/api/jobs")
async def get_jobs(
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    track: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    sort: Optional[str] = Query("fit-desc")
):
    jobs = load_json(JOBS_PATH, [])
    tracker = load_json(TRACKER_PATH, {"saved": [], "applied": [], "interviewing": [], "offers": []})

    # Attach tracker status to each job
    enriched_jobs = []
    for job in jobs:
        jid = job.get("id")
        status = "None"
        if jid in tracker.get("offers", []): status = "Offer"
        elif jid in tracker.get("interviewing", []): status = "Interviewing"
        elif jid in tracker.get("applied", []): status = "Applied"
        elif jid in tracker.get("saved", []): status = "Saved"
        
        job_copy = dict(job)
        job_copy["trackerStatus"] = status
        job_copy["trackerNote"] = tracker.get("notes", {}).get(str(jid), "")
        enriched_jobs.append(job_copy)

    # Filter logic
    filtered = enriched_jobs
    if q:
        query_str = q.lower().strip()
        filtered = [
            j for j in filtered if (
                query_str in j.get("title", "").lower() or
                query_str in j.get("company", "").lower() or
                query_str in j.get("location", "").lower() or
                any(query_str in s.lower() for s in j.get("keySkills", []))
            )
        ]

    if category and category != "ALL":
        filtered = [j for j in filtered if j.get("category") == category]

    if track and track != "ALL":
        filtered = [j for j in filtered if j.get("track") == track]

    if location and location != "ALL":
        filtered = [j for j in filtered if location.lower() in j.get("location", "").lower()]

    # Sort logic
    if sort == "fit-desc":
        filtered.sort(key=lambda x: x.get("fitScore", 0), reverse=True)
    elif sort == "fit-asc":
        filtered.sort(key=lambda x: x.get("fitScore", 0))
    elif sort == "company-asc":
        filtered.sort(key=lambda x: x.get("company", "").lower())

    return {
        "total": len(jobs),
        "count": len(filtered),
        "jobs": filtered
    }


@app.get("/api/jobs/{job_id}")
async def get_job_by_id(job_id: int):
    jobs = load_json(JOBS_PATH, [])
    job = next((j for j in jobs if j.get("id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    tracker = load_json(TRACKER_PATH, {})
    status = "None"
    if job_id in tracker.get("offers", []): status = "Offer"
    elif job_id in tracker.get("interviewing", []): status = "Interviewing"
    elif job_id in tracker.get("applied", []): status = "Applied"
    elif job_id in tracker.get("saved", []): status = "Saved"

    job_data = dict(job)
    job_data["trackerStatus"] = status
    job_data["trackerNote"] = tracker.get("notes", {}).get(str(job_id), "")
    return job_data


@app.post("/api/jobs/{job_id}/status")
async def update_job_status(job_id: int, payload: StatusUpdateRequest):
    tracker = load_json(TRACKER_PATH, {"saved": [], "applied": [], "interviewing": [], "offers": [], "notes": {}})
    new_status = payload.status.lower()

    # Remove from all current lists
    for key in ["saved", "applied", "interviewing", "offers"]:
        if job_id in tracker[key]:
            tracker[key].remove(job_id)

    # Add to target list
    if new_status in ["saved", "applied", "interviewing", "offers"]:
        tracker[new_status].append(job_id)

    save_json(TRACKER_PATH, tracker)
    return {"success": True, "jobId": job_id, "newStatus": new_status, "tracker": tracker}


@app.post("/api/jobs/{job_id}/note")
async def update_job_note(job_id: int, payload: NoteUpdateRequest):
    tracker = load_json(TRACKER_PATH, {"saved": [], "applied": [], "interviewing": [], "offers": [], "notes": {}})
    if "notes" not in tracker:
        tracker["notes"] = {}
    tracker["notes"][str(job_id)] = payload.note
    save_json(TRACKER_PATH, tracker)
    return {"success": True, "jobId": job_id, "note": payload.note}


@app.get("/api/tracker")
async def get_tracker():
    tracker = load_json(TRACKER_PATH, {"saved": [], "applied": [], "interviewing": [], "offers": [], "notes": {}})
    jobs = {j["id"]: j for j in load_json(JOBS_PATH, [])}

    return {
        "stats": {
            "savedCount": len(tracker.get("saved", [])),
            "appliedCount": len(tracker.get("applied", [])),
            "interviewingCount": len(tracker.get("interviewing", [])),
            "offersCount": len(tracker.get("offers", []))
        },
        "savedJobs": [jobs[jid] for jid in tracker.get("saved", []) if jid in jobs],
        "appliedJobs": [jobs[jid] for jid in tracker.get("applied", []) if jid in jobs],
        "interviewingJobs": [jobs[jid] for jid in tracker.get("interviewing", []) if jid in jobs],
        "offersJobs": [jobs[jid] for jid in tracker.get("offers", []) if jid in jobs],
        "notes": tracker.get("notes", {})
    }


@app.get("/api/profile")
async def get_profile():
    profile = load_json(PROFILE_PATH, {})
    return profile


@app.get("/api/top10")
async def get_top10():
    jobs = load_json(JOBS_PATH, [])
    top10 = sorted(jobs, key=lambda x: x.get("fitScore", 0), reverse=True)[:10]
    return top10


@app.post("/api/resume/audit-existing")
async def audit_existing_resume():
    """Audits the candidate's ATS-optimized resume vs the legacy resume."""
    ats_text = ""
    if os.path.exists(ATS_RESUME_PATH):
        with open(ATS_RESUME_PATH, "r", encoding="utf-8") as f:
            ats_text = f.read()

    # Legacy raw resume for comparison
    legacy_path = os.path.join(BASE_DIR, "extracted_resume.txt")
    legacy_text = ""
    if os.path.exists(legacy_path):
        with open(legacy_path, "r", encoding="utf-8", errors="ignore") as f:
            legacy_text = f.read()

    ats_audit = audit_resume_text(ats_text) if ats_text else {}
    legacy_audit = audit_resume_text(legacy_text) if legacy_text else {}

    return {
        "atsOptimized": {
            "text": ats_text,
            "audit": ats_audit
        },
        "legacyResume": {
            "text": legacy_text[:1000] if legacy_text else "",
            "audit": legacy_audit
        }
    }


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Receives an uploaded resume, extracts text, and calculates ATS score."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext == ".doc":
        raise HTTPException(status_code=400, detail="Legacy .doc format is not supported. Please save as .docx or PDF.")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a PDF, DOCX, or TXT file.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty. Please upload a valid resume.")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 5 MB. Please upload a smaller resume document.")

    temp_dir = os.path.join(BASE_DIR, "data", "uploads")
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, file.filename)

    with open(temp_file_path, "wb") as f:
        f.write(content)

    extracted_text = extract_text_from_file(temp_file_path)
    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract readable text from this file. It may be empty or corrupted. Try pasting the text instead.")

    profile = parse_candidate_profile(extracted_text)
    audit = audit_resume_text(extracted_text)

    return {
        "filename": file.filename,
        "extractedLength": len(extracted_text),
        "profile": profile,
        "audit": audit
    }


@app.post("/api/resume/upload-and-match")
async def upload_and_match(file: UploadFile = File(...)):
    """Uploads a new resume, parses profile, and returns dynamically ranked job openings."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext == ".doc":
        raise HTTPException(status_code=400, detail="Legacy .doc format is not supported. Please save as .docx or PDF.")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a PDF, DOCX, or TXT file.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty. Please upload a valid resume.")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 5 MB. Please upload a smaller resume document.")

    temp_dir = os.path.join(BASE_DIR, "data", "uploads")
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, file.filename)

    with open(temp_file_path, "wb") as f:
        f.write(content)

    resume_text = extract_text_from_file(temp_file_path)
    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract readable text from this file. It may be empty or corrupted. Try pasting the text instead.")

    profile = parse_candidate_profile(resume_text)
    audit = audit_resume_text(resume_text)
    
    jobs = load_json(JOBS_PATH, [])
    ranked_jobs = rank_and_score_jobs_for_resume(resume_text, jobs)

    return {
        "success": True,
        "filename": file.filename,
        "profile": profile,
        "audit": audit,
        "rankedJobs": ranked_jobs,
        "totalJobs": len(ranked_jobs),
        "resumeText": resume_text,
        "previewText": resume_text[:1200]
    }


@app.post("/api/resume/paste-and-match")
async def paste_and_match(payload: Dict[str, str]):
    """Accepts pasted resume text, parses profile, and returns dynamically ranked job openings."""
    resume_text = payload.get("resumeText") or payload.get("resume_text", "")
    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="Resume text cannot be empty.")

    profile = parse_candidate_profile(resume_text)
    audit = audit_resume_text(resume_text)
    
    jobs = load_json(JOBS_PATH, [])
    ranked_jobs = rank_and_score_jobs_for_resume(resume_text, jobs)

    return {
        "success": True,
        "profile": profile,
        "audit": audit,
        "rankedJobs": ranked_jobs,
        "totalJobs": len(ranked_jobs),
        "resumeText": resume_text,
        "previewText": resume_text[:1200]
    }


@app.post("/api/resume/match-jd")
async def match_with_jd(payload: JobDescriptionAuditRequest):
    """Matches candidate resume against any pasted Job Description."""
    ats_text = ""
    if os.path.exists(ATS_RESUME_PATH):
        with open(ATS_RESUME_PATH, "r", encoding="utf-8") as f:
            ats_text = f.read()

    jd_lower = payload.jobDescription.lower()
    resume_lower = ats_text.lower()

    # Extract detected technical skills in JD
    detected_in_jd = []
    for cat, kws in [
        ("skills", ["python", "java", "c", "sql", "flask", "django", "fastapi", "numpy", "pandas", "matplotlib", "yolo", "lstm", "git", "linux", "docker", "aws", "rest api", "cyber security", "data structures", "algorithms"])
    ]:
        for kw in kws:
            if kw in jd_lower:
                detected_in_jd.append(kw)

    matched = [kw for kw in detected_in_jd if kw in resume_lower]
    missing = [kw for kw in detected_in_jd if kw not in resume_lower]
    
    match_score = int((len(matched) / max(1, len(detected_in_jd))) * 100) if detected_in_jd else 85

    return {
        "jobTitle": payload.jobTitle,
        "matchScore": match_score,
        "skillsIdentifiedInJD": detected_in_jd,
        "matchedSkills": matched,
        "missingSkills": missing
    }


@app.post("/api/outreach/generate")
async def generate_outreach(payload: CustomOutreachRequest):
    profile = load_json(PROFILE_PATH, {})
    outreach = generate_personalized_outreach(
        candidate_name=profile.get("name", "Sample Fresher"),
        candidate_phone=profile.get("phone", "+91 98765 43210"),
        candidate_email=profile.get("email", "sample.fresher@example.com"),
        portfolio_url="https://github.com/sample-fresher",
        company=payload.company,
        role=payload.role,
        recruiter_name=payload.recruiterName or "Hiring Team",
        project_focus=payload.projectFocus or "Smart Traffic Vision System (LSTM + YOLO) and Python Automation"
    )
    return outreach


@app.get("/api/resume/download-ats")
async def download_ats_resume():
    if os.path.exists(ATS_RESUME_PATH):
        return FileResponse(
            path=ATS_RESUME_PATH,
            filename="Sample_Fresher_ATS_Resume.md",
            media_type="text/markdown"
        )
    raise HTTPException(status_code=404, detail="Resume file not found")

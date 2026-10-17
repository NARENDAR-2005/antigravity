import os
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

KEYWORD_CATEGORIES = {
    "languages": ["python", "c", "c++", "java", "sql", "javascript", "html", "css", "bash", "shell"],
    "frameworks": ["flask", "django", "fastapi", "numpy", "pandas", "matplotlib", "yolo", "yolov8", "lstm", "scikit-learn", "tensorflow", "pytorch", "opencv"],
    "databases": ["mysql", "postgresql", "sqlite", "mongodb", "redis"],
    "tools_infra": ["git", "github", "linux", "unix", "docker", "aws", "azure", "postman", "jupyter", "rest api", "ci/cd"],
    "cybersecurity": ["cyber security", "network security", "soc", "siem", "vapt", "wireshark", "incident response", "cryptography", "firewall"],
    "soft_skills": ["teamwork", "leadership", "problem-solving", "communication", "collaboration", "analytical"]
}

STRONG_ACTION_VERBS = [
    "engineered", "developed", "architected", "implemented", "automated",
    "optimized", "accelerated", "reduced", "improved", "deployed",
    "designed", "spearheaded", "orchestrated", "streamlined", "integrated",
    "constructed", "formulated", "delivered", "analyzed", "led"
]

TECH_KEYWORDS_DICTIONARY = [
    'python', 'javascript', 'typescript', 'java', 'c', 'c++', 'sql', 'bash', 'html', 'css',
    'react', 'next.js', 'vue', 'node.js', 'express', 'flask', 'django', 'fastapi', 'spring boot',
    'rest api', 'restful', 'graphql', 'microservices', 'crud',
    'mysql', 'postgresql', 'mongodb', 'sqlite', 'redis', 'firebase',
    'git', 'github', 'linux', 'ubuntu', 'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'ci/cd',
    'data structures', 'algorithms', 'oop', 'oops', 'dbms', 'operating systems', 'computer networks',
    'machine learning', 'deep learning', 'tensorflow', 'pytorch', 'opencv', 'yolo', 'lstm',
    'pandas', 'numpy', 'scikit-learn', 'matplotlib',
    'cyber security', 'network security', 'cryptography', 'penetration testing', 'soc',
    'unit testing', 'jest', 'pytest', 'postman'
]

OUTDATED_ATS_PATTERNS = [
    'curriculum vitae',
    'objective:',
    'references available upon request',
    'date of birth',
    'marital status',
    'hobbies:',
    'mother tongue'
]

NEGATIVE_PATTERNS = [
    (r"-\d{4,}-\d{4,}", "Raw template generator numbers detected (e.g. -51435-430530)"),
    (r"let me know if you’d like", "AI/template placeholder conversational remnant found"),
    (r"resume\s+---\s+resume", "Duplicate resume title banner repeated"),
    (r"4rd year", "Typographical error in education ('4rd Year' instead of '4th Year')"),
    (r"python for data sciece", "Typo in certification title ('sciece' instead of 'science')")
]


def extract_text_from_file(file_path: str) -> str:
    """Extracts raw text from PDF, DOCX, or TXT/MD files."""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".txt" or ext == ".md":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
            
    elif ext == ".pdf":
        if not PdfReader:
            return "PDF reader library not available."
        try:
            reader = PdfReader(file_path)
            text_parts = []
            embedded_uris = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
                # Also extract embedded hyperlink annotations (/Annots -> /A -> /URI)
                try:
                    annots = page.get("/Annots")
                    if annots:
                        for annot in annots:
                            obj = annot.get_object()
                            action = obj.get("/A") if hasattr(obj, "get") else None
                            if action and hasattr(action, "get"):
                                uri = action.get("/URI")
                                if uri and isinstance(uri, str) and uri not in embedded_uris:
                                    embedded_uris.append(str(uri))
                except Exception:
                    pass
            full_text = "\n".join(text_parts)
            if embedded_uris:
                full_text = full_text + "\n" + "\n".join(embedded_uris)
            return full_text
        except Exception:
            return ""
            
    elif ext == ".docx":
        try:
            with zipfile.ZipFile(file_path) as z:
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                paragraphs = []
                for node in tree.iter():
                    if node.tag.endswith("}p"):
                        p_text = "".join(node.itertext()).strip()
                        if p_text:
                            paragraphs.append(p_text)
                # Also extract hyperlink relationships from word/_rels/document.xml.rels
                if "word/_rels/document.xml.rels" in z.namelist():
                    try:
                        rels_xml = z.read("word/_rels/document.xml.rels")
                        rels_tree = ET.fromstring(rels_xml)
                        for rel in rels_tree.iter():
                            target = rel.attrib.get("Target", "")
                            if target.startswith(("http://", "https://", "mailto:")):
                                paragraphs.append(target)
                    except Exception:
                        pass
                return "\n".join(paragraphs)
        except Exception:
            return ""
            
    return ""


PHONE_REGEX = r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\d{5}[-.\s]?\d{5})"
EMAIL_REGEX = r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}"
LINKEDIN_REGEX = r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in/|pub/)?[\w\-]+/?"
GITHUB_REGEX = r"(?:https?://)?(?:www\.)?(?:github\.com/[\w\-]+|[\w\-]+\.github\.io(?:/[\w\-]+)?)/?"

SECTION_HEADINGS = {
    "SUMMARY", "PROFESSIONAL SUMMARY", "OBJECTIVE", "CAREER OBJECTIVE", "PROFILE",
    "EDUCATION", "ACADEMIC BACKGROUND", "QUALIFICATIONS",
    "TECHNICAL SKILLS", "SKILLS", "CORE COMPETENCIES", "TECHNOLOGIES",
    "PROJECTS", "ACADEMIC PROJECTS", "KEY PROJECTS", "PERSONAL PROJECTS",
    "EXPERIENCE", "WORK EXPERIENCE", "INTERNSHIPS", "INTERNSHIP", "EMPLOYMENT",
    "CERTIFICATIONS", "CERTIFICATES", "ACHIEVEMENTS", "AWARDS"
}


def _is_section_heading(line: str) -> Optional[str]:
    cleaned = re.sub(r"^[\s#*\-•–—:]+|[\s#*\-•–—:]+$", "", line).strip().upper()
    if cleaned in SECTION_HEADINGS:
        return cleaned
    return None


def parse_candidate_profile(resume_text: str) -> Dict[str, Any]:
    """Parses candidate name, contact, links, skills, education, projects, and real lines from raw resume text."""
    # Rejoin emails that were wrapped across lines in narrow PDF columns (e.g. "user@gmail.\ncom")
    normalized_text = re.sub(r"([\w\.-]+@[\w\.-]+\.)\s*\n\s*([a-zA-Z]{2,})", r"\1\2", resume_text)
    lines = [l.strip() for l in normalized_text.splitlines() if l.strip()]
    text_lower = normalized_text.lower()

    # 1. Candidate Name extraction from actual resume lines
    name = "Not found"
    non_name_tokens = {
        "RESUME", "CURRICULUM", "VITAE", "PROFILE", "OBJECTIVE", "SUMMARY",
        "EMAIL", "PHONE", "CONTACT", "LINKEDIN", "GITHUB", "HTTP", "@",
        "ENGINEER", "DEVELOPER", "ANALYST", "STUDENT", "INTERN", "SPECIALIST",
        "CYBERSECURITY", "SECURITY", "SOFTWARE", "FULLSTACK", "BACKEND", "FRONTEND",
        "B.TECH", "BTECH", "INSTITUTE", "INSTITUTION", "TECHNOLOGY", "TECHNOLOGIES", "UNIVERSITY", "COLLEGE", "SCHOOL",
        "PRIVATE", "LTD", "LIMITED", "SOLUTIONS", "SERVICES", "SYSTEMS", "CORP", "CORPORATION",
        "EXPERIENCE", "EDUCATION", "SKILLS", "PROJECTS", "CERTIFICATIONS", "ACHIEVEMENTS",
        "LANGUAGE", "LANGUAGES", "COMPUTER", "WORK", "TECHNICAL", "PERSONAL", "ACADEMIC",
        "HYDERABAD", "BANGALORE", "BENGALURU", "CHENNAI", "MUMBAI", "DELHI", "PUNE", "INDIA",
        "KHAMMAM", "TELANGANA", "ENGLISH", "HINDI", "TELUGU", "PYTHON", "JAVA", "MYSQL", "SQL"
    }
    single_word_fallback = "Not found"
    for idx, line in enumerate(lines[:35]):
        cleaned = re.sub(r"[#\*\-_\|:]", " ", line).strip()
        upper_cleaned = cleaned.upper()
        if _is_section_heading(line) or any(h in upper_cleaned.split() or h in upper_cleaned for h in non_name_tokens):
            continue
        words = cleaned.split()
        if 1 <= len(words) <= 4 and all((w.isalpha() or "." in w) and w[0].isupper() for w in words):
            if len(words) >= 2 or "." in words[0]:
                name = cleaned
                break
            elif single_word_fallback == "Not found" and idx < 8:
                single_word_fallback = cleaned
    if name == "Not found" and single_word_fallback != "Not found":
        name = single_word_fallback

    # 2. Contact details & real links
    email_match = re.search(EMAIL_REGEX, normalized_text)
    email = email_match.group(0) if email_match else "Not found"

    phone_match = re.search(PHONE_REGEX, normalized_text)
    phone = phone_match.group(0).strip() if phone_match else "Not found"

    linkedin_match = re.search(LINKEDIN_REGEX, normalized_text, re.IGNORECASE)
    if linkedin_match:
        linkedin = re.sub(r"^https?://(?:www\.)?", "", linkedin_match.group(0)).rstrip("/")
    elif re.search(r"\blinkedin\b", normalized_text, re.IGNORECASE):
        linkedin = "LinkedIn (Detected in Resume)"
    else:
        linkedin = "Not found"

    github_match = re.search(GITHUB_REGEX, normalized_text, re.IGNORECASE)
    if github_match:
        github = re.sub(r"^https?://(?:www\.)?", "", github_match.group(0)).rstrip("/")
    elif re.search(r"\bgithub\b", normalized_text, re.IGNORECASE):
        github = "GitHub (Detected in Resume)"
    else:
        github = "Not found"

    # 3. Extract actual header lines (lines before the first section heading, up to 3 lines)
    header_lines: List[str] = []
    for line in lines[:6]:
        if _is_section_heading(line):
            break
        header_lines.append(line)
        if len(header_lines) >= 3:
            break
    if not header_lines and lines:
        header_lines = lines[:2]

    # 4. Education extraction from actual resume text (never guess a fake degree if not present)
    education = "Not found"
    deg_patterns = [
        (r"b\.?\s*tech(?:\s+in)?\s+[a-zA-Z\s&\(\)]+", "B.Tech"),
        (r"bachelor\s+of\s+technology(?:\s+in)?\s+[a-zA-Z\s&\(\)]+", "B.Tech"),
        (r"b\.?\s*e\.?(?:\s+in)\s+[a-zA-Z\s&\(\)]+", "B.E."),
        (r"bachelor\s+of\s+engineering(?:\s+in)?\s+[a-zA-Z\s&\(\)]+", "B.E."),
        (r"b\.?\s*sc\.?(?:\s+in)\s+[a-zA-Z\s&\(\)]+", "B.Sc"),
        (r"bachelor\s+of\s+science(?:\s+in)?\s+[a-zA-Z\s&\(\)]+", "B.Sc"),
        (r"\bb\.?\s*c\.?\s*a\.?\b", "BCA"),
        (r"\bm\.?\s*c\.?\s*a\.?\b", "MCA"),
        (r"m\.?\s*tech(?:\s+in)?\s+[a-zA-Z\s&\(\)]+", "M.Tech"),
    ]
    for line in lines:
        for pat, fallback_label in deg_patterns:
            m = re.search(pat, line, re.IGNORECASE)
            if m:
                extracted_deg = re.split(
                    r"[,|—–\-]|\b(?:graduate|student|with|from|at|cgpa|gpa|20\d{2}|university|institute|college)\b",
                    m.group(0),
                    flags=re.IGNORECASE
                )[0].strip()
                if len(extracted_deg) >= 3:
                    education = extracted_deg
                    break
        if education != "Not found" and " in " in education.lower():
            break
    if education == "Not found":
        if "b.tech" in text_lower or "btech" in text_lower:
            education = "B.Tech"
        elif "b.e." in text_lower or "bachelor of engineering" in text_lower:
            education = "B.E."
        elif "bca" in text_lower:
            education = "BCA"
        elif "b.sc" in text_lower or "bsc" in text_lower:
            education = "B.Sc"

    # 5. Extract Summary / Objective and Project lines from actual resume sections
    current_section = "HEADER"
    summary_lines: List[str] = []
    project_lines: List[str] = []

    for line in lines:
        sec = _is_section_heading(line)
        if sec:
            if "SUMMARY" in sec or "OBJECTIVE" in sec or "PROFILE" in sec:
                current_section = "SUMMARY"
            elif "PROJECT" in sec:
                current_section = "PROJECTS"
            elif "EXPERIENCE" in sec or "INTERNSHIP" in sec or "EMPLOYMENT" in sec:
                current_section = "EXPERIENCE"
            elif "EDUCATION" in sec or "ACADEMIC" in sec or "QUALIFICATION" in sec:
                current_section = "EDUCATION"
            elif "SKILL" in sec or "COMPETENC" in sec or "TECHNOLOG" in sec:
                current_section = "SKILLS"
            else:
                current_section = "OTHER"
            continue

        if re.match(r"^(?:career\s+)?(?:objective|summary|profile)\s*[:\-–]", line, re.IGNORECASE):
            summary_lines.append(line)
            continue

        if current_section == "SUMMARY" and len(summary_lines) < 3:
            summary_lines.append(line)
        elif current_section == "PROJECTS" and len(line) > 12:
            project_lines.append(line)

    # Fallback project line detection if no explicit PROJECTS heading was found
    if not project_lines:
        for line in lines:
            if any(line.startswith(b) for b in ["•", "-", "*"]) or re.search(r"\b(?:built|developed|engineered|designed|created|implemented|made|worked on)\b", line, re.IGNORECASE):
                if not any(k in line.lower() for k in ["intern", "university", "college", "cgpa", "b.tech", "b.e.", "email", "linkedin"]):
                    project_lines.append(line)

    # 6. Seniority heuristic
    seniority = "Fresher / Entry-Level (0–1 Years)"
    if "senior" in text_lower or "lead engineer" in text_lower or "5+ years" in text_lower:
        seniority = "Senior Professional (5+ Years)"
    elif "2+ years" in text_lower or "3+ years" in text_lower:
        seniority = "Mid-Level Professional (2–4 Years)"

    # 7. Extract categorized skills
    detected_skills = []
    all_kws: List[str] = []
    for cat, kws in KEYWORD_CATEGORIES.items():
        matched = [k for k in kws if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w|\+)", text_lower)]
        for m_kw in matched:
            if m_kw not in all_kws:
                all_kws.append(m_kw)
        if matched:
            detected_skills.append({"category": cat, "skills": matched})

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
        "education": education,
        "seniority": seniority,
        "detectedSkills": detected_skills,
        "allKeywords": all_kws,
        "headerLines": header_lines,
        "summaryLine": " ".join(summary_lines).strip() if summary_lines else "",
        "projectLines": project_lines[:5]
    }


def rank_and_score_jobs_for_resume(resume_text: str, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dynamically calculates fit score and matches skills for every job against the provided resume."""
    text_lower = resume_text.lower()
    ranked_jobs = []

    for job in jobs:
        key_skills = [s.lower() for s in job.get("keySkills", [])]
        matched = [s for s in key_skills if s in text_lower]
        missing = [s for s in key_skills if s not in text_lower]

        overlap_ratio = len(matched) / len(key_skills) if key_skills else 0.8

        score = int(overlap_ratio * 70)

        if "python" in text_lower and "python" in job.get("track", "").lower():
            score += 15
        if ("cyber" in text_lower or "security" in text_lower) and "security" in job.get("track", "").lower():
            score += 15
        if ("yolo" in text_lower or "lstm" in text_lower or "vision" in text_lower) and "vision" in job.get("track", "").lower():
            score += 15
        if "sql" in text_lower or "mysql" in text_lower:
            score += 5
        if "git" in text_lower:
            score += 5

        final_fit = max(65, min(96, score))

        if final_fit >= 90:
            category = "Apply First"
        elif final_fit >= 83:
            category = "Good Match"
        else:
            category = "Stretch"

        job_copy = dict(job)
        job_copy["fitScore"] = final_fit
        job_copy["category"] = category
        job_copy["matchedSkills"] = matched
        job_copy["missingSkills"] = missing

        if matched:
            job_copy["whyMatch"] = f"Your resume demonstrates proficiency in {', '.join(matched[:3]).title()}, closely matching this role's core technical requirements."
        if missing:
            job_copy["missingReqs"] = f"Consider highlighting or brushing up on {', '.join(missing[:2]).title()} for technical rounds."

        ranked_jobs.append(job_copy)

    ranked_jobs.sort(key=lambda x: x["fitScore"], reverse=True)
    return ranked_jobs


def _build_resume_corrections(profile: Dict[str, Any], resume_text: str) -> List[Dict[str, str]]:
    """Builds 'What to fix, and where' items directly from parsed resume text using placeholders for missing metrics/links."""
    corrections: List[Dict[str, str]] = []
    lines = [l.strip() for l in resume_text.splitlines() if l.strip()]

    name = profile.get("name", "Not found")
    email = profile.get("email", "Not found")
    phone = profile.get("phone", "Not found")
    linkedin = profile.get("linkedin", "Not found")
    github = profile.get("github", "Not found")
    education = profile.get("education", "Not found")
    all_kws = profile.get("allKeywords", [])
    header_lines = profile.get("headerLines") or lines[:2]
    summary_line = profile.get("summaryLine", "")
    project_lines = profile.get("projectLines", [])

    has_email = email != "Not found"
    has_phone = phone != "Not found"
    has_linkedin = linkedin != "Not found"
    has_github = github != "Not found"

    # 1. Contact Header Fix (only if email, phone, LinkedIn, or GitHub is missing)
    if not (has_email and has_phone and has_linkedin and has_github):
        missing_parts = []
        if not has_email:
            missing_parts.append("email")
        if not has_phone:
            missing_parts.append("phone number")
        if not has_linkedin:
            missing_parts.append("LinkedIn URL")
        if not has_github:
            missing_parts.append("GitHub URL")

        before_header = "\n".join(header_lines) if header_lines else (lines[0] if lines else "[Resume Header]")
        clean_name = name if name != "Not found" else "[Your Full Name]"
        clean_email = email if has_email else "[your.email@domain.com]"
        clean_phone = phone if has_phone else "[+91 XXXXX XXXXX]"
        clean_linkedin = linkedin if has_linkedin else "linkedin.com/in/[your-username]"
        clean_github = github if has_github else "github.com/[your-username]"

        after_header = f"{clean_name}\n{clean_email}  |  {clean_phone}\n{clean_linkedin}  |  {clean_github}"
        corrections.append({
            "section": "Contact Header",
            "icon": "📌",
            "status": "critical",
            "before": before_header,
            "after": after_header,
            "tip": f"We detected your header but could not find your {', '.join(missing_parts)}. Keep your real contact details and replace the [brackets] with your real profile links."
        })

    # 2. Professional Summary Fix (built only from actual extracted degree, skills, and project title)
    first_proj_title = ""
    if project_lines:
        raw_p = re.sub(r"^[•\-\*\d\.\s]+", "", project_lines[0]).strip()
        first_proj_title = re.split(r"[:|—–\-]", raw_p)[0].strip()
        if len(first_proj_title) > 45:
            first_proj_title = " ".join(first_proj_title.split()[:5])

    top_skills = [s.upper() if s in ("sql", "c", "aws", "soc", "siem", "vapt", "lstm", "yolo", "html", "css", "rest api") else s.title() for s in all_kws[:4]]
    has_enough_summary_data = (education != "Not found") and (len(top_skills) >= 2)

    if has_enough_summary_data:
        proj_clause = f", demonstrated through building {first_proj_title}" if first_proj_title else ""
        suggested_summary = (
            f"{education} graduate with hands-on experience in {', '.join(top_skills)}{proj_clause}. "
            f"Seeking an entry-level [target role] position to deliver reliable software solutions."
        )
    else:
        deg_part = education if education != "Not found" else "[Your Degree & Specialization]"
        skills_part = ", ".join(top_skills) if top_skills else "[your top 3–4 technical skills]"
        proj_part = first_proj_title if first_proj_title else "[your key project name]"
        suggested_summary = (
            f"{deg_part} graduate with hands-on experience in {skills_part}, "
            f"demonstrated by building {proj_part}. Seeking an entry-level [target role] role."
        )

    before_summary = summary_line if summary_line else (
        f"[No summary section found — top of resume starts with: \"{lines[0] if lines else ''}\"]"
    )
    corrections.append({
        "section": "Professional Summary",
        "icon": "🎯",
        "status": "suggested",
        "before": before_summary,
        "after": suggested_summary,
        "tip": "Summarize your actual degree, core skills, and flagship project in 2 lines tailored to your [target role]."
    })

    # 3. Projects Fix (uses real project line from the resume and placeholder metrics)
    target_proj_line = ""
    for pl in project_lines:
        if not re.search(r"(\d+%|\d+k\+|\d+\+?\s*(?:seconds|ms|records|users|trainees|hours))", pl.lower()):
            target_proj_line = pl
            break
    if not target_proj_line and project_lines:
        target_proj_line = project_lines[0]

    if target_proj_line:
        clean_pl = re.sub(r"^[•\-\*\d\.\s]+", "", target_proj_line).strip()
        line_skills = [
            (s.upper() if s in ("sql", "c", "c++", "aws", "lstm", "yolo", "html", "css", "rest api") else s.title())
            for s in all_kws
            if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w|\+)", clean_pl.lower())
        ]
        tech_used = ", ".join(line_skills[:3]) if line_skills else (", ".join(top_skills[:3]) if top_skills else "[tech stack from your project]")
        what_built = first_proj_title if first_proj_title else "[project / feature name]"
        after_proj = (
            f"Built {what_built} using {tech_used}, achieving [X% accuracy / latency improvement] "
            f"across [number of users or records]."
        )
        corrections.append({
            "section": "Projects — Add Numbers & Scale",
            "icon": "🏗️",
            "status": "suggested",
            "before": target_proj_line,
            "after": after_proj,
            "tip": "Pair what you built and the real tools you used with measurable outcomes in [brackets]."
        })
    else:
        tech_used = ", ".join(top_skills[:3]) if top_skills else "[tech stack used]"
        corrections.append({
            "section": "Projects — Add Numbers & Scale",
            "icon": "🏗️",
            "status": "critical",
            "before": "[No project bullet points detected in resume]",
            "after": f"Built [what you built] using {tech_used}, achieving [X% result] for [number of users or records].",
            "tip": "Add 2–3 academic or personal projects showing what you built, what tools you used, and the measurable result."
        })

    return corrections


def calculate_deterministic_ats_score(
    raw_text: str,
    email: str = "Not found",
    phone: str = "Not found",
    linkedin: str = "Not found",
    github: str = "Not found",
    is_scanned_pdf: bool = False
) -> Dict[str, Any]:
    """Calculates the identical 100-point deterministic ATS score as Next.js fresherlaunch rubric."""
    text_lower = raw_text.lower()

    # 1. FORMATTING & STRUCTURE (Max: 25)
    formatting_score = 25
    formatting_details = []
    if is_scanned_pdf or len(raw_text.strip()) < 50:
        formatting_score = 5
        formatting_details.append('CRITICAL: Scanned or unreadable document detected. ATS cannot parse bitmap images.')
    else:
        non_printable = len(re.findall(r'[^\x20-\x7E\t\r\n]', raw_text))
        if non_printable > 30:
            formatting_score -= 5
            formatting_details.append('Encoding artifacts detected; potential multi-column or embedded shape table.')
        else:
            formatting_details.append('Clean plain-text encoding; easily parsable by ATS tokenizers.')

        lines = [l for l in raw_text.split('\n') if l.strip()]
        if len(lines) > 15:
            formatting_details.append('Well-structured line breaks and distinct paragraphs.')
        else:
            formatting_score -= 4
            formatting_details.append('Text appears collapsed without clear vertical spacing.')

        has_bullets = bool(re.search(r'(?:^|\n)\s*[-•*▪]\s+', raw_text) or '•' in raw_text)
        if has_bullets:
            formatting_details.append('Standard bullet points utilized for project and experience logs.')
        else:
            formatting_score -= 5
            formatting_details.append('Missing explicit bullet point delimiters (- or •).')

        detected_bad = [p for p in OUTDATED_ATS_PATTERNS if p in text_lower]
        for p in detected_bad:
            formatting_score -= 2
            formatting_details.append(f'Outdated pattern detected: "{p}".')

        if not detected_bad:
            formatting_details.append('Zero outdated resume filler phrases or personal demographic tags.')

    formatting_score = max(0, min(25, formatting_score))

    # 2. KEYWORDS & SKILLS (Max: 25)
    matched_kws = []
    for kw in TECH_KEYWORDS_DICTIONARY:
        if kw == 'c++':
            if re.search(r'\bc\+\+', text_lower):
                matched_kws.append(kw)
        else:
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                matched_kws.append(kw)
    matched_count = len(matched_kws)
    if matched_count >= 14:
        keywords_score = 25
    elif matched_count >= 10:
        keywords_score = 21
    elif matched_count >= 7:
        keywords_score = 17
    elif matched_count >= 4:
        keywords_score = 12
    else:
        keywords_score = 6
    keywords_score = max(0, min(25, keywords_score))

    # 3. ESSENTIAL SECTIONS (Max: 15)
    section_checklist = [
        ('Education', r'\b(education|academic|b\.tech|bachelor|university|college|cgpa|gpa)\b', 3),
        ('Skills', r'\b(skills|technical skills|technologies|proficiencies|tools)\b', 3),
        ('Projects', r'\b(projects|academic projects|technical projects|personal projects)\b', 3),
        ('Experience / Training', r'\b(experience|internship|training|work experience|employment|leadership)\b', 3),
        ('Summary or Contact', r'\b(summary|profile|about|contact|email|phone)\b', 3)
    ]
    sections_score = 0
    sections_found = []
    sections_missing = []
    for name, pattern, weight in section_checklist:
        if re.search(pattern, text_lower):
            sections_score += weight
            sections_found.append(name)
        else:
            sections_missing.append(name)
    sections_score = max(0, min(15, sections_score))

    # 4. ACTION VERBS & METRICS (Max: 15)
    found_verbs = [v for v in STRONG_ACTION_VERBS if v in text_lower]
    metric_matches = re.findall(r'\b(?:\d+%\s*|\d+k\+|\d+\+?\s*(?:seconds|ms|records|users|trainees|hours|leads|queries))\b', raw_text, re.IGNORECASE)
    verbs_count = len(found_verbs)
    metrics_count = len(metric_matches)

    action_score = 0
    if verbs_count >= 6: action_score += 8
    elif verbs_count >= 4: action_score += 6
    elif verbs_count >= 2: action_score += 4
    else: action_score += 2

    if metrics_count >= 3: action_score += 7
    elif metrics_count >= 2: action_score += 5
    elif metrics_count == 1: action_score += 3

    action_score = max(0, min(15, action_score))

    # 5. LENGTH & DENSITY (Max: 10)
    word_count = len(raw_text.split())
    if 350 <= word_count <= 750:
        length_score = 10
        length_verdict = 'Perfect (350–750 words)'
    elif (250 <= word_count < 350) or (750 < word_count <= 900):
        length_score = 7
        length_verdict = 'Slightly Brief' if word_count < 350 else 'Approaching 2-Page Limit'
    elif word_count < 250:
        length_score = 4
        length_verdict = 'Too Short (< 250 words)'
    else:
        length_score = 4
        length_verdict = 'Too Long (> 900 words)'

    # 6. CONTACT & PROFESSIONAL LINKS (Max: 10)
    contact_score = 0.0
    has_email = bool(email and email != 'Not detected' and email != 'Not found')
    has_phone = bool(phone and phone != 'Not detected' and phone != 'Not found')
    has_linkedin = bool((linkedin and linkedin != 'Not found') or 'linkedin.com' in text_lower)
    has_github = bool((github and github != 'Not found') or 'github.com' in text_lower)

    if has_email: contact_score += 2.5
    if has_phone: contact_score += 2.5
    if has_linkedin: contact_score += 2.5
    if has_github: contact_score += 2.5
    contact_score = max(0.0, min(10.0, contact_score))

    total = round(formatting_score + keywords_score + sections_score + action_score + length_score + contact_score)
    final_score = min(100, max(0, total))

    return {
        "totalScore": final_score,
        "formatting": {"score": formatting_score, "max": 25, "details": formatting_details},
        "keywords": {"score": keywords_score, "max": 25, "matchedCount": matched_count, "matchedKeywords": matched_kws},
        "sections": {"score": sections_score, "max": 15, "found": sections_found, "missing": sections_missing},
        "actionVerbsAndMetrics": {"score": action_score, "max": 15, "verbsCount": verbs_count, "metricsCount": metrics_count},
        "length": {"score": length_score, "max": 10, "wordCount": word_count, "verdict": length_verdict},
        "contactAndLinks": {"score": contact_score, "max": 10, "hasEmail": has_email, "hasPhone": has_phone, "hasLinkedIn": has_linkedin, "hasGitHub": has_github}
    }


def audit_resume_text(resume_text: str) -> Dict[str, Any]:
    """Performs deep ATS scoring, keyword detection, flaw analysis, and builds real-resume corrections."""
    profile = parse_candidate_profile(resume_text)
    text_lower = resume_text.lower()
    total_words = len(resume_text.split())

    # 1. Negative patterns & template flaws
    detected_flaws = []
    for pat, desc in NEGATIVE_PATTERNS:
        if re.search(pat, text_lower):
            detected_flaws.append(desc)

    # 2. Contact details detection (shared with parse_candidate_profile so audit and fixes never disagree)
    has_email = profile["email"] != "Not found"
    has_phone = profile["phone"] != "Not found"
    has_github = profile["github"] != "Not found"
    has_linkedin = profile["linkedin"] != "Not found"

    # 3. Action verbs detection
    found_verbs = [v for v in STRONG_ACTION_VERBS if re.search(r"\b" + re.escape(v) + r"\b", text_lower)]

    # 4. Quantified metrics detection (% numbers, hours, reductions)
    metric_matches = re.findall(r"(\d+%\s*|\d+k\+|\d+\+?\s*(seconds|ms|records|users|trainees|hours))", text_lower)
    quantified_count = len(metric_matches)

    # 5. Keywords detection across categories
    found_keywords = {}
    for cat, kws in KEYWORD_CATEGORIES.items():
        matched = [k for k in kws if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w|\+)", text_lower)]
        found_keywords[cat] = matched

    # Base ATS Score calculation using the single source of truth 100-point rubric
    scoring_result = calculate_deterministic_ats_score(
        resume_text,
        profile["email"],
        profile["phone"],
        profile["linkedin"],
        profile["github"]
    )
    final_ats_score = scoring_result["totalScore"]

    # Recommendations (no invented metrics)
    recommendations = []
    if detected_flaws:
        recommendations.append(f"Remove {len(detected_flaws)} critical formatting flaws/residual template numbers.")
    if quantified_count < 3:
        recommendations.append("Add numbers to your projects: how many users, records, or [X%] faster?")
    if not has_linkedin:
        recommendations.append("Include your LinkedIn profile link (linkedin.com/in/[your-username]) in the resume header.")
    if not has_github:
        recommendations.append("Include your GitHub profile link (github.com/[your-username]) so recruiters can review your code.")
    if "docker" not in text_lower:
        recommendations.append("If you have used Docker or containers, list them in your skills section.")

    corrections = _build_resume_corrections(profile, resume_text)

    return {
        "atsScore": final_ats_score,
        "scoreBreakdown": scoring_result,
        "wordCount": total_words,
        "contactDetails": {
            "hasEmail": has_email,
            "hasPhone": has_phone,
            "hasGithub": has_github,
            "hasGitHub": has_github,
            "hasLinkedin": has_linkedin,
            "hasLinkedIn": has_linkedin,
            "email": profile["email"],
            "phone": profile["phone"],
            "linkedin": profile["linkedin"],
            "github": profile["github"]
        },
        "detectedFlaws": detected_flaws,
        "actionVerbsFound": found_verbs,
        "quantifiedMetricsCount": quantified_count,
        "keywordsFound": found_keywords,
        "recommendations": recommendations,
        "corrections": corrections
    }


def compare_resume_with_job(resume_text: str, job_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Compares resume text against a target job requirements and returns match details."""
    text_lower = resume_text.lower()
    
    key_skills = [s.lower() for s in job_dict.get("keySkills", [])]
    matched_skills = [s for s in key_skills if s in text_lower]
    missing_skills = [s for s in key_skills if s not in text_lower]
    
    match_percentage = int((len(matched_skills) / len(key_skills) * 100)) if key_skills else 80
    
    return {
        "jobId": job_dict.get("id"),
        "jobTitle": job_dict.get("title"),
        "company": job_dict.get("company"),
        "matchedSkills": matched_skills,
        "missingSkills": missing_skills,
        "matchPercentage": match_percentage,
        "whyMatch": job_dict.get("whyMatch", ""),
        "missingReqs": job_dict.get("missingReqs", "")
    }

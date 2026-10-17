from typing import Dict, Any

def generate_personalized_outreach(
    candidate_name: str,
    candidate_phone: str,
    candidate_email: str,
    portfolio_url: str,
    company: str,
    role: str,
    recruiter_name: str = "Hiring Team",
    project_focus: str = "Deep Traffic-VTS (LSTM + YOLO) and Python Automation"
) -> Dict[str, str]:
    """
    Generates high-conversion LinkedIn connection notes (<300 chars) and 
    comprehensive InMail/Email drafts customized for the company and role.
    """
    first_name = candidate_name.split()[0] if candidate_name else "Candidate"
    recruiter_display = recruiter_name if recruiter_name.strip() else "Recruiter"
    
    # 1. Short LinkedIn Connection Note (<300 chars strictly)
    short_note = (
        f"Hi {recruiter_display}, I'm {first_name}, final-year B.Tech CSE (Cyber Security) at GNIT (73%). "
        f"Skilled in Python, SQL & ML algorithms, I'm eager to contribute to {company}'s {role} team. "
        f"Would love to connect!"
    )
    if len(short_note) > 298:
        short_note = (
            f"Hi {recruiter_display}, I'm {first_name}, final-year B.Tech CSE at GNIT (73%). "
            f"Proficient in Python, SQL & ML, I'm passionate about {company}'s {role} role. "
            f"Looking forward to connecting!"
        )

    # 2. Comprehensive InMail / Direct Email
    full_email = f"""Subject: Application: {role} - {candidate_name} (2025/2026 Batch)

Dear {recruiter_display},

I hope this message finds you well.

I am writing to express my strong enthusiasm for the {role} opportunity at {company}. I am currently in my final year of B.Tech in Computer Science & Engineering (Cyber Security) at Guru Nanak Institute of Technology, Hyderabad, graduating with a 73% aggregate and zero backlogs.

Key qualifications I bring to {company}:
1. Robust Core Programming: Extensive hands-on experience in Python, OOP principles, Relational Databases (MySQL/PostgreSQL), and RESTful API development.
2. Machine Learning & Automation: Developed {project_focus}, combining computer vision and predictive sequential modeling, alongside automated data preparation scripts that eliminated 50% of manual turnaround time.
3. Leadership & Communication: Served as Team Lead at Dexterity Pvt Ltd, coordinating trainee cohorts and presenting metrics dashboards to executive leadership.

I have submitted my application via your official careers portal and would welcome the opportunity to discuss how my technical toolkit can contribute to {company}'s engineering initiatives.

Portfolio: {portfolio_url}
Phone: {candidate_phone}
Email: {candidate_email}

Thank you for your time and consideration.

Warm regards,
{candidate_name}
Hyderabad, India"""

    return {
        "company": company,
        "role": role,
        "recruiter": recruiter_display,
        "connectionNote": short_note,
        "connectionNoteLength": len(short_note),
        "inMailMessage": full_email
    }

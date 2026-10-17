from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class StatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Status string: 'saved', 'applied', 'interviewing', 'offers', or 'none'")

class NoteUpdateRequest(BaseModel):
    note: str

class CustomOutreachRequest(BaseModel):
    company: str
    role: str
    recruiterName: Optional[str] = "Hiring Team"
    projectFocus: Optional[str] = "Deep Traffic-VTS (LSTM + YOLO) and Python Automation"

class JobDescriptionAuditRequest(BaseModel):
    jobDescription: str
    jobTitle: Optional[str] = "Target Role"

"""Pydantic Structured Output Schemas for LLM Classification.

Enforces strict enum values for:
- 12 role categories
- 11 standardized Indian cities
- 5 job types
- 3-class fresher eligibility ('fresher_friendly', 'not_fresher_friendly', 'uncertain')
- Model self-reported confidence between 0.0 and 1.0
"""
from typing import List, Literal
from pydantic import BaseModel, Field


RoleCategoryType = Literal[
    "Frontend", "Backend", "Full Stack", "Mobile",
    "Data & Analytics", "AI / ML", "DevOps & Cloud",
    "QA & Testing", "Cybersecurity", "Product & Design",
    "Other Tech", "Non-Tech"
]

CityType = Literal[
    "Bengaluru", "Hyderabad", "Pune", "Mumbai",
    "Delhi-NCR", "Chennai", "Kolkata", "Ahmedabad",
    "Remote", "Other India", "Unknown"
]

JobTypeLiteral = Literal[
    "Full-Time", "Internship", "Contract", "Part-Time", "Unknown"
]

FresherEligibilityType = Literal[
    "fresher_friendly", "not_fresher_friendly", "uncertain"
]


class ClassifiedJobItem(BaseModel):
    """Pydantic model validating individual job classification from LLM output."""
    job_id: int
    role_category: RoleCategoryType = Field(
        description="One of: Frontend, Backend, Full Stack, Mobile, Data & Analytics, AI / ML, DevOps & Cloud, QA & Testing, Cybersecurity, Product & Design, Other Tech, Non-Tech"
    )
    standardized_city: CityType = Field(
        description="One of: Bengaluru, Hyderabad, Pune, Mumbai, Delhi-NCR, Chennai, Kolkata, Ahmedabad, Remote, Other India, Unknown"
    )
    job_type: JobTypeLiteral = Field(
        description="One of: Full-Time, Internship, Contract, Part-Time, Unknown"
    )
    fresher_eligibility: FresherEligibilityType = Field(
        description="'fresher_friendly' (0-1 yrs exp / interns), 'not_fresher_friendly' (2+ yrs exp), or 'uncertain' (unclear/unstated)"
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Uncalibrated model self-reported confidence score between 0.0 and 1.0"
    )
    reasoning: str = Field(
        description="Concise 1-sentence explanation citing explicit keywords from title, company, or snippet"
    )


class BatchClassificationResponse(BaseModel):
    """Root container model for Gemini structured JSON response."""
    classifications: List[ClassifiedJobItem]

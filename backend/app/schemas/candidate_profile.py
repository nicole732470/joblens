"""Candidate profile — durable job-search intent (separate from resume text)."""

from pydantic import BaseModel, Field


class Track(BaseModel):
    id: str
    label: str
    priority: int = Field(ge=1, le=5, description="1 = most wanted, 5 = last resort")
    example_titles: list[str] = []


class AvoidTrack(BaseModel):
    id: str
    label: str
    example_titles: list[str] = []


class Locations(BaseModel):
    summary: str = ""
    tier_1: list[str] = []
    tier_2: list[str] = []
    tier_3: list[str] = []
    remote_ok: bool = True
    relocation_ok: bool = True


class Constraints(BaseModel):
    needs_sponsorship: bool = True


class CandidateProfile(BaseModel):
    tracks: list[Track] = []
    avoid_tracks: list[AvoidTrack] = []
    locations: Locations = Field(default_factory=Locations)
    trajectory: list[str] = []
    dealbreakers: list[str] = []
    preferences: list[str] = []
    # JD domains you cannot do — bump Role P-tier when responsibilities mention these.
    technical_penalties: list[str] = []
    # Schools to match against LinkedIn «X alumni work here» (page text from extension).
    alumni_schools: list[str] = []
    constraints: Constraints = Field(default_factory=Constraints)

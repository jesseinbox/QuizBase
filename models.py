from pydantic import BaseModel
from typing import Optional


class CourseCreate(BaseModel):
    name: str


class TopicCreate(BaseModel):
    name: str


class FactCreate(BaseModel):
    content: str
    course_id: Optional[int] = None


class FactUpdate(BaseModel):
    content: str
    course_id: Optional[int] = None

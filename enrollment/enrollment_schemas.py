from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings, env_file=".env", extra="ignore"):
    enrollment_database: str
    enrollment_logging_config: str

class Instructor(BaseModel):
    id: int
    name: str

class Student(BaseModel):
    id: int
    name: str

class Waitlist_Student(BaseModel):
    class_id: int
    waitlist_position: int

class Waitlist_Instructor(BaseModel):
    student: Student
    waitlist_position: int

class Waitlist_Info(BaseModel):
    class_id: int
    students: List[Waitlist_Instructor]

class Class(BaseModel):
    id: int
    name: str
    course_code: str
    section_number: int
    current_enroll: int
    max_enroll: int
    department: str
    instructor_id: int
    enrolled: List[int]
    dropped: List[int]

class Class_SQL(BaseModel):
    name: str
    course_code: str
    section_number: int
    current_enroll: int
    max_enroll: int
    department_id: int

class Enroll(BaseModel):
    placement: int
    class_id: int
    student_id: int

class User_info(BaseModel):
    id: int
    name: str
    roles: List

class Create_User(BaseModel):
    name: str
    roles: List

class Class_Enroll(BaseModel):
    id: int
    name: str
    course_code: str
    section_number: int
    current_enroll: int
    max_enroll: int
    department: str
    instructor: Instructor
    current_waitlist: int
    max_waitlist: int

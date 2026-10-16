from dataclasses import dataclass, field


@dataclass
class StudentRecord:
    student_no: str
    chinese_name: str
    english_name: str
    class_name: str
    course_code: str
    course_name: str = ''
    programme: str = ''
    teachers: str = ''
    source: str = ''
    raw_name: str = ''
    issues: list[str] = field(default_factory=list)
    teaching_code: str = ''
    academic_year: str = ''
    semester: str = ''
    programme_code: str = ''
    grade: int | None = None
    administrative_class: str = ''


@dataclass
class Candidate:
    sheet: str
    class_name: str
    records: list[StudentRecord]
    recommended: bool = False


class ValidationError(ValueError):
    """An actionable business validation failure, safe to show in the UI."""


class CapacityError(ValidationError):
    def __init__(self, remaining, requested):
        self.remaining = remaining
        self.requested = requested
        super().__init__(f'此考場剩餘 {remaining} 個座位，無法容納整個班級（{requested} 人）。')

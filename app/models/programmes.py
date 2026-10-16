from dataclasses import dataclass
import re

FACULTY = '金融學院'
PROGRAMMES = {
    'BAECF': ('應用經濟學學士學位課程 (中文學制)',
              'Bachelor of Applied Economics Programme (Chinese)'),
}
DEFAULT_PROGRAMME = 'BAECF'
SEMESTERS = {'1': '第一學期', '2': '第二學期', '3': '第三學期'}


@dataclass(frozen=True)
class TeachingCode:
    value: str
    academic_year: str
    semester: str
    programme_code: str
    grade: int
    class_name: str
    course_code: str


def parse_teaching_code(value, course_hint=''):
    value = str(value or '').strip().upper()
    subject = re.escape(course_hint.upper()) if course_hint else r'[A-Z]{3}\d{3}'
    match = re.fullmatch(r'(\d{2})([123])([A-Z]+)(\d{1,2})([A-Z]+?)(' + subject + r')(\d{2})', value)
    if not match:
        return None
    year, semester, programme, grade, group, subject, _ = match.groups()
    start = 2000 + int(year)
    return TeachingCode(value, f'{start}–{start+1}', SEMESTERS[semester], programme,
                        int(grade), f'{int(grade)}{group}', subject)


def programme_values(code=DEFAULT_PROGRAMME):
    cn, en = PROGRAMMES[code]
    return {'programme': cn, 'programme_en': en, 'language': '中文'}

"""Offline parser for copied Excel/Word/HTML course tables."""
import csv
import io
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from app.models.programmes import DEFAULT_PROGRAMME, programme_values
from app.models.records import ValidationError

CODE = re.compile(r'\b[A-Z]{2,6}\d{3,4}\b', re.I)


@dataclass
class CoursePreview:
    values: dict
    issues: list[str] = field(default_factory=list)


class TableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[];self.row=[];self.cell=None

    def handle_starttag(self, tag, attrs):
        if tag=='tr':self.row=[]
        elif tag in ('td','th'):self.cell=[]
        elif tag in ('br','p','div') and self.cell is not None:self.cell.append('\n')

    def handle_data(self, data):
        if self.cell is not None:self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip());self.cell=None
        elif tag=='tr' and self.row:self.rows.append(self.row);self.row=[]


def bilingual(value):
    value=value.strip()
    match=re.search(r'[A-Za-z]',value)
    if match:
        cn=value[:match.start()].strip()
        en=' '.join(value[match.start():].split())
        # Do not guess when Chinese appears after the proposed English boundary.
        if re.search(r'[\u3400-\u9fff]',en):return value,'',['中英文科名分界不明，請人工修正']
        return cn,en,[]
    return value,'',[]


def parse_courses(text, html='', programme_code=DEFAULT_PROGRAMME):
    rows=[]
    if html:
        parser=TableHTML();parser.feed(html);rows=parser.rows
    if not rows:
        rows=list(csv.reader(io.StringIO(text),delimiter='\t'))
    if not any(any(CODE.search(c) for c in row) for row in rows):
        raise ValidationError('找不到科目編號。請複製包含「課程、科目編號、中英文科名、教師」的表格。')
    result=[]
    for row in rows:
        if not any(c.strip() for c in row):continue
        code_index=next((i for i,c in enumerate(row) if CODE.search(c)),None)
        if code_index is None:
            if any(x in ''.join(row) for x in ('科目','課程','教師','Course','Instructor')):continue
            # A plain-text continuation has no safe column attribution.
            result.append(CoursePreview(dict(programme_values(programme_code),code='',name_cn=' '.join(row),name_en='',teachers=''),
                                        ['此列缺少科目編號或表格換行不明，請人工確認']))
            continue
        codes=[m.group().upper() for m in CODE.finditer(row[code_index])]
        after=row[code_index+1:]
        issues=[]
        if len(after)==2:
            cn,en,name_issues=bilingual(after[0]);teachers=after[1].strip();issues+=name_issues
        elif len(after)==3:
            cn,en,teachers=[x.strip() for x in after]
        else:
            cn,en,name_issues=bilingual(after[0] if after else '')
            teachers='';issues+=name_issues+['欄位數目不明，請核對科名與教師']
        if not cn:issues.append('中文科名缺失')
        if not en:issues.append('英文科名缺失')
        if not teachers:issues.append('教師缺失')
        if len(codes)>1:issues.append('同列有多個科目編號，已分開列出，請確認是否共用科名及教師')
        if len(codes)!=len(set(codes)):issues.append('同列科目編號重複')
        for code in dict.fromkeys(codes):
            result.append(CoursePreview(dict(programme_values(programme_code),code=code,name_cn=cn,name_en=en,
                                             teachers=' '.join(teachers.split())),list(issues)))
    counts={}
    for r in result:counts[r.values['code']]=counts.get(r.values['code'],0)+1
    for r in result:
        if r.values['code'] and counts[r.values['code']]>1:r.issues.append('貼上內容有重複科目，請刪除多餘列')
    return result

"""Parse copied room/capacity tables without guessing conflicting capacities."""
import csv
import io
import re
from dataclasses import dataclass, field
from app.importers.courses import TableHTML
from app.models.records import ValidationError


@dataclass
class RoomPreview:
    name: str
    capacity: str
    issues: list[str] = field(default_factory=list)


def parse_rooms(text, html=''):
    rows=[]
    if html:
        parser=TableHTML();parser.feed(html);rows=parser.rows
    if not rows:
        for line in text.splitlines():
            line=line.strip()
            if not line:continue
            if '|' in line:row=[c.strip() for c in line.strip('|').split('|')]
            elif '\t' in line:row=next(csv.reader(io.StringIO(line),delimiter='\t'))
            elif ',' in line:row=next(csv.reader(io.StringIO(line)))
            else:row=re.split(r'\s+(?=\d+\s*$)',line,maxsplit=1)
            rows.append(row)
    result=[];seen=set();by_name={}
    for row in rows:
        row=[str(c).strip() for c in row]
        if not any(row):continue
        if all(re.fullmatch(r'[:\-\s]*',c) for c in row):continue
        if len(row)>=2 and row[0].lower() in ('考場','考場名稱','名稱','room','venue') and not row[1].isdigit():continue
        name=(row[0] if row else '').upper()
        capacity=row[1] if len(row)>1 else ''
        key=(name,capacity)
        if key in seen:continue
        seen.add(key)
        issues=[]
        if not name:issues.append('缺少考場名稱')
        if len(row)!=2:issues.append('需為考場名稱、最多人數兩欄')
        if not capacity.isascii() or not capacity.isdigit() or int(capacity)<=0:
            issues.append('最多人數須為正整數')
        entry=RoomPreview(name,capacity,issues)
        if name in by_name:
            for old in by_name[name]:
                if '同一考場有不同容量，請核對並保留一列' not in old.issues:
                    old.issues.append('同一考場有不同容量，請核對並保留一列')
            entry.issues.append('同一考場有不同容量，請核對並保留一列')
        by_name.setdefault(name,[]).append(entry);result.append(entry)
    if not result:raise ValidationError('找不到考場資料，請貼上「考場名稱、最多人數」兩欄表格。')
    return result

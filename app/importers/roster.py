import re
from collections import Counter
from pathlib import Path
from openpyxl import load_workbook
from app.models.records import Candidate, StudentRecord, ValidationError


def split_name(raw):
    """Conservative CJK/Latin split; retain the original and flag ambiguities."""
    raw = str(raw or '').strip()
    if not raw:
        return '', '', ['姓名缺失']
    cjk = r'[\u3400-\u9fff\uf900-\ufaff·・]+'
    latin = r"[A-Za-zÀ-ž][A-Za-zÀ-ž\s\-'’.]*"
    if re.fullmatch(cjk, raw):
        return raw, '', []
    if re.fullmatch(latin, raw):
        return '', raw, []
    m = re.fullmatch(f'({cjk})\\s+({latin})', raw)
    if m:
        return m[1], ' '.join(m[2].split()), []
    m = re.fullmatch(f'({latin})\\s+({cjk})', raw)
    if m:
        return m[2], ' '.join(m[1].split()), []
    return raw, '', ['姓名需要人工確認（已保留原文）']


def cell_text(cell):
    if cell.data_type == 'f':
        return '', ['欄位包含公式，請以文字值提供']
    value = cell.value
    if value is None:
        return '', []
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            return str(value), ['學號含非整數值，需要人工確認']
        text = str(int(value))
        if re.fullmatch('0+', cell.number_format):
            text = text.zfill(len(cell.number_format))
        elif abs(value) >= 10**15:
            return text, ['數值學號可能已失去精度，需要人工確認']
        return text, []
    return str(value).strip(), []


ALIASES = {
    'id': {'帳號', '学号', '學號', 'studentid', 'studentno', 'id'},
    'cn': {'姓名', '中文姓名', 'chinesename', 'name'},
    'en': {'英文姓名', 'englishname'},
    'class': {'班級', '班级', 'class'},
    'code': {'科目代碼', '科目代码', 'coursecode'},
    'course': {'科目名稱', '科目名称', 'coursename'},
}


def norm(v):
    return re.sub(r'[\s._]', '', str(v or '')).lower()


def inspect_roster(path):
    path = Path(path)
    if path.suffix.lower() != '.xlsx':
        raise ValidationError('只接受 .xlsx 名單；不會執行巨集或外部連結。')
    try:
        wb = load_workbook(path, data_only=False, keep_links=False)
    except Exception as exc:
        raise ValidationError('無法開啟 Excel，請確認檔案未損壞或加密。') from exc
    candidates = []
    try:
        for sheet in wb:
            columns, header = {}, None
            for row in sheet.iter_rows(max_row=min(sheet.max_row, 50)):
                mapping = {}
                for cell in row:
                    for key, aliases in ALIASES.items():
                        if norm(cell.value) in aliases:
                            mapping[key] = cell.column
                if 'id' in mapping and ('cn' in mapping or 'en' in mapping):
                    columns, header = mapping, row[0].row
                    break
            if header is None:
                continue
            meta = {}
            for row in sheet.iter_rows(max_row=header-1):
                for i, cell in enumerate(row[:-1]):
                    if cell.value in ('科目名稱', '教務科目代碼', '授課老師', '課程'):
                        meta[str(cell.value)] = str(row[i+1].value or '').strip()
            title = meta.get('科目名稱', '')
            match = re.search(r'([A-Za-z]{2,}\d{2,})-([A-Za-z0-9]+)\s*$', title)
            code = meta.get('教務科目代碼', '') or (match[1] if match else '')
            course_name = title[:match.start()].rstrip(' -') if match else title
            grouped = {}
            for row in sheet.iter_rows(min_row=header+1):
                idcell = row[columns['id']-1]
                raw_id = str(idcell.value or '')
                if '教師簽字' in raw_id or '教师签字' in raw_id:
                    continue
                def val(key):
                    return str(row[columns[key]-1].value or '').strip() if key in columns else ''
                if not any(val(k) for k in ['id', 'cn', 'en', 'class']):
                    continue
                sid, issues = cell_text(idcell)
                cn, en = val('cn'), val('en')
                raw = '\n'.join(filter(None, [cn, en]))
                if not en:
                    cn, en, name_issues = split_name(cn)
                    issues += name_issues
                elif not cn:
                    issues.append('中文姓名缺失，需要人工確認')
                if not sid or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', sid):
                    issues.append('空白或錯誤學號')
                cls = val('class') or (sheet.title if sheet.title not in ('匯總', '汇总', 'Summary') else '')
                record = StudentRecord(sid, cn, en, cls, val('code') or code,
                                       val('course') or course_name, meta.get('課程', ''),
                                       meta.get('授課老師', ''), path.name, raw, issues)
                if not record.course_code:
                    issues.append('科目代碼缺失（可在預覽填寫）')
                if not cls:
                    issues.append('班級缺失（可在預覽填寫）')
                grouped.setdefault(cls, []).append(record)
            for cls, records in grouped.items():
                counts = Counter(r.student_no for r in records)
                for rec in records:
                    if counts[rec.student_no] > 1:
                        rec.issues.append('同 Sheet 重複學號，需要人工確認')
                candidates.append(Candidate(sheet.title, cls, records))
        independent = {c.class_name for c in candidates if c.sheet == c.class_name}
        hint = re.search(r'(?:\d|[-_])([A-Za-z])$', path.stem)
        for c in candidates:
            eligible = c.sheet == c.class_name or c.class_name not in independent
            c.recommended = eligible and (not hint or c.class_name.upper() == hint[1].upper())
        if not candidates:
            raise ValidationError('找不到學號與姓名表頭，請使用「帳號／學號、姓名、英文姓名、班級」欄位。')
        return candidates
    finally:
        wb.close()

import re
from collections import Counter
from pathlib import Path
from openpyxl import load_workbook
from app.models.records import Candidate, StudentRecord, ValidationError
from app.models.programmes import parse_teaching_code, PROGRAMMES


def split_name(raw):
    """Conservative CJK/Latin split; retain the original and flag ambiguities."""
    raw = str(raw or '').strip()
    if not raw:
        return '', '', ['姓名缺失']
    # Some original rosters prefix the Chinese name with a nationality.
    han = r'[\u3400-\u9fff\uf900-\ufaff·・]+'
    cjk = rf'(?:[（(]{han}[）)]\s*)?{han}'
    latin = r"[A-Za-zÀ-ž][A-Za-zÀ-ž\u0300-\u036f\s\-'’.]*"
    if re.fullmatch(cjk, raw):
        return raw, '', []
    if re.fullmatch(latin, raw):
        return '', raw, []
    m = re.fullmatch(f'({cjk})\\s*({latin})', raw)
    if m:
        return m[1], ' '.join(m[2].split()), []
    m = re.fullmatch(f'({latin})\\s*({cjk})', raw)
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
    'pinyin': {'英文拼音', '拼音姓名', '姓名拼音', '拼音', 'pinyin', 'romanizedname'},
    'teaching_class': {'授課班', '授课班', '授課班級', '授课班级', 'teachingclass'},
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
        summaries=[s for s in wb if norm(s.title) in {'匯總','汇总','summary','總表','总表'}]
        if summaries:
            sheets=[summaries[0]]
        elif len(wb.worksheets)==1:
            sheets=wb.worksheets
        else:
            raise ValidationError(f'{path.name}：找不到匯總工作表，請提供完整匯總名單；不會讀取或合併分班 Sheet。')
        for sheet in sheets:
            columns, header = {}, None
            for row in sheet.iter_rows(max_row=min(sheet.max_row, 50)):
                mapping = {}
                for cell in row:
                    for key, aliases in ALIASES.items():
                        if norm(cell.value) in aliases:
                            mapping[key] = cell.column
                # VBA output may retain both a pinyin column and a nickname
                # column. Prefer the explicit pinyin regardless of column order.
                if 'pinyin' in mapping:
                    if 'en' in mapping:
                        mapping['alternate_en'] = mapping['en']
                    mapping['en'] = mapping['pinyin']
                if 'id' in mapping and ('cn' in mapping or 'en' in mapping):
                    columns, header = mapping, row[0].row
                    break
            if header is None:
                continue
            meta = {}
            for row in sheet.iter_rows(max_row=header-1):
                for i, cell in enumerate(row[:-1]):
                    if cell.value in ('科目名稱', '科目代碼', '教務科目代碼', '授課老師', '課程'):
                        meta[str(cell.value)] = str(row[i+1].value or '').strip()
            title = meta.get('科目名稱', '')
            match = re.search(r'([A-Za-z]{2,}\d{2,})-([A-Za-z0-9]+)\s*$', title)
            code = meta.get('教務科目代碼', '') or (match[1] if match else '')
            teaching = parse_teaching_code(meta.get('科目代碼', ''), code)
            if teaching:
                code = teaching.course_code
            elif meta.get('科目代碼'):
                raise ValidationError(f'{path.name}：完整科目代碼「{meta["科目代碼"]}」無法識別或與科目編號不符，請核對該檔案的科目資料。')
            course_name = title[:match.start()].rstrip(' -') if match else title
            filename_class=re.fullmatch(r'\d{1,2}[A-Za-z]+',path.stem.strip())
            title_class=match[2].upper() if match else ''
            explicit_classes=set()
            if 'teaching_class' in columns:
                explicit_classes={str(sheet.cell(i,columns['teaching_class']).value or '').strip()
                                  for i in range(header+1,sheet.max_row+1)
                                  if sheet.cell(i,columns['id']).value}
                explicit_classes.discard('')
                if len(explicit_classes)>1:
                    raise ValidationError(f'{path.name}：明確授課班欄包含多個授課班，請分開提供各班的匯總名單。')
            cls=(teaching.class_name if teaching else
                 next(iter(explicit_classes),'') or
                 (filename_class[0].upper() if filename_class else '') or
                 (title_class if re.fullmatch(r'\d{1,2}[A-Z]+',title_class) else ''))
            records = []
            for row in sheet.iter_rows(min_row=header+1):
                idcell = row[columns['id']-1]
                raw_id = str(idcell.value or '')
                if '教師簽字' in raw_id or '教师签字' in raw_id:
                    continue
                def val(key):
                    return str(row[columns[key]-1].value or '').strip() if key in columns else ''
                if not any(val(k) for k in ['id', 'cn', 'en']):
                    continue
                sid, issues = cell_text(idcell)
                cn, en = val('cn'), val('en')
                raw = '\n'.join(dict.fromkeys(filter(None, [cn, en, val('alternate_en')])))
                if cn:
                    cn, embedded_en, name_issues = split_name(cn)
                    # Existing explicit two-column names need no new script
                    # restriction. Still flag an ambiguous mixed-script cell.
                    mixed = re.search(r'[\u3400-\u9fff\uf900-\ufaff]', cn) and re.search(r'[A-Za-zÀ-ž]', cn)
                    if not en or mixed:
                        issues += name_issues
                    # The separate English column can contain a nickname. The
                    # official full name/pinyin in 姓名 takes precedence.
                    en = embedded_en or en
                elif en:
                    _, _, name_issues = split_name(en)
                    issues += name_issues
                else:
                    issues.append('姓名缺失')
                if not sid or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', sid):
                    issues.append('空白或錯誤學號')
                record = StudentRecord(sid, cn, en, cls, code or val('code'),
                                       val('course') or course_name, meta.get('課程', ''),
                                       meta.get('授課老師', ''), path.name, raw, issues)
                if teaching:
                    record.teaching_code = teaching.value
                    record.academic_year = teaching.academic_year
                    record.semester = teaching.semester
                    record.programme_code = teaching.programme_code
                    record.grade = teaching.grade
                    if teaching.programme_code in PROGRAMMES:
                        record.programme = PROGRAMMES[teaching.programme_code][0]
                if not record.course_code:
                    issues.append('科目代碼缺失（可在預覽填寫）')
                if not cls:
                    issues.append('班級缺失（可在預覽填寫）')
                records.append(record)
            if records:
                counts = Counter(r.student_no for r in records)
                for rec in records:
                    if counts[rec.student_no] > 1:
                        rec.issues.append('同 Sheet 重複學號，需要人工確認')
                candidates.append(Candidate('匯總', cls, records, True))
        if not candidates:
            raise ValidationError('匯總名單找不到學號與姓名表頭，請使用「帳號／學號、姓名、英文姓名」欄位。')
        return candidates
    finally:
        wb.close()

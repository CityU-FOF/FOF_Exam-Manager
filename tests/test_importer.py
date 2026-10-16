import os
from pathlib import Path
import pytest
from openpyxl import Workbook,load_workbook
from app.importers.roster import inspect_roster,split_name
from app.models.records import ValidationError
from app.exporters.excel import ExcelExporter


@pytest.mark.parametrize('raw,cn,en',[
 ('陳大文 CHAN TAI MAN','陳大文','CHAN TAI MAN'),
 ('陈大文\nCHAN TAI MAN','陈大文','CHAN TAI MAN'),
 ("王小明 O'NEILL-SMITH",'王小明',"O'NEILL-SMITH"),
 ('CHAN TAI MAN 陳大文','陳大文','CHAN TAI MAN'),
 ('陳大文','陳大文',''),
 ('陳大文CHAN TAI MAN','陳大文','CHAN TAI MAN'),
 ('CHAN TAI MAN陳大文','陳大文','CHAN TAI MAN'),
 ('(緬甸)昂敏 AUNG MIN','(緬甸)昂敏','AUNG MIN'),
 ('ANA MARIA SILVA','','ANA MARIA SILVA'),
 ('José de Sousa','','José de Sousa'),
])
def test_names(raw,cn,en):
    assert split_name(raw)==(cn,en,[])


def test_ambiguous_name_retained():
    raw='陳（大文） / CHAN 123';cn,en,issues=split_name(raw)
    assert cn==raw and issues


@pytest.mark.parametrize('pinyin_first',[True,False])
def test_vba_pinyin_header_wins_over_nickname(tmp_path,pinyin_first):
    wb=Workbook();s=wb.active
    names=['英文拼音','英文姓名'] if pinyin_first else ['英文姓名','英文拼音']
    values=['CHAN TAI MAN','David'] if pinyin_first else ['David','CHAN TAI MAN']
    s.append(['帳號','中文姓名',*names,'班級','科目代碼'])
    s.append(['F20990100001','陳大文',*values,'4B','BAE409'])
    path=tmp_path/'vba-output.xlsx';wb.save(path)
    record=inspect_roster(path)[0].records[0]
    assert (record.chinese_name,record.english_name)==('陳大文','CHAN TAI MAN')
    assert 'David' in record.raw_name
    assert not record.issues


def test_official_combined_name_overrides_nickname_and_allows_english_only(manager,tmp_path):
    wb=Workbook();s=wb.active
    s.append(['學號','姓名','英文姓名','班級','科目代碼'])
    s.append(['001','陳大文CHAN TAI MAN','David','4B','BAE409'])
    s.append(['002','ANA MARIA SILVA','Ana','4B','BAE409'])
    s.append(['003','','José de Sousa','4B','BAE409'])
    s.append(['004','李小明','LI XIAOMING','4B','BAE409'])
    path=tmp_path/'original.xlsx';wb.save(path)
    records=inspect_roster(path)[0].records
    assert [(r.chinese_name,r.english_name) for r in records]==[
        ('陳大文','CHAN TAI MAN'),('','ANA MARIA SILVA'),
        ('','José de Sousa'),('李小明','LI XIAOMING')]
    assert records[0].raw_name=='陳大文CHAN TAI MAN\nDavid'
    assert not any(r.issues for r in records)
    manager.import_records(records)
    assert len(manager.students())==4
    course=manager.courses()[0]
    manager.save_course(dict(code='BAE409',name_cn='風險管理簡介',name_en='Introduction to Risk Management',teachers='測試教師'),course['id'])
    room=manager.save_room(dict(name='TEST',capacity=4,enabled=1))
    batch=manager.save_batch(dict(name='姓名驗證',academic_year='2026–2027',semester='第一學期',exam_type='期中'))
    cls=manager.classes()[0]['id']
    session=manager.create_session(batch,course['id'],dict(date='2026-10-17',start='10:30',end='12:30',teachers='測試教師',intake='2023-08'),[cls],[room])
    aid=manager.allocations(session)[0]['id'];manager.assign(aid,cls)
    wb=load_workbook(ExcelExporter(manager).generate(aid,tmp_path/'output'))
    for sheet in wb:
        en_col=5 if sheet.title=='Attendance' else 6
        assert [sheet.cell(row,4).value for row in range(18,22)]==['陳大文',None,None,'李小明']
        assert [sheet.cell(row,en_col).value for row in range(18,22)]==['CHAN TAI MAN','ANA MARIA SILVA','José de Sousa','LI XIAOMING']
    wb.close()


def test_original_fourth_year_attachments(manager,tmp_path):
    root=os.environ.get('FOF_REFERENCE_DIR')
    if not root:pytest.skip('Set FOF_REFERENCE_DIR to private original rosters')
    files={p.name:p for p in Path(root).rglob('4?.xlsx')}
    if not {'4B.xlsx','4C.xlsx','4D.xlsx','4E.xlsx'}<=set(files):
        pytest.skip('Original fourth-year attachments not provided')
    for cls,count in {'B':30,'C':28,'D':32,'E':26}.items():
        selected=[c for c in inspect_roster(files[f'4{cls}.xlsx']) if c.recommended]
        assert len(selected)==1
        candidate=selected[0]
        assert candidate.class_name=='4'+cls
        assert len(candidate.records)==count
        assert not any(r.issues for r in candidate.records)
        for r in candidate.records:
            assert r.chinese_name and r.english_name
            assert not any(c.isascii() and c.isalpha() for c in r.chinese_name)
            assert r.raw_name.startswith(r.chinese_name)
            assert r.english_name in r.raw_name.split('\n')[0]
        manager.import_records(candidate.records)
    assert len(manager.students())==116
    course=manager.courses()[0]
    manager.save_course(dict(code=course['code'],name_cn=course['name_cn'],
                            name_en='Introduction to Risk Management'),course['id'])
    rooms=[manager.save_room(dict(name=n,capacity=80,enabled=1)) for n in ('G2207','G2209')]
    batch=manager.save_batch(dict(name='原檔驗證',academic_year='2026–2027',semester='第一學期',exam_type='期中'))
    classes=manager.classes()
    session=manager.create_session(batch,course['id'],dict(date='2026-10-17',start='10:30',end='12:30',teachers='測試教師',intake='2023-08'),
                                   [c['id'] for c in classes],rooms)
    allocations={a['room_name']:a['id'] for a in manager.allocations(session)}
    for c in classes:
        manager.assign(allocations['G2209' if c['name'] in ('4B','4D') else 'G2207'],c['id'])
    for aid in allocations.values():
        path=ExcelExporter(manager).generate(aid,tmp_path/'private-output')
        with path.open('rb') as stream:
            wb=load_workbook(stream)
            for sheet in wb:
                assert sheet['A1'].value=='澳門城市大學'
                assert sheet.sheet_view.topLeftCell=='A1'
                assert sheet.freeze_panes is None
                assert not sheet.protection.sheet
                assert sheet['E10'].alignment.horizontal=='right'
                assert sheet.row_dimensions[10].height==16.5
            wb.close()


def test_numeric_id_formats_and_duplicates(tmp_path):
    wb=Workbook();s=wb.active;s.title='D'
    s.append(['帳號','姓名','英文姓名','班級','科目代碼'])
    s.append([123,'陳大文 CHAN TAI MAN','','D','C101']);s['A2'].number_format='000000'
    s.append(['000123','陳大文','CHAN TAI MAN','D','C101'])
    s.append(['=1+1','未確認','UNKNOWN','D','C101'])
    path=tmp_path/'roster.xlsx';wb.save(path)
    candidates=inspect_roster(path);records=candidates[0].records
    assert records[0].student_no=='000123'
    assert records[0].chinese_name=='陳大文' and records[0].english_name=='CHAN TAI MAN'
    assert any('重複' in x for x in records[0].issues)
    assert any('公式' in x for x in records[2].issues)


def test_summary_fallback(tmp_path):
    wb=Workbook();s=wb.active;s.title='匯總'
    s.append(['學號','姓名','英文姓名','班級','科目代碼']);s.append(['001','甲','A','D','C101']);s.append(['002','乙','B','E','C101'])
    p=tmp_path/'all.xlsx';wb.save(p)
    cs=inspect_roster(p);assert len(cs)==2 and all(c.recommended for c in cs)


def test_file_validation(tmp_path):
    p=tmp_path/'bad.xlsx';p.write_bytes(b'not Excel')
    with pytest.raises(ValidationError):inspect_roster(p)
    with pytest.raises(ValidationError):inspect_roster(tmp_path/'macro.xlsm')


def test_actual_attachments_import_and_export(manager,tmp_path):
    root=os.environ.get('FOF_REFERENCE_DIR')
    if not root:pytest.skip('Set FOF_REFERENCE_DIR to the six private uploaded Excel files')
    files={p.name:p for p in Path(root).rglob('*.xlsx')}
    assert {'3D.xlsx','3E.xlsx','3F.xlsx','3G.xlsx'}<=set(files)
    expected={'D':30,'E':28,'F':34,'G':35}
    for cls,n in expected.items():
        cs=inspect_roster(files[f'3{cls}.xlsx'])
        selected=[c for c in cs if c.recommended]
        assert len(selected)==1 and selected[0].sheet=='匯總' and selected[0].class_name=='3'+cls and len(selected[0].records)==n
        assert not any(r.issues for r in selected[0].records)
        manager.import_records(selected[0].records)
    assert len(manager.students())==127
    assert manager.db.one('SELECT COUNT(*) n FROM students')['n']==127
    # Reimport is idempotent, never doubles membership.
    rr=[r for c in inspect_roster(files['3F.xlsx']) if c.recommended for r in c.records]
    assert len(manager.import_records(rr)['unchanged'])==34
    course=manager.courses()[0]
    manager.save_course({'code':course['code'],'name_cn':course['name_cn'],'name_en':'Corporate Finance','programme':course['programme'],
                         'programme_en':'Bachelor of Applied Economics Programme (Chinese)','teachers':'江宇'},course['id'])
    rooms=[manager.save_room({'name':n,'capacity':80,'enabled':1}) for n in ['G2207','G2209']]
    batch=manager.save_batch({'name':'實際附件驗證','academic_year':'2026–2027','semester':'第一學期','exam_type':'期中'})
    classes=manager.classes();sid=manager.create_session(batch,course['id'],{'date':'2026-10-14','start':'19:00','end':'21:00','teachers':'江宇','intake':'2026-08'},[c['id'] for c in classes],rooms)
    als={a['room_name']:a['id'] for a in manager.allocations(sid)}
    for c in classes:manager.assign(als['G2209' if c['name'] in ('3D','3F') else 'G2207'],c['id'])
    assert [a['count'] for a in manager.allocations(sid)]==[63,64]
    for aid in als.values():
        path=ExcelExporter(manager).generate(aid,tmp_path/'actual-output')
        wb=load_workbook(path,data_only=True)
        students=manager.assigned(aid=aid)
        assert wb['Attendance']['D14'].value==len(students)
        assert [wb['Attendance'].cell(i,3).value for i in range(18,18+len(students))]==[wb['Seat Plan'].cell(i,3).value for i in range(18,18+len(students))]
        wb.close()

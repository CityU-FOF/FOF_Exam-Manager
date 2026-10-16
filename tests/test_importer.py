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
])
def test_names(raw,cn,en):
    assert split_name(raw)==(cn,en,[])


def test_ambiguous_name_retained():
    raw='陳（大文） / CHAN 123';cn,en,issues=split_name(raw)
    assert cn==raw and issues


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

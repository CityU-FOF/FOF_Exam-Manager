import hashlib
import sqlite3
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

pytestmark=pytest.mark.usefixtures("qapp")
from PySide6.QtWidgets import QFileDialog,QMessageBox
from app.database.store import Store
from app.services.manager import Manager
from app.services.papers import PaperManager,default_settings,print_quantities,language_for_class
from app.exporters.papers import PaperExporter
from app.models.records import ValidationError,StudentRecord
from app.ui.window import MainWindow
from app.ui.student_flags import StudentFlagReminder
from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt
from conftest import setup_exam


def confirmed():
    settings=default_settings();settings.update(approval='not_required',book='closed')
    settings['cn'].update(pages=10,formula='included');settings['en'].update(pages=13,formula='included')
    return settings


def setup_documents(manager):
    sid,classes,rooms=setup_exam(manager,(3,2))
    for name,cid in zip(rooms,classes.values()):manager.assign(rooms[name],cid)
    pm=PaperManager(manager);pm.save(sid,confirmed())
    return sid,classes,rooms,pm


def test_confirmed_1630_sheet_example():
    groups=[dict(name='1A',language='en',students=25)]
    groups += [dict(name='1'+c,language='cn',students=33 if c!='H' else 32) for c in 'BCDEFGH']
    result=print_quantities(groups,confirmed())
    assert result['total_sheets']==1630 and result['boxes']==1 and result['reams']==4
    assert (result['full_reams'],result['loose_sheets'])==(3,130)
    assert [(r['copies'],r['sheets_per_copy'],r['paper_sheets']) for r in result['rows']]==[(237,6,1422),(26,8,208)]


@pytest.mark.parametrize('name,language',[('A','en'),('1A','en'),('4a','en'),('1B','cn'),('3D','cn'),('AA','cn')])
def test_language_uses_teaching_class(name,language):assert language_for_class(name)==language


def test_formula_included_separate_and_unknown_are_distinct():
    groups=[dict(name='1B',language='cn',students=25)]
    settings=confirmed()
    assert print_quantities(groups,settings)['total_sheets']==156
    settings['cn'].update(formula='separate')
    with pytest.raises(ValidationError,match='獨立公式表'):print_quantities(groups,settings)
    settings['cn'].update(formula_pages=3,formula_copies=26,formula_sides='double',formula_cover='none')
    assert print_quantities(groups,settings)['total_sheets']==208
    settings['cn'].update(formula_cover='single')
    assert print_quantities(groups,settings)['total_sheets']==234
    settings['cn'].update(formula='pending')
    with pytest.raises(ValidationError,match='公式表'):print_quantities(groups,settings)


def test_spares_count_class_once_even_when_split(manager):
    sid,cl,rooms=setup_exam(manager,(3,))
    first=manager.pending(sid)[0]
    manager.assign(rooms['G2207'],cl['D'],[first['student_id']]);manager.assign(rooms['G2209'],cl['D'])
    context=PaperManager(manager).context(sid)
    r=print_quantities(context['groups'],confirmed())['rows'][0]
    assert r['copies']==4 and r['spares']==1


def test_approved_pdf_exact_bytes_survive_backup_and_restart(manager,tmp_path):
    sid,cl,rooms,pm=setup_documents(manager)
    settings=confirmed();settings['approval']='required';pm.save(sid,settings)
    original=b'%PDF-1.7\n% APPROVED_QR_CODE_DO_NOT_CHANGE\n%%EOF'
    source=tmp_path/'approved.pdf';source.write_bytes(original);pm.put_cover(sid,'cn',source)
    saved=manager.db.backup(tmp_path/'backup.sqlite3')
    with manager.db.conn:manager.db.conn.execute('DELETE FROM paper_covers')
    manager.db.restore(saved)
    assert pm.cover_bytes(sid,'cn')==original
    bundle=PaperExporter(manager).generate(sid,tmp_path/'output',['cover'])
    exported=next(bundle.glob('*.pdf'))
    assert exported.read_bytes()==source.read_bytes()
    assert hashlib.sha256(exported.read_bytes()).hexdigest()==pm.covers(sid)['cn']['sha256']
    assert {p.name for p in bundle.iterdir()}=={exported.name}


def test_pending_approval_and_missing_pdf_block_without_partial_files(manager,tmp_path):
    sid,cl,rooms,pm=setup_documents(manager)
    settings=confirmed();settings['approval']='pending';pm.save(sid,settings)
    with pytest.raises(ValidationError,match='是否需要'):PaperExporter(manager).generate(sid,tmp_path/'out',['review','cover'])
    assert not (tmp_path/'out').exists()
    settings['approval']='required';pm.save(sid,settings)
    with pytest.raises(ValidationError,match='未匯入'):PaperExporter(manager).generate(sid,tmp_path/'out',['cover'])
    assert not (tmp_path/'out').exists()


def test_original_pdf_forms_and_unchanged_cover_excel(manager,tmp_path):
    sid,cl,rooms,pm=setup_documents(manager)
    student=manager.assigned(sid)[0];manager.set_student_flag(student['student_id'],'PRIVATE_FLAG_MUST_NOT_PRINT_985')
    output=PaperExporter(manager).generate(sid,tmp_path,['review','cover','bag','statistics'])
    assert len(list(output.glob('附件一*.pdf')))==1
    assert len(list(output.glob('試卷袋封面*.pdf')))==2
    assert len(list(output.glob('*.xlsx')))==2
    assert len(list(output.iterdir()))==5
    for pdf in output.glob('*.pdf'):
        reader=PdfReader(pdf)
        assert len(reader.pages)==1 and list(map(float,reader.pages[0].mediabox))==[0,0,595.32,841.92]
        assert 'PRIVATE_FLAG_MUST_NOT_PRINT_985' not in reader.pages[0].extract_text()
    context=PaperManager(manager).context(sid)
    assert [(r['name'],r['count'],r['classes']) for r in context['rooms']]==[
        ('G2207',3,[dict(name='D',count=3,spares=1)]),('G2209',2,[dict(name='E',count=2,spares=1)])]
    # Annex two is still the original editable Excel path; no XFA code is used.
    cover=next(output.glob('附件二*.xlsx'))
    ns={'x':'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'}
    with ZipFile(cover) as z:
        assert z.testzip() is None
        assert not any(b'PRIVATE_FLAG_MUST_NOT_PRINT_985' in z.read(n) for n in z.namelist())
        assert [n for n in z.namelist() if n.startswith('xl/media/')]
        drawing=ET.fromstring(z.read('xl/drawings/drawing1.xml'))
        assert all(shape.get('textlink').startswith("'資料'!$B$") for shape in drawing.findall('x:absoluteAnchor/x:sp',ns))
    again=PaperExporter(manager).generate(sid,tmp_path,['review'])
    assert again!=output and output.exists()


def test_bag_export_rejects_unassigned_students(manager,tmp_path):
    sid,_,_=setup_exam(manager,(3,))
    with pytest.raises(ValidationError,match='未分配'):PaperExporter(manager).generate(sid,tmp_path,['bag'])


def test_multi_course_boxes_round_after_summing_and_do_not_repeat_selected_exam(manager,tmp_path):
    first,_,_,pm=setup_documents(manager)
    second,_,_=setup_exam(manager,(3,2),code='BAE103',dt='2026-12-03')
    pm.save(second,confirmed())
    path=PaperExporter(manager).batch_statistics([first,second,first],tmp_path)
    wb=load_workbook(path);rows=list(wb.active.values)
    total=next(r[1] for r in rows if r[0]=='整批總張數')
    assert total==84
    assert next(r[1] for r in rows if r[0]=='約需整箱')==1
    assert len([r for r in rows if isinstance(r[0],str) and r[0].startswith('BAE')])==2
    wb.close()


def test_v3_upgrade_preserves_flags_and_assignments(manager,tmp_path):
    sid,cl,rooms,pm=setup_documents(manager);r=manager.assigned(sid)[0]
    manager.set_student_flag(r['student_id'],'保留標記')
    snapshot=manager.snapshot(sid);path=manager.db.backup(tmp_path/'old_v3.sqlite3')
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE paper_covers');db.execute('DROP TABLE paper_settings');db.execute('UPDATE schema_version SET version=3')
    upgraded=Store(path)
    try:
        m=Manager(upgraded)
        assert m.snapshot(sid)==snapshot and m.flagged_students()[0]['flag_reason']=='保留標記'
        assert upgraded.one('SELECT version FROM schema_version')['version']==4
        with sqlite3.connect(upgraded.upgrade_backup) as backup:assert backup.execute('SELECT version FROM schema_version').fetchone()[0]==3
    finally:upgraded.close()


def test_paper_page_auto_saves_per_course_and_exports(qtbot,manager,tmp_path,monkeypatch):
    sid,cl,rooms,pm=setup_documents(manager)
    window=MainWindow(manager);qtbot.addWidget(window);window.select_session(sid,8)
    page=window.paper_page
    page.language_editors['cn']['pages'].setValue(11)
    assert pm.settings(sid)['cn']['pages']==11
    assert '設定已自動保存' in page.total.text()
    page.kinds['statistics'].setChecked(True)
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**k:str(tmp_path))
    messages=[];monkeypatch.setattr(QMessageBox,'information',lambda *a,**k:messages.append(a))
    monkeypatch.setattr(QMessageBox,'warning',lambda *a,**k:pytest.fail(str(a)))
    page.generate()
    assert page.last_output.exists() and list(page.last_output.glob('印刷*.xlsx'))
    backup=manager.db.backup(tmp_path/'paper_backup.sqlite3')
    page.language_editors['cn']['pages'].setValue(99)
    manager.db.restore(backup);window.refresh_all()
    assert page.language_editors['cn']['pages'].value()==11
    other,_,_=setup_exam(manager,(1,),code='BAE103',dt='2026-12-03')
    window.refresh_all();window.select_session(other,8)
    assert page.language_editors['cn']['pages'].value()==0
    window.select_session(sid,8);assert page.language_editors['cn']['pages'].value()==11


def test_bag_generation_preserves_special_student_reminder(qtbot,manager,monkeypatch):
    sid,cl,rooms,pm=setup_documents(manager)
    student=manager.assigned(sid)[0];manager.set_student_flag(student['student_id'],'私有原因')
    window=MainWindow(manager);qtbot.addWidget(window);window.select_session(sid,8)
    def adjust(dialog):
        dialog.adjust();return QDialog.DialogCode.Rejected
    monkeypatch.setattr(StudentFlagReminder,'exec',adjust)
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**k:pytest.fail('Must return to seating before export'))
    window.paper_page.generate()
    assert window.nav.currentRow()==6
    assert window.seat_tree.currentItem().data(0,Qt.ItemDataRole.UserRole)==student['id']


def test_review_and_bags_need_no_approved_cover_or_page_counts(manager,tmp_path):
    sid,_,_,pm=setup_documents(manager)
    pm.save(sid,default_settings())
    output=PaperExporter(manager).generate(sid,tmp_path,['review','bag'])
    assert {p.name for p in output.iterdir()}=={'附件一_試卷評審記錄.pdf','試卷袋封面_BAE305_D_G2207.pdf','試卷袋封面_BAE305_E_G2209.pdf'}
    assert pm.covers(sid)=={}


def test_legacy_cover_missing_image_support_explains_repair_without_creating_outputs(manager,tmp_path,monkeypatch):
    import openpyxl.drawing.image
    sid,_,_,_=setup_documents(manager)
    monkeypatch.setattr(openpyxl.drawing.image,'PILImage',None)
    folder=tmp_path/'not_created'
    with pytest.raises(RuntimeError,match='首次安裝.bat') as error:
        PaperExporter(manager).generate(sid,folder,['cover'])
    assert '與試題審批無關' in str(error.value)
    assert not folder.exists()


def test_paper_output_opens_before_generation_and_reports_desktop_failure(qtbot,manager,monkeypatch):
    from app.ui.papers import PaperPage,QDesktopServices
    page=PaperPage(manager);qtbot.addWidget(page)
    opened=[]
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:opened.append(url) or True)
    assert not page.output_folder.exists() and page.last_output is None
    page.open_output()
    assert page.output_folder.is_dir() and Path(opened[0].toLocalFile())==page.output_folder
    messages=[]
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:False)
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:messages.append(a[-1]))
    page.open_output()
    assert str(page.output_folder) in messages[0]


def test_failed_generation_retains_selected_output_folder(qtbot,manager,tmp_path,monkeypatch):
    import openpyxl.drawing.image
    from app.ui.papers import PaperPage,QDesktopServices
    sid,_,_,_=setup_documents(manager)
    page=PaperPage(manager);qtbot.addWidget(page);page.load_session(sid)
    page.kinds['cover'].setChecked(True)
    page.last_output=tmp_path/'previous';page.last_output.mkdir()
    chosen=tmp_path/'chosen';chosen.mkdir()
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**k:str(chosen))
    monkeypatch.setattr(openpyxl.drawing.image,'PILImage',None)
    messages=[];monkeypatch.setattr(QMessageBox,'warning',lambda *a:messages.append(a[-1]))
    page.generate()
    assert messages and page.last_output is None and page.output_folder==chosen
    opened=[];monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:opened.append(url) or True)
    page.open_output()
    assert Path(opened[0].toLocalFile())==chosen and not list(chosen.iterdir())

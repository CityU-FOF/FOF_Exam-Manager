import pytest
from openpyxl import Workbook
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QMessageBox
from app.importers.roster import inspect_roster
from app.models.programmes import parse_teaching_code
from app.models.records import ValidationError
from app.ui.import_dialog import ImportDialog
from app.ui.window import MainWindow


def original_roster(path,group='B',count=3,summary_title='匯總'):
    wb=Workbook();admin=wb.active;admin.title='A'
    admin.append(['帳號','姓名','班級']);admin.append(['SHOULD_NOT_IMPORT','錯誤分頁','A'])
    summary=wb.create_sheet(summary_title)
    summary.append(['科目名稱',f'微觀經濟學導論 - BAE103-{group}'])
    summary.append(['科目代碼',f'261BAECF1{group}BAE10300CB','教務科目代碼','BAE103'])
    summary.append(['帳號','姓名','英文姓名','班級'])
    for i in range(count):summary.append([f'DEMO{group}{i:04d}','陳大文 CHAN TAI MAN','David','ABCDEFGH'[i%8]])
    # A damaged administrative sheet must not even be parsed.
    for name in ['B','C','H']:
        s=wb.create_sheet(name);s.append(['帳號','姓名','班級']);s.append(['=1+1','不應讀取','X'])
    wb.save(path);return path


@pytest.mark.parametrize('value',['261BAECF1BBAE10300CB',' 261BAECF1BBAE10300CB\n','２６１ＢＡＥＣＦ１ＢＢＡＥ１０３００ＣＢ'])
def test_first_year_cb_code(value):
    code=parse_teaching_code(value,'BAE103')
    assert (code.value,code.class_name,code.course_code,code.academic_year,code.semester)==(
        '261BAECF1BBAE10300CB','1B','BAE103','2026–2027','第一學期')


@pytest.mark.parametrize('summary_title',['匯總','汇总','Summary'])
def test_only_summary_read_and_administrative_fields_ignored(tmp_path,summary_title):
    path=original_roster(tmp_path/'1B.xlsx',count=27,summary_title=summary_title)
    candidates=inspect_roster(path)
    assert len(candidates)==1 and candidates[0].sheet=='匯總'
    records=candidates[0].records
    assert len(records)==27 and {r.class_name for r in records}=={'1B'}
    assert {r.course_code for r in records}=={'BAE103'}
    assert not any(r.administrative_class or r.issues for r in records)
    assert not any(r.student_no=='SHOULD_NOT_IMPORT' for r in records)


def test_many_students_confirm_without_per_row_code_warnings(qtbot,manager,tmp_path,monkeypatch):
    paths=[original_roster(tmp_path/'1B.xlsx',count=101),original_roster(tmp_path/'1H.xlsx',group='H',count=100)]
    dialog=ImportDialog(manager,paths);qtbot.addWidget(dialog)
    assert dialog.sheets.rowCount()==2 and dialog.preview.rowCount()==201
    assert [dialog.sheets.item(i,2).text() for i in range(2)]==['匯總','匯總']
    assert '0 筆資料需核對' in dialog.summary.text()
    assert all(dialog.preview.item(i,9).checkState()==Qt.CheckState.Checked for i in range(201))
    errors=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:errors.append(args))
    dialog.commit()
    assert not errors and dialog.result()==QDialog.DialogCode.Accepted
    assert len(manager.students())==201 and len(manager.classes())==2
    assert {r.administrative_class for r in dialog.records}=={''}
    window=MainWindow(manager);qtbot.addWidget(window)
    for table in [dialog.preview,window.students_table]:
        assert not any('行政班' in table.horizontalHeaderItem(i).text() for i in range(table.columnCount()))
    assert '行政班' not in dialog.summary.text()
    # Reimport the same summaries without doubling either students or membership.
    records=[r for path in paths for c in inspect_roster(path) for r in c.records]
    assert len(manager.import_records(records)['unchanged'])==201
    assert len(manager.students())==201


def test_real_row_errors_still_require_review_and_are_located(qtbot,manager,tmp_path):
    path=original_roster(tmp_path/'1B.xlsx')
    from openpyxl import load_workbook
    wb=load_workbook(path);wb['匯總']['A4']='=1+1';wb.save(path);wb.close()
    dialog=ImportDialog(manager,[path]);qtbot.addWidget(dialog)
    with pytest.raises(ValueError,match='待核對資料'):dialog.edited_records()
    assert dialog.preview.currentRow()==0 and dialog.preview.currentColumn()==9
    assert not manager.students()


def test_unknown_code_rejected_once_at_file_level(tmp_path):
    path=original_roster(tmp_path/'1B.xlsx')
    from openpyxl import load_workbook
    wb=load_workbook(path);wb['匯總']['B2']='unsupported';wb.save(path);wb.close()
    with pytest.raises(ValidationError,match='1B.xlsx.*完整科目代碼.*unsupported'):
        inspect_roster(path)

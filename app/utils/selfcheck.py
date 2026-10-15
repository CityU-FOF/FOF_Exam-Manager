import json
import tempfile
from pathlib import Path
from app.database.store import Store
from app.services.manager import Manager
from app.models.records import StudentRecord
from app.exporters.excel import ExcelExporter
from app.ui.window import MainWindow


def selfcheck(app,folder):
    """Explicit deployment check, using synthetic data in an isolated database."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    report=folder/'selfcheck.json'
    if report.exists():raise FileExistsError('Self-check report exists; choose a new output directory.')
    with tempfile.TemporaryDirectory(prefix='fof-selfcheck-') as temp:
        store=Store(Path(temp)/'test.sqlite3');window=None
        try:
            m=Manager(store)
            m.import_records([StudentRecord(f'SMOKE{i:03d}',f'測試學生{i}',f'SYNTHETIC STUDENT {i}','D','TEST101',
                              '打包驗證','測試課程','測試教師') for i in range(1,4)])
            c=m.courses()[0]
            m.save_course({'code':c['code'],'name_cn':'打包驗證','name_en':'Package Check',
                           'programme':'測試課程','programme_en':'Synthetic Programme'},c['id'])
            room=m.save_room({'name':'TESTROOM','capacity':5,'enabled':1})
            batch=m.save_batch({'name':'打包驗證','academic_year':'2026–2027','semester':'第一學期','exam_type':'期中'})
            cls=m.classes()[0]['id']
            sid=m.create_session(batch,c['id'],{'date':'2026-10-14','start':'09:00','end':'11:00','teachers':'測試教師','intake':'2026-08'},[cls],[room])
            aid=m.allocations(sid)[0]['id'];m.assign(aid,cls)
            order=[r['id'] for r in m.assigned(sid)];order.insert(0,order.pop());m.reorder(aid,order)
            m.complete(sid)
            path=ExcelExporter(m).generate(aid,folder)
            window=MainWindow(m);window.show();app.processEvents()
            if window.pages.count()!=9:raise RuntimeError('Missing UI pages')
            result={'status':'passed','ui_pages':9,'students':3,'sheets':['Attendance','Seat Plan'],'output':str(path)}
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
            return result
        finally:
            if window:window.close()
            store.close()

"""Validate the user's six private reference workbooks without bundling them."""
import argparse
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import load_workbook
from app.importers.roster import inspect_roster
from app.database.store import Store
from app.services.manager import Manager
from app.exporters.excel import ExcelExporter


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('reference_dir',type=Path)
    parser.add_argument('output_dir',type=Path)
    args=parser.parse_args()
    files={p.name:p for p in args.reference_dir.rglob('*.xlsx')}
    with tempfile.TemporaryDirectory(prefix='fof-reference-') as temp:
        store=Store(Path(temp)/'validation.sqlite3');m=Manager(store)
        try:
            counts={}
            for cls in 'DEFG':
                candidates=inspect_roster(files[f'3{cls}.xlsx'])
                selected=[c for c in candidates if c.recommended]
                if len(selected)!=1 or selected[0].class_name!='3'+cls:raise RuntimeError('Unexpected selected class')
                counts[cls]=len(selected[0].records);m.import_records(selected[0].records)
            wb=load_workbook(files['考試出席表_BAE305_G2207.xlsx'],keep_links=False,data_only=False)
            s=wb['Attendance'];programme=s['A3'].value;programme_en=s['A4'].value;teachers=s['E10'].value
            intake=s['D10'].value;dt=s['G12'].value.date().isoformat();start,end=s['G14'].value.split('-');wb.close()
            course=m.courses()[0]
            m.save_course({'code':course['code'],'name_cn':course['name_cn'],'name_en':'Corporate Finance',
                           'teachers':teachers,'programme':programme,'programme_en':programme_en},course['id'])
            rooms=[m.save_room({'name':name,'capacity':80,'enabled':1}) for name in ['G2207','G2209']]
            b=m.save_batch({'name':'2026–2027學年第一學期期中考試','academic_year':'2026–2027','semester':'第一學期','exam_type':'期中'})
            classes=m.classes();sid=m.create_session(b,course['id'],{'date':dt,'start':start,'end':end,'teachers':teachers,'intake':intake},[c['id'] for c in classes],rooms)
            als={a['room_name']:a['id'] for a in m.allocations(sid)}
            for c in classes:m.assign(als['G2209' if c['name'] in ('3D','3F') else 'G2207'],c['id'])
            m.complete(sid)
            results=ExcelExporter(m).batch(list(als.values()),args.output_dir)
            if any(r[1]!='成功' for r in results):raise RuntimeError('Reference output failed: '+str(results))
            report={'actual_class_counts':counts,'total':sum(counts.values()),'example_counts':{'D':30,'E':28,'F':34,'G':35},
                    'room_counts':{a['room_name']:a['count'] for a in m.allocations(sid)},'files':[r[2] for r in results],'validation_errors':m.validate(sid)}
            (args.output_dir/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps(report,ensure_ascii=False))
        finally:store.close()


if __name__=='__main__':main()

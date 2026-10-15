import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/fof-qt-cache')
import pytest
from app.database.store import Store
from app.services.manager import Manager
from app.models.records import StudentRecord


@pytest.fixture
def manager(tmp_path):
    store=Store(tmp_path/'data.sqlite3');m=Manager(store)
    yield m
    store.close()


def setup_exam(m,counts=(30,28,34,35),capacity=80,code='BAE305',dt='2026-10-14',start='19:00',end='21:00',merge=False,room_names=('G2207','G2209')):
    records=[]
    for cls,count in zip('DEFG',counts):
        records += [StudentRecord(f'{code}{cls}{i:04d}',f'測試{cls}{i}',f'TEST {cls} {i}',cls,code,
                                   '公司金融','應用經濟學學士學位課程（中文學制）','江宇','synthetic.xlsx') for i in range(count)]
    m.import_records(records)
    c=next(c for c in m.courses() if c['code']==code)
    m.save_course(dict(code=code,name_cn='公司金融',name_en='Corporate Finance',teachers='江宇',
                      programme='應用經濟學學士學位課程（中文學制）',programme_en='Bachelor of Applied Economics Programme (Chinese)'),c['id'])
    rooms=[]
    for name in room_names:
        old=next((r for r in m.rooms() if r['name']==name),None)
        rooms.append(old['id'] if old else m.save_room(dict(name=name,capacity=capacity,enabled=1,usable_seats='')))
    b=m.save_batch(dict(name='2026–2027 期中考試',academic_year='2026–2027',semester='第一學期',exam_type='期中'))
    sid=m.create_session(b,c['id'],dict(date=dt,start=start,end=end,teachers='江宇、王璐',intake='2026-08',allow_merge=merge),
                         [cl['id'] for cl in m.classes(c['id'])],rooms)
    return sid,{c['name']:c['id'] for c in m.classes(c['id'])},{a['room_name']:a['id'] for a in m.allocations(sid)}


def assign_four(m,sid,classes,rooms):
    for cls in 'DEFG':m.assign(rooms['G2209' if cls in 'DF' else 'G2207'],classes[cls])

from datetime import datetime,timezone
import json
from pathlib import Path
import re
import unicodedata
import pytest
from pypdf import PdfReader
from app.models.records import StudentRecord,ValidationError
from app.services.papers import PaperManager,default_settings
from app.exporters.papers import PaperExporter
from app.exporters import paper_pdf
from conftest import setup_exam

pytestmark=pytest.mark.usefixtures('qapp')


def text(path):
    return unicodedata.normalize('NFKC',PdfReader(path).pages[0].extract_text())


def four_rooms(manager):
    counts={'3B':32,'3C':30,'3D':28,'3F':30,'3G':5,'3H':6,'3I':4,'3J':3}
    records=[StudentRecord(f'PROOF{name}{i:03d}','示例','EXAMPLE',name,'BAE303',
                          '金融經濟學導論',teachers='示例教師',administrative_class='A')
             for name,count in counts.items() for i in range(count)]
    manager.import_records(records);course=manager.courses()[0]
    manager.save_course(dict(code=course['code'],name_cn=course['name_cn'],name_en='Introductory Financial Economics'),course['id'])
    batch=manager.save_batch(dict(academic_year='2026–2027',semester='第一學期',exam_type='期末',name='測試考試'))
    names=('G2108','G2110','G2112','G2114')
    room_ids=[manager.save_room(dict(name=name,capacity=80,enabled=1)) for name in names]
    classes={c['name']:c['id'] for c in manager.classes(course['id'])}
    sid=manager.create_session(batch,course['id'],dict(date='2026-12-03',start='19:00',end='21:00',teachers='示例教師'),
                               list(classes.values()),room_ids)
    for allocation,groups in zip(manager.allocations(sid),(('3B','3C'),('3D','3F'),('3G','3H'),('3I','3J'))):
        for name in groups:manager.assign(allocation['id'],classes[name])
    return sid


def test_fixed_review_and_four_independent_bag_pdfs(manager,tmp_path,monkeypatch):
    sid=four_rooms(manager)
    settings=default_settings();settings.update(sender='OLD_SENDER_MUST_NOT_PRINT',submission_date='1999-01-01')
    PaperManager(manager).save(sid,settings)
    monkeypatch.setattr('app.exporters.papers.generation_date',lambda:'2030-02-03')
    bundle=PaperExporter(manager).generate(sid,tmp_path,['review','bag'])
    review=text(bundle/'附件一_試卷評審記錄.pdf')
    assert 'Calvan' in review and 'BAECF' in review and '2030-02-03' in review
    assert 'IntroductoryFinancialEconomics' in ''.join(review.split())
    assert 'OLD_SENDER_MUST_NOT_PRINT' not in review and '1999-01-01' not in review
    assert '應用經濟學學士學位課程' not in review
    expected={'G2108':(62,[(32,'3B'),(30,'3C')]),'G2110':(58,[(28,'3D'),(30,'3F')]),
              'G2112':(11,[(5,'3G'),(6,'3H')]),'G2114':(7,[(4,'3I'),(3,'3J')])}
    assert len(list(bundle.glob('附件三*.pdf')))==4
    for room,(total,groups) in expected.items():
        path=bundle/f'附件三_試卷袋封面_{room}.pdf';reader=PdfReader(path);content=text(path)
        assert len(reader.pages)==1 and list(map(float,reader.pages[0].mediabox))==[0,0,595.32,841.92]
        assert room in content and content.rstrip().splitlines()[-1]==str(total)
        assert '2026-12-03' in content
        for count,name in groups:assert f'{count}({name})' in ''.join(content.split())
        for count,name in groups:assert f'{count}+1({name})' in ''.join(content.split())
        assert f'={total+len(groups)}' in ''.join(content.split())
        for other in expected:
            if other!=room:assert other not in content
        assert not re.search(r'\(\s*A\s*\)',content)
    manifest=json.loads((bundle/'文件校驗.json').read_text())
    assert manifest['generated_date']=='2030-02-03'
    assert sum(room['count'] for room in manifest['rooms'])==138
    assert sum(room['print_copies'] for room in manifest['rooms'])==146
    assert not list(bundle.glob('*.xlsx')) and not list(bundle.glob('附件二*'))


def test_split_class_counts_follow_current_room_after_move(manager,tmp_path):
    sid,classes,rooms=setup_exam(manager,(4,))
    students=manager.pending(sid)
    manager.assign(rooms['G2207'],classes['D'],[s['student_id'] for s in students[:2]])
    manager.assign(rooms['G2209'],classes['D'])
    first=PaperExporter(manager).generate(sid,tmp_path,['bag'])
    assert text(first/'附件三_試卷袋封面_G2207.pdf').rstrip().splitlines()[-1]=='2'
    manager.move_students([manager.assigned(aid=rooms['G2207'])[0]['id']],rooms['G2209'])
    second=PaperExporter(manager).generate(sid,tmp_path,['bag'])
    for room,count in [('G2207',1),('G2209',3)]:
        content=text(second/f'附件三_試卷袋封面_{room}.pdf')
        assert content.rstrip().splitlines()[-1]==str(count)
        assert re.search(rf'{count}\s*\(\s*D\s*\)',content)
        spares=1 if room=='G2207' else 0
        assert f'{count}+{spares}(D)' in ''.join(content.split())
        assert f'={count+spares}' in ''.join(content.split())
    rooms=PaperManager(manager).context(sid)['rooms']
    assert sum(r['print_copies'] for r in rooms)==5
    assert first!=second and first.exists()
    manager.move_students([s['id'] for s in manager.assigned(aid=rooms[0]['allocation_id'])],rooms[1]['allocation_id'])
    third=PaperExporter(manager).generate(sid,tmp_path,['bag'])
    assert [p.name for p in third.glob('*.pdf')]==['附件三_試卷袋封面_G2209.pdf']
    assert '4+1(D)' in ''.join(text(third/'附件三_試卷袋封面_G2209.pdf').split())


def test_empty_allocated_room_has_no_bag_pdf(manager,tmp_path):
    sid,classes,rooms=setup_exam(manager,(2,))
    manager.assign(rooms['G2207'],classes['D'])
    output=PaperExporter(manager).generate(sid,tmp_path,['bag'])
    assert [p.name for p in output.glob('*.pdf')]==['附件三_試卷袋封面_G2207.pdf']


def test_pdf_does_not_depend_on_pillow_bridge(manager,tmp_path,monkeypatch):
    import openpyxl.drawing.image
    sid,classes,rooms=setup_exam(manager,(2,));manager.assign(rooms['G2207'],classes['D'])
    monkeypatch.setattr(openpyxl.drawing.image,'PILImage',None)
    output=PaperExporter(manager).generate(sid,tmp_path,['review','bag'])
    assert len(list(output.glob('*.pdf')))==2


def test_generation_date_uses_macau_taipei_date_at_utc_boundary(monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):return datetime(2026,11,11,17,30,tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(paper_pdf,'datetime',Clock)
    assert paper_pdf.generation_date()=='2026-11-12'


def test_review_requires_english_course_name_before_creating_output(manager,tmp_path):
    sid=four_rooms(manager)
    course=manager.courses()[0];manager.save_course(dict(code=course['code'],name_cn=course['name_cn'],name_en=''),course['id'])
    output=tmp_path/'not_created'
    with pytest.raises(ValidationError,match='科目英文名稱'):PaperExporter(manager).generate(sid,output,['review'])
    assert not output.exists()


def test_missing_pdf_template_fails_before_creating_output(manager,tmp_path,monkeypatch):
    sid,_,_=setup_exam(manager,(1,));folder=tmp_path/'not_created'
    monkeypatch.setattr(paper_pdf,'pdf_template',lambda name:tmp_path/'missing.pdf')
    with pytest.raises(ValidationError,match='完整解壓'):PaperExporter(manager).generate(sid,folder,['review'])
    assert not folder.exists()


def test_long_class_breakdown_is_fitted_without_changing_page(qapp,tmp_path):
    info=dict(code='BAE303',name_cn='金融經濟學導論',faculty='金融學院',date='2026-12-03',start='19:00',end='21:00')
    room=dict(name='展覽廳',count=270,classes=[dict(name='3'+c,count=30,spares=1) for c in 'ABCDEFGHI'])
    path=tmp_path/'hall.pdf';paper_pdf.write_form(path,'bag',paper_pdf.bag_fields(info,room))
    content=text(path)
    assert content.rstrip().splitlines()[-1]=='270'
    for c in 'ABCDEFGHI':assert f'30(3{c})' in ''.join(content.split())
    assert '=279' in ''.join(content.split())


def test_later_failure_does_not_publish_partial_batch_or_replace_existing(manager,tmp_path,monkeypatch):
    sid=four_rooms(manager);exporter=PaperExporter(manager)
    first=exporter.generate(sid,tmp_path,['review']);original=(first/'附件一_試卷評審記錄.pdf').read_bytes()
    from app.exporters import papers
    real=papers.write_form
    def fail(path,template,fields):
        if 'G2110' in path.name:raise OSError('disk failure')
        return real(path,template,fields)
    monkeypatch.setattr(papers,'write_form',fail)
    with pytest.raises(OSError,match='disk failure'):exporter.generate(sid,tmp_path,['review','bag'])
    assert (first/'附件一_試卷評審記錄.pdf').read_bytes()==original
    assert list(tmp_path.glob('BAE303_*'))==[first] and not list(tmp_path.glob('.fof-paper-*'))

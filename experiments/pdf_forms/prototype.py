"""Feasibility samples: preserve original PDF pages; no Excel round-trip."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/fof-qt-cache')
from pathlib import Path
from io import BytesIO
from xml.etree import ElementTree as ET
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QSizeF,QMarginsF,QRectF
from PySide6.QtGui import QPdfWriter,QPageSize,QPageLayout,QPainter,QFont,QFontMetricsF
from pypdf import PdfReader,PdfWriter
from pypdf.generic import (NameObject,TextStringObject,BooleanObject,DictionaryObject,
                          DecodedStreamObject,ArrayObject,FloatObject)
import sys
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.exporters.paper_forms import review_page,bag_page

ROOT=None
SOURCES={}
INFO=dict(faculty='金融學院',programme='應用經濟學學士學位課程（中文學制）',
          programme_en='Bachelor of Applied Economics Programme (Chinese)',
          code='BAE303',name_cn='金融經濟學導論',name_en='Introductory Financial Economics',
          teachers='示例教師',date='2026-12-03',start='19:00',end='21:00')


def overlay(path,width,height,fields):
    pdf=QPdfWriter(str(path));pdf.setResolution(72)
    size=QPageSize(QSizeF(width,height),QPageSize.Unit.Point,'Original',QPageSize.SizeMatchPolicy.ExactMatch)
    pdf.setPageLayout(QPageLayout(size,QPageLayout.Orientation.Portrait,QMarginsF(0,0,0,0),QPageLayout.Unit.Point))
    painter=QPainter(pdf)
    try:
        for label,value,box,points,align,white in fields:
            value=str(value)
            if not value:continue
            rect=QRectF(*box);painter.save();painter.setClipRect(rect)
            if white:painter.fillRect(rect,Qt.GlobalColor.white)
            font=QFont();font.setFamilies(['新細明體','PMingLiU','Noto Serif CJK TC','Noto Sans CJK TC'])
            flags=Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap
            flags|={'ctr':Qt.AlignmentFlag.AlignHCenter,'r':Qt.AlignmentFlag.AlignRight}.get(align,Qt.AlignmentFlag.AlignLeft)
            while points>=5:
                font.setPointSizeF(points);fm=QFontMetricsF(font,pdf)
                if fm.boundingRect(rect,flags,value).height()<=rect.height()+0.05:break
                points-=0.25
            painter.setFont(font);painter.setPen(Qt.GlobalColor.black);painter.drawText(rect,flags,value)
            painter.restore()
    finally:painter.end()
    del pdf


def flat_sample(number,fields,filename):
    writer=PdfWriter(clone_from=SOURCES[number]);page=writer.pages[0]
    temporary=ROOT/f'overlay-{number}.pdf'
    overlay(temporary,float(page.mediabox.width),float(page.mediabox.height),fields)
    page.merge_page(PdfReader(temporary).pages[0],over=True,expand=False)
    writer.write(ROOT/filename)


def xfa_sample():
    reader=PdfReader(SOURCES[2]);writer=PdfWriter(SOURCES[2],incremental=True)
    values={'學院名稱_中[0]':'金融學院','學院名稱_英[0]':'Faculty of Finance',
            '課程名稱_中[0]':INFO['programme'],'課程名稱_英[0]':INFO['programme_en'],
            '學年[0]':'2026/2027','學年_英[0]':'2026/2027','科目代碼[0]':INFO['code'],
            '科目名稱[0]':INFO['name_cn'],'導師名稱[0]':INFO['teachers'],
            '頁數[0]':'10','日期[0]':INFO['date'],'日期[1]':'19:00–21:00',
            '學院簡稱[0]':'FOF','課程簡稱[0]':'BAECF','年份[0]':'26','月份[0]':'12'}
    page=writer.pages[0];height=float(page.mediabox.height);fields=[]
    for ref in page['/Annots']:
        obj=ref.get_object();name=str(obj.get('/T',''))
        if name not in values:continue
        rect=list(map(float,obj['/Rect']));x0,y0,x1,y1=rect
        points=14 if name.startswith('學院名稱') else 12
        fields.append((name,values[name],(x0,height-y1,x1-x0,y1-y0),points,'ctr',True))
    temporary=ROOT/'overlay-xfa.pdf';overlay(temporary,float(page.mediabox.width),height,fields)
    stamp=PdfReader(temporary).pages[0]
    # Form appearances are actual PDF vector text with embedded CJK fonts.
    resources=stamp['/Resources'].clone(writer)
    content=stamp.get_contents().get_data()
    for ref in page['/Annots']:
        obj=ref.get_object();name=str(obj.get('/T',''))
        if name not in values:continue
        obj[NameObject('/V')]=TextStringObject(values[name]);obj.pop('/RV',None)
        x0,y0,x1,y1=map(float,obj['/Rect']);w,h=x1-x0,y1-y0
        appearance=DecodedStreamObject()
        appearance.set_data((f'q 1 1 1 rg 0 0 {w} {h} re f 1 0 0 1 {-x0} {-y0} cm\n'.encode()+content+b'\nQ'))
        appearance.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
            NameObject('/BBox'):ArrayObject([FloatObject(v) for v in (0,0,w,h)]),NameObject('/Resources'):resources})
        obj[NameObject('/AP')]=DictionaryObject({NameObject('/N'):writer._add_object(appearance)})
    acro=writer.root_object['/AcroForm'];acro[NameObject('/NeedAppearances')]=BooleanObject(False)
    packets=acro['/XFA'];xml_values={k.rsplit('[',1)[0]:[] for k in values}
    for k,v in values.items():xml_values[k.rsplit('[',1)[0]].append(v)
    xml_values['CheckBox1']=['1','0']
    for index in range(0,len(packets),2):
        if str(packets[index])!='datasets':continue
        root=ET.fromstring(packets[index+1].get_object().get_data());counts={}
        for node in root.iter():
            name=node.tag.rsplit('}',1)[-1]
            if name not in xml_values:continue
            occurrence=counts.get(name,0);counts[name]=occurrence+1
            if occurrence<len(xml_values[name]):node.text=xml_values[name][occurrence]
        stream=DecodedStreamObject();stream.set_data(ET.tostring(root,encoding='utf8',xml_declaration=True))
        packets[index+1]=writer._add_object(stream)
    for ref in page['/Annots']:
        obj=ref.get_object();name=str(obj.get('/T',''))
        if name.startswith('CheckBox1'):
            states=[str(k) for k in obj['/AP']['/N'] if str(k)!='/Off']
            state=states[0] if name=='CheckBox1[0]' and states else '/Off'
            obj[NameObject('/V')]=NameObject(state);obj[NameObject('/AS')]=NameObject(state)
    writer.write(ROOT/'附件二_XFA原欄位填寫_待Adobe驗證.pdf')


def cover_print_copy():
    """Print-only derivative of this blank template, not an approved cover."""
    writer=PdfWriter(clone_from=ROOT/'附件二_XFA原欄位填寫_待Adobe驗證.pdf')
    page=writer.pages[0];resources=page['/Resources']
    if '/XObject' not in resources:resources[NameObject('/XObject')]=DictionaryObject()
    commands=[]
    for i,ref in enumerate(page['/Annots']):
        obj=ref.get_object()
        if obj.get('/Subtype')!='/Widget':continue
        normal=obj['/AP']['/N']
        if not hasattr(normal,'get_data'):normal=normal[obj.get('/AS','/Off')].get_object()
        if list(normal.get('/Matrix',[1,0,0,1,0,0]))!=[1,0,0,1,0,0]:
            raise ValueError('Sample flattener expects unrotated official widgets.')
        bx,by,bx1,by1=map(float,normal['/BBox']);x,y,x1,y1=map(float,obj['/Rect'])
        sx=(x1-x)/(bx1-bx);sy=(y1-y)/(by1-by)
        key=NameObject(f'/OfficialField{i}');resources['/XObject'][key]=writer._add_object(normal)
        commands.append(f'q 1 1 1 rg {x} {y} {x1-x} {y1-y} re f '
                        f'{sx} 0 0 {sy} {x-bx*sx} {y-by*sy} cm {key} Do Q')
    content=DecodedStreamObject();content.set_data(page.get_contents().get_data()+b'\n'+'\n'.join(commands).encode())
    page[NameObject('/Contents')]=writer._add_object(content)
    writer.remove_annotations(subtypes='/Widget')
    # This separate ordinary PDF does not claim the original Reader extension
    # signature. The incrementally filled original remains available separately.
    for key in ('/AcroForm','/Perms','/OpenAction','/AA'):writer.root_object.pop(key,None)
    names=writer.root_object.get('/Names')
    if names:names.get_object().pop('/JavaScript',None)
    writer.write(ROOT/'附件二_普通PDF列印副本_示例.pdf')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--templates-dir',type=Path,required=True,help='Folder containing original Annex 1/2/3 PDFs')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    ROOT=args.output_dir;ROOT.mkdir(parents=True,exist_ok=True)
    SOURCES={n:next(args.templates_dir.rglob(f'Annex {n}*.pdf')) for n in (1,2,3)}
    APP=QApplication.instance() or QApplication([])
    fields=review_page(INFO,dict(sender='示例送審人',submission_date='2026-11-11'))[2]
    fields[0]=('學院','金融',(420.55,28,107,17),11,'r',False)
    fields[1]=('課程',INFO['programme'],(364,46,164,18),7,'r',False)
    flat_sample(1,fields,'附件一_直接填入原PDF_示例.pdf')
    flat_sample(3,bag_page(INFO,dict(name='展覽廳',count=273))[2],'附件三_直接填入原PDF_示例.pdf')
    xfa_sample()
    cover_print_copy()
    print('Samples generated')

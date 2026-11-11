"""Official page artwork with editable, cell-linked Excel text boxes.

The background is an unchanged rendering of the supplied official PDF, so
logos, borders and OMR areas retain their relative positions. Values are
editable on the 資料 sheet; the drawing textlink points to those cells.
"""
from pathlib import Path
import sys
from zipfile import ZipFile,ZIP_DEFLATED
from xml.etree import ElementTree as ET
from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.drawing.spreadsheet_drawing import AbsoluteAnchor,XDRPoint2D,XDRPositiveSize2D
from openpyxl.styles import Font,Alignment
from openpyxl.worksheet.page import PageMargins
from app.templates.engine import write_text

X='http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
ET.register_namespace('xdr',X);ET.register_namespace('a',A)
EMU=12700


def artwork(name):
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
    return root/'resources'/'exam_forms'/(name+'.png')


def text_shape(parent,index,cell,text,box,size=12,align='l',white=False,east_asian='新細明體'):
    x,y,w,h=box
    anchor=ET.SubElement(parent,f'{{{X}}}absoluteAnchor')
    ET.SubElement(anchor,f'{{{X}}}pos',x=str(round(x*EMU)),y=str(round(y*EMU)))
    ET.SubElement(anchor,f'{{{X}}}ext',cx=str(round(w*EMU)),cy=str(round(h*EMU)))
    shape=ET.SubElement(anchor,f'{{{X}}}sp',textlink=f"'資料'!$B${cell}")
    nv=ET.SubElement(shape,f'{{{X}}}nvSpPr')
    ET.SubElement(nv,f'{{{X}}}cNvPr',id=str(index),name=f'欄位_{cell}')
    ET.SubElement(nv,f'{{{X}}}cNvSpPr',txBox='1')
    props=ET.SubElement(shape,f'{{{X}}}spPr')
    geom=ET.SubElement(props,f'{{{A}}}prstGeom',prst='rect');ET.SubElement(geom,f'{{{A}}}avLst')
    if white:
        fill=ET.SubElement(props,f'{{{A}}}solidFill');ET.SubElement(fill,f'{{{A}}}srgbClr',val='FFFFFF')
    else:ET.SubElement(props,f'{{{A}}}noFill')
    line=ET.SubElement(props,f'{{{A}}}ln');ET.SubElement(line,f'{{{A}}}noFill')
    body=ET.SubElement(shape,f'{{{X}}}txBody')
    body_props=ET.SubElement(body,f'{{{A}}}bodyPr',wrap='square',lIns='0',rIns='0',tIns='0',bIns='0',anchor='ctr')
    ET.SubElement(body_props,f'{{{A}}}normAutofit')
    ET.SubElement(body,f'{{{A}}}lstStyle')
    for part in str(text or '').split('\n'):
        p=ET.SubElement(body,f'{{{A}}}p');ET.SubElement(p,f'{{{A}}}pPr',algn=align)
        run=ET.SubElement(p,f'{{{A}}}r');rp=ET.SubElement(run,f'{{{A}}}rPr',sz=str(round(size*100)),lang='zh-TW')
        ET.SubElement(rp,f'{{{A}}}latin',typeface='Times New Roman')
        ET.SubElement(rp,f'{{{A}}}ea',typeface=east_asian)
        ET.SubElement(run,f'{{{A}}}t').text=part
        ET.SubElement(p,f'{{{A}}}endParaRPr',sz=str(round(size*100)))
    ET.SubElement(anchor,f'{{{X}}}clientData',fPrintsWithSheet='1')


def form_workbook(path,pages):
    """pages: (sheet name, background name, [(label,value,box,size,align)])."""
    wb=Workbook();data=wb.active;data.title='資料'
    data.append(['欄位（按表格分組）','可修改的內容'])
    data['D1']='修改B欄會更新列印表格；亦可直接選取列印頁文字框修改。只列印官方表格頁，不列印本資料頁。'
    data.column_dimensions['A'].width=42;data.column_dimensions['B'].width=66;data.column_dimensions['D'].width=70
    overlays=[]
    for title,background,fields in pages:
        sheet=wb.create_sheet(title[:31]);sheet.sheet_view.showGridLines=False
        sheet.column_dimensions['A'].width=112.68
        for row in range(1,113):sheet.row_dimensions[row].height=841.92/112
        sheet.page_setup.paperSize=sheet.PAPERSIZE_A4;sheet.page_setup.orientation='portrait'
        sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=1;sheet.page_setup.scale=None
        sheet.sheet_properties.pageSetUpPr.fitToPage=True
        sheet.page_margins=PageMargins(left=0,right=0,top=0,bottom=0,header=0,footer=0)
        sheet.print_area='A1:A112'
        img=Image(artwork(background))
        img.anchor=AbsoluteAnchor(pos=XDRPoint2D(0,0),ext=XDRPositiveSize2D(round(595.32*EMU),round(841.92*EMU)))
        sheet.add_image(img)
        overlay=[]
        for label,value,box,size,align,white in fields:
            row=data.max_row+1;write_text(data.cell(row,1),title+' · '+label)
            if isinstance(value,(int,float)):data.cell(row,2).value=value
            else:write_text(data.cell(row,2),value)
            data.cell(row,2).font=Font(name='新細明體',size=12)
            data.cell(row,2).alignment=Alignment(wrap_text=True,vertical='center');data.row_dimensions[row].height=30
            overlay.append((row,value,box,size,align,white))
        overlays.append((background,overlay))
    wb.calculation.forceFullCalc=True;wb.active=1;wb.save(path);wb.close()
    # openpyxl does not serialize text boxes; add schema-valid DrawingML after
    # its image relationships have been written. Never re-save with openpyxl.
    with ZipFile(path) as source:contents={n:source.read(n) for n in source.namelist()}
    for i,(background,overlay) in enumerate(overlays,1):
        key=f'xl/drawings/drawing{i}.xml';root=ET.fromstring(contents[key])
        for j,(row,value,box,size,align,white) in enumerate(overlay,2):
            text_shape(root,j,row,value,box,size,align,white,'標楷體' if background=='cover' else '新細明體')
        contents[key]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    with ZipFile(path,'w',ZIP_DEFLATED) as target:
        for name,value in contents.items():target.writestr(name,value)


def field(label,value,x,y,w,h=18,size=12,align='l',white=False):
    return (label,value,(x,y,w,h),size,align,white)


def review_page(info,settings):
    year,month,day=info['date'].split('-')
    return ('試卷評審記錄','review',[
        field('學院',info['faculty'].removesuffix('學院'),423,27,112,16,11,'r'),
        field('課程',info['programme'],400,45,154,21,8,'r',True),
        field('送審人',settings['sender'],374,66,160),field('送審日期',settings['submission_date'],374,85,160),
        field('科目編號',info['code'],140,133,94),field('任課教師',info['teachers'],309,133,220),
        field('科目名稱',info['name_cn'],140,158,395),
        field('年',year,141,183,51,18,12,'ctr'),field('月',month,211,183,34,18,12,'ctr'),
        field('日',day,265,183,34,18,12,'ctr'),field('考試時間',info['start']+'–'+info['end'],392,183,145)])


def bag_page(info,room):
    return (room['name'][:24]+'試卷袋','bag',[
        field('科目',info['code']+' '+info['name_cn'],117,202,230,31),
        field('院系',info['faculty'],117,240,230,29),
        field('考場',room['name'],117,276,153,29),field('試卷編號','',398,276,139,29),
        field('日期',info['date'],117,312,151,29),field('時間',info['start']+'–'+info['end'],316,312,221,29),
        field('應考人數',room['count'],158,349,103,29),
        field('印刷份數','',390,210,42,48),field('使用份數','',477,202,59,31),field('未用份數','',477,240,59,29),
        field('實考人數','',313,349,88,29),field('缺考人數','',449,349,87,29),
        field('現場情況／建議','',118,394,413,290),field('主監考','',111,690,170,26),field('副監考','',341,690,192,26)])


def cover_page(info,settings,language,classes):
    en=language=='en';config=settings[language]
    title=info['name_en'] if en else info['name_cn']
    return (('英文' if en else '中文')+'試題封面','cover',[
        field('學院／課程',info['faculty']+'\n'+(info['programme_en'] if en else info['programme']),112,165,450,45,12,'ctr'),
        field('授課班','、'.join(classes),122,219,430,24,12,'ctr'),
        field('學年度',info['academic_year'].replace('–','/'),194,263,104,20,16,'r'),
        field('Academic Year',info['academic_year'].replace('–','/'),176,287,104,18,12,'r'),
        field('考試類型',info['exam_type'],236,306,37,22,16,'r'),
        field('Examination type',{'期中':'Midterm','期末':'Final'}.get(info['exam_type'],info['exam_type']),155,332,89,20,14,'r'),
        field('科目編號',info['code'],120,354,440,18,14,'ctr'),field('科目名稱',title,120,372,440,18,12,'ctr'),
        field('任課教師',info['teachers'],352,390,221,22),
        field('總頁數（含封面）',int(config['pages'])+1,249,423,91,24),
        field('考試日期',info['date'],177,444,160,24),field('考試時間',info['start']+'–'+info['end'],177,466,160,24),
        field('開閉卷標記','✓',354,426 if settings['book']=='closed' else 454,16,20,16,'ctr')])

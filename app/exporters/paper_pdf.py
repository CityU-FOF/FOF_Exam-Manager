"""Fill the original official PDF pages without rescaling or rasterizing them."""
from datetime import datetime,timedelta,timezone
from io import BytesIO
from pathlib import Path
import sys
from PySide6.QtCore import QBuffer,QIODevice,QMarginsF,QRectF,QSizeF,Qt
from PySide6.QtGui import QFont,QFontMetricsF,QGuiApplication,QPageLayout,QPageSize,QPainter,QPdfWriter
from pypdf import PdfReader,PdfWriter
from app.models.records import ValidationError

REVIEW_SENDER='Calvan'
REVIEW_PROGRAMME='BAECF'


def generation_date():
    # Macau/Taipei civil date, including when a cloud host uses UTC.
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def pdf_template(name):
    if name not in ('review','bag'):raise ValidationError('未支援的官方PDF模板。')
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
    return root/'resources'/'exam_forms'/(name+'.pdf')


def load_template(name):
    try:
        reader=PdfReader(pdf_template(name))
        if reader.is_encrypted or len(reader.pages)!=1:raise ValueError('Expected one unencrypted page')
        page=reader.pages[0]
        if page.rotation or list(map(float,page.mediabox))!=[0.0,0.0,595.32,841.92]:
            raise ValueError('Unexpected page dimensions')
        return reader
    except Exception as exc:
        raise ValidationError('無法讀取官方PDF模板，請完整解壓新版程式：'+str(pdf_template(name))) from exc


def field(label,value,x,y,w,h=18,size=12,align='l'):
    return label,str(value),(x,y,w,h),size,align


def review_fields(info,generated_date):
    year,month,day=info['date'].split('-')
    english=info.get('name_en','').strip()
    if not english:raise ValidationError('附件一需要科目英文名稱，請在「科目管理」補齊。')
    return [field('學院',info['faculty'].removesuffix('學院'),420.55,28,107,17,11,'r'),
        field('課程',REVIEW_PROGRAMME,420.91,48,107,17,11,'r'),
        field('送審人',REVIEW_SENDER,374,66,160),
        field('送審日期',generated_date,374,85,160),
        field('科目編號',info['code'],140,133,94),
        field('任課教師',info['teachers'],309,133,220),
        field('科目名稱',info['name_cn'],140,158,395),
        field('科目英文名稱',english,140,176.5,395,11.5,9.5),
        field('年',year,141,183,51,18,12,'ctr'),
        field('月',month,211,183,34,18,12,'ctr'),
        field('日',day,265,183,34,18,12,'ctr'),
        field('考試時間',info['start']+'–'+info['end'],392,183,145)]


def bag_fields(info,room):
    groups=room['classes']
    if sum(g['count'] for g in groups)!=room['count']:
        raise ValidationError('考場班級人數與應考總數不一致，請重新檢查編排。')
    breakdown=', '.join(f'{g["count"]}\u00a0({g["name"]})' for g in groups)
    copies=room['count']+sum(g['spares'] for g in groups)
    printing='\n'.join([f'{g["count"]}+{g["spares"]}\u00a0({g["name"]})' for g in groups]+[f'={copies}'])
    return [field('科目',info['code']+' '+info['name_cn'],117,202,230,32),
        field('院系',info['faculty'],117,240,230,29),
        field('考場',room['name'],117,276,153,29),
        field('日期',info['date'],117,312,151,29),
        field('時間',info['start']+'–'+info['end'],316,312,221,29),
        field('班級及人數',breakdown,181,349,84,29,9.5),
        field('印刷份數',printing,398.5,202,39.5,70,10),
        field('應考人數',room['count'],158,349,21,29)]


def text_overlay(width,height,fields):
    if QGuiApplication.instance() is None:
        raise ValidationError('請從「啟動程式」開啟系統後生成PDF。')
    buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pdf=QPdfWriter(buffer);pdf.setResolution(72)
    size=QPageSize(QSizeF(width,height),QPageSize.Unit.Point,'Official',QPageSize.SizeMatchPolicy.ExactMatch)
    layout=QPageLayout(size,QPageLayout.Orientation.Portrait,QMarginsF(0,0,0,0),QPageLayout.Unit.Point)
    if not pdf.setPageLayout(layout):raise ValidationError('無法設定原PDF頁面尺寸。')
    painter=QPainter(pdf)
    if not painter.isActive():raise ValidationError('無法建立PDF文字層。')
    try:
        for label,value,box,points,align in fields:
            if not value:continue
            rect=QRectF(*box)
            font=QFont();font.setFamilies(['Times New Roman','Liberation Serif','新細明體','PMingLiU',
                                         'Microsoft JhengHei','Noto Serif CJK TC','Noto Sans CJK TC'])
            flags=Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap
            flags|={'ctr':Qt.AlignmentFlag.AlignHCenter,'r':Qt.AlignmentFlag.AlignRight}.get(align,Qt.AlignmentFlag.AlignLeft)
            fits=False
            while points>=6:
                font.setPointSizeF(points);bounds=QFontMetricsF(font,pdf).boundingRect(rect,flags,value)
                if bounds.height()<=rect.height()+0.05 and bounds.width()<=rect.width()+0.05:
                    fits=True;break
                points-=0.25
            if not fits:raise ValidationError(label+'內容太長，無法完整放入原表格；請縮短相關文字後再生成。')
            painter.save();painter.setClipRect(rect);painter.setFont(font)
            painter.setPen(Qt.GlobalColor.black);painter.drawText(rect,flags,value);painter.restore()
    finally:painter.end()
    del pdf
    data=bytes(buffer.data());buffer.close()
    return data


def write_form(path,template,fields):
    reader=load_template(template);writer=PdfWriter(clone_from=reader);page=writer.pages[0]
    original_box=list(page.mediabox)
    overlay=PdfReader(BytesIO(text_overlay(float(page.mediabox.width),float(page.mediabox.height),fields)))
    page.merge_page(overlay.pages[0],over=True,expand=False)
    if list(page.mediabox)!=original_box:raise ValidationError('PDF頁面尺寸已改動，停止輸出。')
    writer.write(path)

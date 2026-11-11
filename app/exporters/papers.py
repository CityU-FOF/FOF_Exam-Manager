import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import math
from openpyxl import Workbook
from openpyxl.styles import Font,Alignment
from app.services.papers import PaperManager,LANGUAGES,print_quantities
from app.models.records import ValidationError
from app.templates.engine import write_text
from app.exporters.paper_forms import form_workbook,review_page,bag_page,cover_page


def statistics_workbook(path,context,statistics):
    wb=Workbook();ws=wb.active;ws.title='印刷統計'
    ws.append(['科目',context['info']['code']+' '+context['info']['name_cn']])
    ws.append(['考試日期',context['info']['date']])
    ws.append(['計算規則','每班後備1份；內容雙面，封面另佔1張單面。獨立公式表分開計。'])
    ws.append(['卷別','學生人數','授課班數','後備份數','印刷份數','內容頁數','每份封面頁數','每份試卷用紙','試卷用紙','獨立公式表用紙','合計張數'])
    keys=['label','students','classes','spares','copies','pages','cover_pages','sheets_per_copy','paper_sheets','formula_sheets','total_sheets']
    for row in statistics['rows']:ws.append([row[k] for k in keys])
    ws.append(['整批用紙（張）',statistics['total_sheets']])
    ws.append(['包裝規格',f'{statistics["sheets_per_ream"]}張／令，{statistics["reams_per_box"]}令／箱'])
    ws.append(['約需整令',statistics['reams']]);ws.append(['約需整箱',statistics['boxes']])
    ws.append(['精確用紙分解',f'{statistics["full_reams"]}令 {statistics["loose_sheets"]}張'])
    ws.append(['說明','以上為生成時的數量快照；變更頁數或份數請在程式重新計算。按整批總張數取整包裝，不逐科取整。'])
    ws.append([]);ws.append(['授課班','卷別','學生人數','每班後備'])
    for group in context['groups']:ws.append([group['name'],LANGUAGES[group['language']],group['students'],1])
    for row in ws:
        for c in row:
            if isinstance(c.value,str):write_text(c,c.value)
            c.font=Font(name='新細明體',size=11);c.alignment=Alignment(vertical='center',wrap_text=True)
    for key in 'ABCDEFGHIJK':ws.column_dimensions[key].width=18
    ws.column_dimensions['A'].width=24;ws.row_dimensions[3].height=32
    ws.freeze_panes='A5';ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0;ws.sheet_properties.pageSetUpPr.fitToPage=True
    wb.save(path);wb.close()


class PaperExporter:
    def __init__(self,manager):self.manager=manager;self.papers=PaperManager(manager)

    def batch_statistics(self,sids,folder):
        sids=list(dict.fromkeys(sids))
        if not sids:raise ValidationError('請選擇要統計的科目場次。')
        collected=[];packages=set()
        for sid in sids:
            context=self.papers.context(sid);settings=self.papers.settings(sid)
            try:stats=print_quantities(context['groups'],settings)
            except ValidationError as exc:raise ValidationError(context['info']['code']+'：'+str(exc)) from exc
            collected.append((context,stats));packages.add((stats['sheets_per_ream'],stats['reams_per_box']))
        if len(packages)!=1:raise ValidationError('選中科目的每令／每箱規格不同，請先統一A4包裝規格。')
        wb=Workbook();ws=wb.active;ws.title='多科印刷總表'
        ws.append(['科目','日期','卷別','人數','班數／後備','份數','內容頁數','每份試卷用紙','試卷用紙','公式表用紙','合計張數'])
        for context,stats in collected:
            for r in stats['rows']:
                ws.append([context['info']['code']+' '+context['info']['name_cn'],context['info']['date'],r['label'],r['students'],r['classes'],r['copies'],r['pages'],r['sheets_per_copy'],r['paper_sheets'],r['formula_sheets'],r['total_sheets']])
        total=sum(s['total_sheets'] for _,s in collected);ream,box=next(iter(packages))
        ws.append(['整批總張數',total]);ws.append(['A4規格',f'{ream}張／令，{box}令／箱'])
        ws.append(['約需整令',math.ceil(total/ream)]);ws.append(['約需整箱',math.ceil(total/(ream*box))])
        ws.append(['精確張數',f'{total//ream}令 {total%ream}張'])
        for row in ws:
            for cell in row:
                if isinstance(cell.value,str):write_text(cell,cell.value)
                cell.font=Font(name='新細明體',size=11);cell.alignment=Alignment(wrap_text=True,vertical='center')
        for col in 'ABCDEFGHIJK':ws.column_dimensions[col].width=18
        ws.column_dimensions['A'].width=32;ws.freeze_panes='A2'
        ws.page_setup.paperSize=ws.PAPERSIZE_A4;ws.page_setup.orientation='landscape'
        ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0;ws.sheet_properties.pageSetUpPr.fitToPage=True
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        path=folder/'多科印刷總表.xlsx';i=2
        while path.exists():path=folder/f'多科印刷總表_{i}.xlsx';i+=1
        temp=None
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx',dir=folder,delete=False) as handle:temp=Path(handle.name)
            wb.save(temp);wb.close()
            if os.name=='nt':os.rename(temp,path)
            else:os.link(temp,path);temp.unlink()
        finally:
            if temp:temp.unlink(missing_ok=True)
        return path

    def generate(self,sid,folder,kinds):
        kinds=set(kinds)
        if not kinds or not kinds<={'review','cover','bag','statistics'}:raise ValidationError('請選擇要輸出的考務文件。')
        context=self.papers.context(sid);info=context['info'];settings=self.papers.settings(sid)
        languages=[l for l in LANGUAGES if any(g['language']==l and g['students'] for g in context['groups'])]
        if not languages:raise ValidationError('此場次沒有應考學生。')
        if 'bag' in kinds and context['pending']:raise ValidationError(f'尚有 {context["pending"]} 位學生未分配考場，請先完成編排再生成試卷袋封面。')
        if 'bag' in kinds:
            errors=self.manager.validate(sid)
            if errors:raise ValidationError('試卷袋考場資料有待處理：'+'；'.join(errors))
        statistics=print_quantities(context['groups'],settings) if 'statistics' in kinds else None
        covers={}
        if 'cover' in kinds:
            if settings['approval'] not in ('required','not_required'):raise ValidationError('請先確認此科是否需要試題審批。')
            for language in languages:
                if settings['approval']=='required':covers[language]=self.papers.cover_bytes(sid,language)
                else:
                    if settings['book'] not in ('open','closed'):raise ValidationError('請選擇開卷或閉卷。')
                    if int(settings[language]['pages'])<=0:raise ValidationError(LANGUAGES[language]+'：請填內容頁數。')
                    if language=='en' and not info['name_en']:raise ValidationError('英文卷封面需要科目英文名稱，請先在科目管理補齊。')
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        base=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',f'{info["code"]}_{info["date"]}_考務文件')
        final=folder/base;counter=2
        while final.exists():final=folder/(base+f'_{counter}');counter+=1
        with tempfile.TemporaryDirectory(prefix='.fof-paper-',dir=folder) as temp:
            temp=Path(temp)
            if 'review' in kinds:form_workbook(temp/'附件一_試卷評審記錄.xlsx',[review_page(info,settings)])
            if 'bag' in kinds:
                pages=[bag_page(info,r) for r in context['rooms'] if r['count']]
                if not pages:raise ValidationError('沒有已分配學生的考場。')
                form_workbook(temp/'附件三_試卷袋封面.xlsx',pages)
            if 'cover' in kinds:
                if covers:
                    for language,data in covers.items():(temp/f'附件二_{LANGUAGES[language]}_已審批原封面.pdf').write_bytes(data)
                else:
                    pages=[cover_page(info,settings,l,[g['name'] for g in context['groups'] if g['language']==l]) for l in languages]
                    form_workbook(temp/'附件二_試題封面.xlsx',pages)
            if statistics:statistics_workbook(temp/'印刷用紙統計.xlsx',context,statistics)
            manifest=dict(course=info['code'],exam_date=info['date'],files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in temp.iterdir()})
            (temp/'文件校驗.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
            (temp/'列印及修改說明.txt').write_text('Excel：請在「資料」頁B欄修改內容，列印頁文字框已連結相應儲存格；亦可直接編輯文字框。\n只列印官方表格頁，不印「資料」頁。版面保留官方模板影像，A4直向一頁，邊界設為0（模板本身已有留白）。\n試卷袋每個考場一頁；需要多個袋時，可重複列印同一頁。實考、缺考、印刷／使用／未用及現場情況按實際情況填寫。\n已審批PDF按原位元組匯出，QR不修改。文件校驗.json可核對SHA-256。\n若以openpyxl等第三方工具重新儲存Excel，可能移除文字框；請用Microsoft Excel編輯。\n',encoding='utf8')
            os.rename(temp,final)
        return final

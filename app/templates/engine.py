import sys
from copy import copy
from datetime import datetime
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, Protection
from openpyxl.worksheet.pagebreak import Break, RowBreak
from openpyxl.worksheet.properties import PageSetupProperties


def template_path():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    return root / 'resources' / 'official_template.xlsx'


def write_text(cell, value):
    # Explicit text type prevents formula injection while preserving every character.
    cell.value = str(value or '')
    cell.data_type = 's'


class TemplateEngine:
    def render(self, info, students):
        wb = load_workbook(template_path(), keep_links=False)
        count = len(students)
        for sheet in wb:
            attendance = sheet.title == 'Attendance'
            styles = [copy(sheet.cell(18, col)._style) for col in range(1, 8)]
            for m in list(sheet.merged_cells.ranges):
                if m.min_row >= 18:
                    sheet.unmerge_cells(str(m))
            sheet.delete_rows(18, sheet.max_row-17)
            sheet.column_dimensions['G'].width = 20
            sheet.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
            sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
            sheet.page_setup.orientation = 'portrait'
            sheet.page_setup.fitToWidth = 1
            sheet.page_setup.fitToHeight = 0
            sheet.page_setup.scale = None
            sheet.print_title_rows = '1:17'
            sheet.freeze_panes = 'A18'
            # Prevent accidental header edits; Excel can unprotect without a password.
            sheet.protection.sheet = True
            sheet.protection.selectLockedCells = False
            sheet.protection.selectUnlockedCells = False
            sheet.row_breaks = RowBreak()
            year = info['academic_year']
            semester = info['semester']
            kind = info['exam_type']
            title = '考試出席表' if attendance else '考試座位表'
            eng_title = 'Attendance List' if attendance else 'Seat Plan'
            kind_en = {'期中':'Midterm','期末':'Final'}.get(kind,kind)
            semester_en = {'第一學期':'1st Semester','第二學期':'2nd Semester','第三學期':'3rd Semester'}.get(semester,semester)
            headers = {
                'A3': info.get('programme') or '應用經濟學學士學位課程（中文學制）',
                'A4': info.get('programme_en') or 'Bachelor of Applied Economics Programme (Chinese)',
                'A5': f'{year}學年{semester}{kind}{title}',
                'A6': f'{eng_title} of {year.replace("–","/").replace("-","/")} {semester_en} {kind_en} Examination',
                'A8': ' '.join(filter(None,[info['code'],info['name_cn'],info.get('name_en','')])),
                'D10':info.get('intake',''), 'E10':info['teachers'], 'D12':info['room_name'],
                'G14':f'{info["start"]}-{info["end"]}',
            }
            for pos, val in headers.items(): write_text(sheet[pos],val)
            sheet['G12'] = datetime.strptime(info['date'], '%Y-%m-%d')
            sheet['G12'].number_format = 'yyyy-mm-dd'
            sheet['D14'] = count
            sheet['D14'].font = Font(name='Times New Roman',size=12)
            sheet.row_dimensions[10].height = max(30, 15*((len(info['teachers'])//32)+1))
            sheet['E10'].alignment = Alignment(horizontal='left',vertical='center',wrap_text=True)
            if not attendance:
                sheet['C15'] = None
            for index, student in enumerate(students):
                row = 18+index
                for col in range(1,8):
                    sheet.cell(row,col)._style = copy(styles[col-1])
                    sheet.cell(row,col).protection = Protection(locked=False)
                values = {1:index+1,2:student['seat'],3:student['student_no'],4:student['chinese_name'],
                          (5 if attendance else 6):student['english_name']}
                if not attendance:
                    sheet.merge_cells(start_row=row,start_column=4,end_row=row,end_column=5)
                    sheet.merge_cells(start_row=row,start_column=6,end_row=row,end_column=7)
                for col,val in values.items():
                    cell=sheet.cell(row,col)
                    if col==1:cell.value=val
                    else:write_text(cell,val)
                    cell.font=Font(name='標楷體' if col==4 else 'Times New Roman',size=12)
                    cell.alignment=Alignment(horizontal='center' if col<=3 else 'left',vertical='center',wrap_text=True)
                    if col in (2,3):cell.number_format='@'
                # Wider names wrap; allocate height so records are never clipped.
                cn_lines=max(1,(len(student['chinese_name'])+5)//6)
                en_lines=max(1,(len(student['english_name'])+23)//24)
                sheet.row_dimensions[row].height=max(22,16*max(cn_lines,en_lines))
            last=17+count
            if attendance:
                for offset,text in [(2,'出席人數 Number of Attendees: '),(3,'缺席人數 Number of Absentees: '),(5,'監考員簽名 Signature of Invigilator(s): ')]:
                    row=last+offset
                    sheet.merge_cells(start_row=row,start_column=1,end_row=row,end_column=5)
                    write_text(sheet.cell(row,1),text)
                    sheet.cell(row,1).font=Font(name='Times New Roman',size=12)
                    sheet.row_dimensions[row].height=24
                last+=6
                for row in range(18+count,last+1):
                    for col in range(6,8):sheet.cell(row,col).protection=Protection(locked=False)
            # Deterministic conservative A4 page breaks, repeat the entire official header.
            height=0
            for row in range(18,last+1):
                h=sheet.row_dimensions[row].height or 22
                if height+h>340 and row>18:
                    sheet.row_breaks.append(Break(id=row-1))
                    height=0
                height+=h
            sheet.print_area=f'A1:G{last}'
            sheet.oddFooter.center.text='第 &P 頁 / 共 &N 頁'
            sheet.sheet_properties.outlinePr.summaryRight=False
        return wb

from datetime import date
from PySide6.QtWidgets import QLabel
from app.ui.widgets import FormDialog
from app.models.programmes import FACULTY,PROGRAMMES,DEFAULT_PROGRAMME


class BatchDialog(FormDialog):
    def __init__(self,old=None,parent=None):
        current=date.today();year=current.year if current.month>=8 else current.year-1
        years=[f'{y}–{y+1}' for y in range(year-3,year+5)]
        values=dict(old or {})
        if values.get('academic_year') and values['academic_year'] not in years:years.append(values['academic_year'])
        values.setdefault('academic_year',f'{year}–{year+1}')
        values.setdefault('semester','第一學期');values.setdefault('exam_type','期中')
        fields=[('academic_year','學年',[(v,v) for v in years]),
                ('semester','學期',[(v,v) for v in ['第一學期','第二學期','第三學期']]),
                ('exam_type','考試',[(v,v) for v in ['期中','期末']]),('notes','備註','text')]
        super().__init__('學年、學期與考試設定',fields,values,parent)
        self.preview=QLabel();self.preview.setWordWrap(True)
        self.layout().insertRow(3,'考試名稱（自動）',self.preview)
        self.layout().insertRow(4,'學院',QLabel(FACULTY))
        programme=QLabel('\n'.join(PROGRAMMES[DEFAULT_PROGRAMME]));programme.setWordWrap(True)
        self.layout().insertRow(5,'課程',programme)
        for key in ['academic_year','semester','exam_type']:self.editors[key].currentIndexChanged.connect(self.update_name)
        self.update_name()

    def update_name(self):
        values=self.values()
        self.preview.setText(f'{values["academic_year"]}學年{values["semester"]}{values["exam_type"]}考試')

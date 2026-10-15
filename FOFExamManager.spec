# Build on the target OS: PyInstaller does not cross-compile Windows executables.
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'run.py')],pathex=[str(root)],binaries=[],
             datas=[(str(root / 'resources' / 'official_template.xlsx'),'resources')],
             hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],
             excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtNetwork',
                       'PySide6.QtPdf','PySide6.QtQml','PySide6.QtQuick','tkinter','matplotlib','numpy','pandas','pytest'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='FOFExamManager',debug=False,
          bootloader_ignore_signals=False,strip=False,upx=False,console=False)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='FOFExamManager')

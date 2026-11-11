"""Check the current checkout's requirements using the launcher's interpreter."""
from importlib.metadata import version,PackageNotFoundError
from pathlib import Path
import sys


def check():
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    from scripts.prepare_environment import require_supported_python
    require_supported_python()
    for line in (root/'requirements.txt').read_text(encoding='utf8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        package,required=line.split('==',1)
        try:installed=version(package)
        except PackageNotFoundError:installed=None
        if installed!=required:raise RuntimeError(f'{package} {required} is required; found {installed or "not installed"}.')
    from PySide6 import QtWidgets
    from app.utils.paper_support import ensure_paper_support
    ensure_paper_support()
    from app.exporters.paper_forms import artwork
    from openpyxl.drawing.image import Image
    for name in ('review','cover','bag'):Image(artwork(name))._data()
    from app.exporters.paper_pdf import load_template
    for name in ('review','bag'):load_template(name)
    from app.templates.engine import template_path
    from openpyxl import load_workbook
    with_template=load_workbook(template_path(),keep_links=False)
    try:
        if with_template.sheetnames!=['Attendance','Seat Plan']:raise RuntimeError('Invalid official Excel template.')
    finally:with_template.close()


if __name__=='__main__':
    try:check()
    except Exception as exc:
        # Keep Windows console output safe even with a legacy code page.
        message=f'Environment check failed: {exc}'
        print(message.encode(sys.stdout.encoding or 'utf8',errors='replace').decode(sys.stdout.encoding or 'utf8'))
        sys.exit(1)

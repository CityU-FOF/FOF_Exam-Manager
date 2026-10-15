import argparse
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from app.database.store import Store
from app.services.manager import Manager
from app.ui.window import MainWindow
from app.ui.style import STYLE


def main():
    parser=argparse.ArgumentParser(description='FOF Exam Seating & Attendance Manager')
    parser.add_argument('--data-dir',type=Path,help='Override local data directory (no network required)')
    parser.add_argument('--self-test',type=Path,metavar='OUTPUT_DIR',help='Run isolated synthetic deployment check and save a report')
    args=parser.parse_args()
    app=QApplication(sys.argv[:1]);app.setApplicationName('FOF Exam Manager');app.setOrganizationName('CityU FOF')
    app.setStyle('Fusion');app.setStyleSheet(STYLE)
    if args.self_test:
        from app.utils.selfcheck import selfcheck
        try:selfcheck(app,args.self_test);return 0
        except Exception as exc:
            # Windowed builds have no console; retain an explicit machine-readable failure.
            import json
            failure=args.self_test/'selfcheck-failure.json'
            if not failure.exists():
                args.self_test.mkdir(parents=True,exist_ok=True)
                failure.write_text(json.dumps({'status':'failed','error':str(exc)},ensure_ascii=False),encoding='utf8')
            return 1
    try:
        store=Store(args.data_dir/'fof_exam.sqlite3' if args.data_dir else None)
        window=MainWindow(Manager(store));window.show()
    except Exception as exc:
        QMessageBox.critical(None,'無法啟動 FOF 考試管理系統',
            '無法讀取或建立本地資料庫，請檢查資料目錄權限或使用相容備份。\n'+str(exc))
        return 1
    app.aboutToQuit.connect(store.close)
    return app.exec()


if __name__=='__main__':sys.exit(main())

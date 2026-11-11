from io import BytesIO


def ensure_paper_support():
    """Exercise the same Pillow bridge used to embed official Excel artwork."""
    try:
        from PIL import Image as PillowImage
        from openpyxl.drawing.image import Image
        with BytesIO() as stream:
            with PillowImage.new('RGB',(1,1),'white') as image:image.save(stream,format='PNG')
            stream.seek(0)
            Image(stream)._data()
    except (ImportError,OSError) as exc:
        raise RuntimeError('官方表格所需的 Pillow 圖像套件未正確載入。\n'
            '請先關閉程式，重新執行「首次安裝.bat」，完成後再用「啟動程式.bat」開啟。\n'
            '此問題與試題審批無關，附件一及附件三由系統自動生成。') from exc

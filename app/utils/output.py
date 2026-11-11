from pathlib import Path


def default_output_directory(manager):
    """Keep a stable writable location alongside the local database."""
    return Path(manager.db.path).parent/'輸出文件'

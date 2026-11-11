import importlib.util
from pathlib import Path
import pytest


def checker():
    path=Path(__file__).resolve().parents[1]/'scripts/check_environment.py'
    spec=importlib.util.spec_from_file_location('fof_environment_check',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_environment_check_accepts_installed_dependencies_and_template():
    checker().check()


@pytest.mark.parametrize('installed',[None,'11.0.0'])
def test_environment_check_rejects_pre_pillow_upgrade_even_with_old_ready_marker(monkeypatch,installed):
    module=checker();real=module.version
    def version(package):
        if package!='Pillow':return real(package)
        if installed is None:raise module.PackageNotFoundError(package)
        return installed
    monkeypatch.setattr(module,'version',version)
    with pytest.raises(RuntimeError,match='Pillow 12.0.0 is required'):module.check()


def test_environment_check_rejects_broken_image_bridge_despite_valid_metadata(monkeypatch):
    import openpyxl.drawing.image
    monkeypatch.setattr(openpyxl.drawing.image,'PILImage',None)
    with pytest.raises(RuntimeError,match='Pillow'):checker().check()

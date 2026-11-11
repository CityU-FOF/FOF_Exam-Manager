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


@pytest.mark.parametrize('version,bits,accepted',[
    ((3,11,9),64,False),((3,12,10),64,True),((3,13,7),64,True),
    ((3,14,0),64,True),((3,15,0),64,False),((4,0,0),64,False),((3,12,10),32,False)])
def test_supported_python_range(version,bits,accepted):
    from scripts.prepare_environment import require_supported_python
    if accepted:require_supported_python(version,bits)
    else:
        with pytest.raises(RuntimeError,match='Python 3.15'):require_supported_python(version,bits)


def test_preview_and_free_threaded_builds_rejected(monkeypatch):
    from scripts import prepare_environment as setup
    class Preview(tuple):releaselevel='alpha'
    with pytest.raises(RuntimeError):setup.require_supported_python(Preview((3,14,0)),64)
    monkeypatch.setattr(setup,'sysconfig_free_threaded',lambda:True)
    with pytest.raises(RuntimeError):setup.require_supported_python((3,14,0),64)


def test_rebuild_unsupported_environment_retains_old_env_and_sibling_database(tmp_path):
    import sys,venv
    from scripts.prepare_environment import prepare_environment
    target=tmp_path/'venv';target.mkdir()
    (target/'pyvenv.cfg').write_text('version = 3.15.0\n')
    (target/'.fof-setup-complete').write_text('old marker')
    database=tmp_path/'fof_exam.sqlite3';database.write_bytes(b'existing exam data')
    backup=prepare_environment(target,venv.EnvBuilder(with_pip=False).create)
    assert (backup/'pyvenv.cfg').read_text()=='version = 3.15.0\n'
    assert (backup/'.fof-setup-complete').read_text()=='old marker'
    assert f'version = {sys.version_info.major}.{sys.version_info.minor}' in (target/'pyvenv.cfg').read_text()
    assert not (target/'.fof-setup-complete').exists()
    assert database.read_bytes()==b'existing exam data'


@pytest.mark.parametrize('with_config',[False,True])
def test_non_environment_or_database_folder_never_moved(tmp_path,with_config):
    from scripts.prepare_environment import prepare_environment
    target=tmp_path/'venv';target.mkdir();data=target/'fof_exam.sqlite3';data.write_bytes(b'keep')
    if with_config:(target/'pyvenv.cfg').write_text('version = 3.15.0\n')
    with pytest.raises(RuntimeError):prepare_environment(target,lambda path:pytest.fail('Must not create'))
    assert data.read_bytes()==b'keep' and not list(tmp_path.glob('venv.previous-*'))


def test_environment_creation_failure_restores_old_env_and_retains_partial(tmp_path):
    from scripts.prepare_environment import prepare_environment
    target=tmp_path/'venv';target.mkdir();(target/'pyvenv.cfg').write_text('old environment')
    def fail(path):
        path=Path(path);path.mkdir();(path/'partial').write_text('diagnostic')
        raise OSError('creation failed')
    with pytest.raises(OSError,match='creation failed'):prepare_environment(target,fail)
    assert (target/'pyvenv.cfg').read_text()=='old environment'
    assert next(tmp_path.glob('venv.failed-*/partial')).read_text()=='diagnostic'
    assert not list(tmp_path.glob('venv.previous-*'))


def test_unsupported_creator_rejected_before_any_environment_change(tmp_path,monkeypatch):
    from scripts import prepare_environment as setup
    target=tmp_path/'venv';target.mkdir();(target/'pyvenv.cfg').write_text('old')
    monkeypatch.setattr(setup.sys,'version_info',(3,15,0))
    with pytest.raises(RuntimeError):setup.prepare_environment(target,lambda path:pytest.fail('Must not create'))
    assert (target/'pyvenv.cfg').read_text()=='old' and not list(tmp_path.glob('venv.previous-*'))


def test_checker_rejects_315_before_attempting_dependency_import(monkeypatch):
    from scripts import prepare_environment as setup
    module=checker()
    monkeypatch.setattr(setup.sys,'version_info',(3,15,0))
    monkeypatch.setattr(module,'version',lambda name:pytest.fail('Version gate must run first'))
    with pytest.raises(RuntimeError,match='Python 3.15'):module.check()

"""Select a supported Python and replace only a dedicated virtual environment."""
from pathlib import Path
import os
import platform
import struct
import sys
import uuid
import venv


def require_supported_python(version=None,bits=None):
    version=sys.version_info if version is None else version
    bits=struct.calcsize('P')*8 if bits is None else bits
    if (not (3,12)<=version[:2]<(3,15) or bits!=64
            or getattr(version,'releaselevel','final')!='final'
            or platform.python_implementation()!='CPython'
            or sysconfig_free_threaded()):
        raise RuntimeError('Use standard 64-bit CPython 3.12, 3.13 or 3.14 (3.12 recommended). '
                           'Python 3.15 and preview/free-threaded builds are not supported by these packages.')


def sysconfig_free_threaded():
    import sysconfig
    return bool(sysconfig.get_config_var('Py_GIL_DISABLED'))


def prepare_environment(target,creator=None):
    require_supported_python()
    target=Path(os.path.abspath(target))
    backup=None
    if target.is_symlink() or target.is_junction():
        raise RuntimeError('The virtual environment path must not be a link or junction.')
    if Path(sys.executable).resolve().is_relative_to(target.resolve()):
        raise RuntimeError('Select a base Python outside the environment before replacing it.')
    if target.exists():
        if not (target/'pyvenv.cfg').is_file():
            raise RuntimeError(f'Refusing to replace a folder without pyvenv.cfg: {target}')
        # Never move a directory containing application data by mistake.
        if any(p.suffix.lower() in ('.db','.sqlite','.sqlite3') for p in target.rglob('*') if p.is_file()):
            raise RuntimeError(f'This folder contains database files; it will not be replaced: {target}')
        backup=target.with_name(target.name+'.previous-'+uuid.uuid4().hex[:8])
        target.rename(backup)
    try:
        if creator is None:creator=venv.EnvBuilder(with_pip=True).create
        creator(str(target))
    except Exception:
        # Keep the partial new environment for diagnosis, and restore the old one.
        if target.exists():target.rename(target.with_name(target.name+'.failed-'+uuid.uuid4().hex[:8]))
        if backup:backup.rename(target)
        raise
    if backup:print(f'Previous environment retained: {backup}')
    print(f'Environment ready: {target}')
    return backup


if __name__=='__main__':
    try:
        if sys.argv[1:]==['--probe']:require_supported_python()
        elif len(sys.argv)==2:prepare_environment(sys.argv[1])
        else:raise ValueError('Usage: prepare_environment.py --probe OR VENV_DIRECTORY')
    except Exception as exc:
        print(str(exc).encode(sys.stdout.encoding or 'utf8',errors='replace').decode(sys.stdout.encoding or 'utf8'))
        sys.exit(1)

"""PyInstaller hook for fermion-research, the package behind the Phonon-2 engine.

Used by scripts/build_exe.ps1 via --additional-hooks-dir packaging/hooks.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# Real module names only. The package ships every platform's kernel libraries,
# and on macOS/Linux ".so" is a Python extension suffix, so the Linux ones would
# otherwise be mistaken for modules ("libfsq-linux-x86_64") and break the build.
hiddenimports = collect_submodules(
    "fermion", filter=lambda name: all(part.isidentifier() for part in name.split("."))
)

# Data, including the .py sources: fermion loads some of its own modules by file
# path (importlib's spec_from_file_location), so they must exist on disk. This
# also brings the sha256-pinned kernel libraries, which must stay unmodified.
datas = collect_data_files("fermion", include_py_files=True) + copy_metadata("fermion-research")

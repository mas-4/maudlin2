"""Scripts the tests load by file (scripts/validate.py, scripts/maudlin_mcp.py), registered as modules so conftest's
redirect of the data folder reaches their paths too (Oct 22: loaded by file and never registered, validate kept its
real verdict log, and test_curation_db wrote 408 fake answers into it). Each load is its own module, as before."""
import importlib.util
import os
import sys

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts')


def script(name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[f'_tests_script_{name}_{id(mod)}'] = mod  # a name of its own: conftest redirects each module once by name
    from tests.conftest import _redirect_data_paths
    _redirect_data_paths()
    return mod

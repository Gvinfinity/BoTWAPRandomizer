"""Load static modules without requiring an Archipelago installation."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "worlds/botw/static"
if "botw_static" not in sys.modules:
    spec = spec_from_file_location("botw_static", PACKAGE / "__init__.py",
                                  submodule_search_locations=[str(PACKAGE)])
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

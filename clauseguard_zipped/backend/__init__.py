import importlib
import sys

# Load the actual clauseguard.backend package
_pkg = importlib.import_module('clauseguard.backend')
# Expose the top-level package as 'backend'
sys.modules[__name__] = _pkg

# List of submodules to alias
_submodules = [
    'schemas',
    'services',
    'vision',
    'preprocessing',
    'model_loader',
    'main',
]
for name in _submodules:
    full_name = f'clauseguard.backend.{name}'
    try:
        mod = importlib.import_module(full_name)
        sys.modules[f'backend.{name}'] = mod
    except ModuleNotFoundError:
        # Skip if submodule does not exist
        continue

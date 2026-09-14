#!/bin/sh
set -eu
python -c "import homeassistant.const as c; print('ha', getattr(c, '__version__', 'ok'))"
if ! python -c "import pytest" 2>/dev/null; then
  pip install --quiet pytest
fi
export PYTHONPATH=/repo/custom_components
cd /repo
python -m pytest tests/test_ha.py tests/test_config_flow.py tests/test_resolve.py tests/test_listen_only.py -q --tb=short

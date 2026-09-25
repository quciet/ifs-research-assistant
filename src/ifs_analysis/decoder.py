"""Decode standard Parquet normally; malformed legacy INT_16 only in an isolated worker."""
import io
import os
import subprocess
import sys
import numpy as np
import pandas as pd
from fastparquet import ParquetFile
from .errors import AnalysisError


def decode(blob, encoding='standard'):
    if encoding not in ('standard', 'legacy_int16'):
        raise AnalysisError(f'Unsupported payload encoding: {encoding}')
    try:
        frame = ParquetFile(io.BytesIO(blob)).to_pandas()
        return frame, 'standard'
    except (ValueError, RuntimeError, IndexError) as exc:
        if encoding != 'legacy_int16':
            raise AnalysisError(f'Parquet decoding failed: {exc}') from exc
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = os.pathsep.join(str(p) for p in sys.path if p)
    result = subprocess.run([sys.executable, '-B', '-m', 'ifs_analysis._legacy_worker'],
                            input=blob, capture_output=True, timeout=90, env=env)
    if result.returncode:
        raise AnalysisError('Legacy Parquet decoding failed: ' + result.stderr.decode('utf-8', errors='replace')[-2000:])
    with np.load(io.BytesIO(result.stdout), allow_pickle=False) as arrays:
        frame = pd.DataFrame({key: arrays[key] for key in arrays.files})
    return frame, 'legacy_int16_worker'

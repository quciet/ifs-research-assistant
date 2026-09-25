"""Private subprocess: the fastparquet compatibility patch never enters the caller process."""
import io
import sys
import numpy as np
from fastparquet import ParquetFile, core


def main():
    payload = sys.stdin.buffer.read()
    parquet = ParquetFile(io.BytesIO(payload))
    # Only the observed IFs flat numeric schema is eligible, not arbitrary corrupt Parquet.
    fields = parquet.fmd.schema[1:]
    if not fields or any(not ((f.name.isdigit() and f.type == 1 and f.converted_type == 16)
                             or (f.name == 'v' and f.type == 4)) for f in fields):
        raise ValueError('Compatibility decoder only supports INT_16 dimension fields and FLOAT v')
    original = core.read_plain
    repaired = 0
    def legacy(raw, type_, count, *args, **kwargs):
        nonlocal repaired
        if type_ == 1 and count > 0 and len(raw) == count * 2:
            repaired += 1
            return np.frombuffer(raw, dtype='<i2', count=count).astype('int32')
        return original(raw, type_, count, *args, **kwargs)
    core.read_plain = legacy
    frame = parquet.to_pandas()
    if not repaired:
        raise ValueError('No legacy short-width pages found')
    out = io.BytesIO()
    np.savez(out, **{name: frame[name].to_numpy(dtype='float64', na_value=np.nan) for name in frame})
    sys.stdout.buffer.write(out.getvalue())

if __name__ == '__main__':
    main()

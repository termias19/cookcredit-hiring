"""Cloud Run Job entrypoint: no public listener, no payment or scoring imports."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.operations import emit_event
from services.recording_compression import process_recording

if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Two UUID arguments required')
        state = process_recording(*sys.argv[1:])
        emit_event('recording_compression_execution', state=state)
    except Exception:
        # Raw dependency/decoder exceptions can contain paths or credentials.
        emit_event('recording_compression_execution_failed', severity='ERROR', code='worker_unhandled')
        sys.exit(1)

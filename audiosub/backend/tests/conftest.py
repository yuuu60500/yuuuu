import os
import subprocess
import tempfile

_tmp = tempfile.mkdtemp(prefix="audiosub-test-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmp}/test.db",
    LOCAL_STORAGE_DIR=f"{_tmp}/storage",
    ASR_PROVIDER="mock",
    TRANSLATION_PROVIDER="mock",
    RUN_JOBS_IN_BACKGROUND="false",
    TRANSLATION_BATCH_SIZE="2",
    TRANSLATION_CONTEXT_SIZE="1",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.media import ffmpeg_binary  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _make(path: str, video: bool) -> str:
    if os.path.exists(path):
        return path
    cmd = [ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=12"]
    if video:
        cmd += ["-f", "lavfi", "-i", "color=c=blue:s=160x120:d=12",
                "-c:v", "mpeg4", "-c:a", "aac", "-shortest"]
    cmd.append(path)
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture(scope="session")
def mp4_file():
    return _make(os.path.join(_tmp, "portuguese_meeting.mp4"), video=True)


@pytest.fixture(scope="session")
def mp3_file():
    return _make(os.path.join(_tmp, "clip.mp3"), video=False)

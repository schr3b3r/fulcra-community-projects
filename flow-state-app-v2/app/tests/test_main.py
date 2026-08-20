from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_read_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_marker_none_when_never_recorded(monkeypatch) -> None:
    """/api/marker returns a clear {"marker": None} rather than erroring
    when no marker sample has ever been recorded."""
    import main

    monkeypatch.setattr(main, "get_current_marker_info", lambda: None)
    response = client.get("/api/marker")
    assert response.status_code == 200
    assert response.json() == {"marker": None}


def test_api_marker_returns_info_when_present(monkeypatch) -> None:
    import main

    fake_info = {"session_id": "abc123", "processed_at": "2026-01-01T00:00:00+00:00"}
    monkeypatch.setattr(main, "get_current_marker_info", lambda: fake_info)
    response = client.get("/api/marker")
    assert response.status_code == 200
    assert response.json() == {"marker": fake_info}


def test_api_ideas_returns_list(monkeypatch) -> None:
    import main

    fake_ideas = [{"idea_id": "s1_idea0", "key": "C Major", "bpm": 120}]
    monkeypatch.setattr(main, "get_fulcra_client", lambda: object())
    monkeypatch.setattr(main, "list_review_ideas", lambda client: fake_ideas)
    response = client.get("/api/ideas")
    assert response.status_code == 200
    assert response.json() == {"ideas": fake_ideas}


def test_api_ideas_returns_503_when_fulcra_unavailable(monkeypatch) -> None:
    import main
    from fulcra_client import FulcraAuthError

    def _raise(*args, **kwargs):
        raise FulcraAuthError("no credentials")

    monkeypatch.setattr(main, "get_fulcra_client", _raise)
    response = client.get("/api/ideas")
    assert response.status_code == 503


def test_api_audio_session_404_when_missing_everywhere(monkeypatch) -> None:
    import main
    from fulcra_client import FulcraAuthError

    def _raise_local(session_id):
        raise main.AudioNotFoundError(f"not found: {session_id}")

    def _raise_auth(*args, **kwargs):
        raise FulcraAuthError("no credentials")

    monkeypatch.setattr(main, "local_processed_audio_path", _raise_local)
    monkeypatch.setattr(main, "get_fulcra_client", _raise_auth)
    response = client.get("/api/audio/session/does-not-exist")
    assert response.status_code == 503


def test_api_audio_session_falls_back_to_fulcra_when_local_missing(monkeypatch) -> None:
    import main

    def _raise_local(session_id):
        raise main.AudioNotFoundError("no local copy")

    monkeypatch.setattr(main, "local_processed_audio_path", _raise_local)
    monkeypatch.setattr(main, "get_fulcra_client", lambda: object())
    monkeypatch.setattr(
        main, "download_session_audio_from_fulcra", lambda client, session_id: b"remote-session-bytes"
    )

    response = client.get("/api/audio/session/whatever")
    assert response.status_code == 200
    assert response.content == b"remote-session-bytes"


def test_api_audio_session_returns_wav_bytes(monkeypatch, tmp_path) -> None:
    import main

    fake_wav = tmp_path / "fake.wav"
    fake_wav.write_bytes(b"RIFF-fake-wav-bytes")
    monkeypatch.setattr(main, "local_processed_audio_path", lambda session_id: fake_wav)

    response = client.get("/api/audio/session/whatever")
    assert response.status_code == 200
    assert response.content == b"RIFF-fake-wav-bytes"
    assert response.headers["content-type"] == "audio/wav"


def test_api_audio_idea_prefers_local_copy(monkeypatch, tmp_path) -> None:
    import main

    fake_clip = tmp_path / "idea.wav"
    fake_clip.write_bytes(b"local-clip-bytes")
    monkeypatch.setattr(main, "local_idea_clip_path", lambda idea_id: fake_clip)

    response = client.get("/api/audio/idea/whatever")
    assert response.status_code == 200
    assert response.content == b"local-clip-bytes"


def test_api_audio_idea_falls_back_to_fulcra_when_local_missing(monkeypatch) -> None:
    import main
    from review_api import AudioNotFoundError

    def _raise_local(idea_id):
        raise AudioNotFoundError("no local copy")

    fake_idea = {
        "idea_id": "s1_idea0",
        "file_path": "/flow-state/ideas/s1_idea0.wav",
    }

    monkeypatch.setattr(main, "local_idea_clip_path", _raise_local)
    monkeypatch.setattr(main, "get_fulcra_client", lambda: object())
    monkeypatch.setattr(main, "list_review_ideas", lambda client: [fake_idea])
    monkeypatch.setattr(
        main, "download_idea_audio_from_fulcra", lambda client, path: b"remote-bytes"
    )

    response = client.get("/api/audio/idea/s1_idea0")
    assert response.status_code == 200
    assert response.content == b"remote-bytes"


def test_api_audio_idea_404_when_not_found_anywhere(monkeypatch) -> None:
    import main
    from review_api import AudioNotFoundError

    def _raise_local(idea_id):
        raise AudioNotFoundError("no local copy")

    monkeypatch.setattr(main, "local_idea_clip_path", _raise_local)
    monkeypatch.setattr(main, "get_fulcra_client", lambda: object())
    monkeypatch.setattr(main, "list_review_ideas", lambda client: [])

    response = client.get("/api/audio/idea/does-not-exist")
    assert response.status_code == 404

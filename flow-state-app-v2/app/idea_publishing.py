"""Musical idea publishing: upload an extracted clip + metadata to Fulcra
for durable, queryable storage.

See app/features/musical_idea_publishing.md for the full spec. Uses the
Fulcra Python SDK directly (upload_file, record_data_type,
moment_annotations) -- never the CLI or subprocess calls.

Custom annotation types (like the "MusicalIdea" type used here) are
recorded against their *base* type (MomentAnnotation) with a special
`source` identifying the custom type: "com.fulcradynamics.annotation.<uuid>".
This mirrors how the `fulcra-api` CLI's own `record` command handles
user-defined annotation subtypes (BaseType/UUID) -- confirmed by reading
its implementation for reference, not guessed at.
"""
import json
import logging
from pathlib import Path
from typing import Optional, Union

from fulcra_api.core import FulcraAPI

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

MUSICAL_IDEA_TYPE_NAME = "MusicalIdea"
ANNOTATION_SOURCE_PREFIX = "com.fulcradynamics.annotation"


class PublishingError(Exception):
    """Raised when publishing a musical idea fails (upload or record
    creation)."""


class MusicalIdeaTypeNotFoundError(PublishingError):
    """Raised when the user's Fulcra account has no 'MusicalIdea' data
    type provisioned yet (see the flow-state-app v1 setup_fulcra.sh for
    the provisioning step this depends on)."""


def _resolve_musical_idea_type(client: FulcraAPI) -> dict:
    """Look up the user's MusicalIdea custom data type, failing with a
    clear error if it doesn't exist rather than crashing unhandled or
    silently no-op'ing.

    Custom/user-configured annotation types are looked up by *display
    name* (e.g. "MusicalIdea"), not by their catalog ID -- the catalog's
    server-side `data_type` filter expects an ID like
    "MomentAnnotation/<uuid>", not a display name, so we fetch the full
    catalog and filter client-side instead of using resolve_data_type()
    (which 404s for a plain display name).
    """
    try:
        catalog = client.v1_catalog()
    except Exception as exc:
        raise PublishingError(f"Failed to fetch Fulcra data type catalog: {exc}") from exc

    matches = [
        entry
        for entry in catalog
        if entry.get("name") == MUSICAL_IDEA_TYPE_NAME
        and "user_configured" in entry.get("categories", [])
    ]

    if not matches:
        raise MusicalIdeaTypeNotFoundError(
            f"'{MUSICAL_IDEA_TYPE_NAME}' data type not found in this Fulcra "
            f"account. It must be provisioned before publishing (see "
            f"flow-state-app's setup_fulcra.sh for the original "
            f"provisioning step; this project would need its own "
            f"equivalent setup script)."
        )
    return matches[0]


def publish_musical_idea(
    client: FulcraAPI,
    clip_path: PathLike,
    key: str,
    bpm: int,
    session_id: str,
    marker_timestamp_seconds: float,
    fulcra_upload_path: Optional[str] = None,
) -> dict:
    """Upload an extracted clip and its metadata to Fulcra as a
    MusicalIdea record.

    Args:
        client: an authenticated FulcraAPI client.
        clip_path: local path to the extracted audio clip.
        key: estimated musical key (e.g. "C Major").
        bpm: estimated tempo.
        session_id: the session this idea was extracted from.
        marker_timestamp_seconds: where in the session the marker (that
            triggered this extraction) was detected.
        fulcra_upload_path: where to upload the clip in Fulcra's file
            store. Defaults to "/flow-state/ideas/<clip filename>".

    Returns:
        A dict with "upload_id" (from record_data_type), "file_path" (the
        Fulcra path the clip was uploaded to), and the metadata that was
        recorded.

    Raises:
        MusicalIdeaTypeNotFoundError: if the MusicalIdea type isn't
            provisioned in this Fulcra account.
        PublishingError: for any other upload/record failure (e.g.
            network or auth error). The local clip file is never deleted
            or modified by this function, regardless of outcome.
    """
    path = Path(clip_path)
    if not path.is_file():
        raise PublishingError(f"Clip file not found: {path}")

    idea_type = _resolve_musical_idea_type(client)
    type_uuid = idea_type["id"].split("/", maxsplit=1)[-1].lower()
    annotation_source = f"{ANNOTATION_SOURCE_PREFIX}.{type_uuid}"

    upload_path = fulcra_upload_path or f"/flow-state/ideas/{path.name}"

    try:
        with open(path, "rb") as f:
            file_size = path.stat().st_size
            client.upload_file(
                data=f,
                file_type="audio/wav",
                file_size=file_size,
                filepath=upload_path,
            )
    except Exception as exc:
        raise PublishingError(
            f"Failed to upload clip {path} to Fulcra at {upload_path}: {exc}"
        ) from exc

    metadata = {
        "session_id": session_id,
        "marker_timestamp_seconds": marker_timestamp_seconds,
        "key": key,
        "bpm": bpm,
        "file_path": upload_path,
    }

    record = {
        "note": json.dumps(metadata),
        "sources": [annotation_source],
    }

    try:
        response = client.record_data_type(
            "MomentAnnotation", [record], api_version="v1alpha1"
        )
    except Exception as exc:
        raise PublishingError(
            f"Uploaded clip to {upload_path} but failed to record MusicalIdea "
            f"metadata: {exc}. The uploaded file is not orphaned data loss on "
            f"its own, but the semantic record linking it is missing."
        ) from exc

    return {
        "upload_id": response.get("upload_id"),
        "file_path": upload_path,
        "metadata": metadata,
    }


def get_published_ideas(
    client: FulcraAPI,
    start_time,
    end_time,
) -> list[dict]:
    """Query back published MusicalIdea records in a time range, decoding
    their JSON metadata payload.

    Args:
        client: an authenticated FulcraAPI client.
        start_time: range start (ISO string or datetime).
        end_time: range end (ISO string or datetime).

    Returns:
        A list of dicts, each with the decoded metadata plus "recorded_at".
    """
    idea_type = _resolve_musical_idea_type(client)
    type_uuid = idea_type["id"].split("/", maxsplit=1)[-1].lower()
    annotation_source = f"{ANNOTATION_SOURCE_PREFIX}.{type_uuid}"

    raw_records = client.moment_annotations(
        start_time, end_time, source=annotation_source
    )

    ideas = []
    for record in raw_records:
        note = record.get("note")
        if not note:
            continue
        try:
            metadata = json.loads(note)
        except json.JSONDecodeError:
            continue
        metadata["recorded_at"] = record.get("recorded_at")
        ideas.append(metadata)

    return ideas

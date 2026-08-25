"""Custom Fulcra data types management for Engineering Journey.

This module provides utilities to idempotently ensure real custom Fulcra data types
and tags exist in the user's catalog and to retrieve their source tags / tag UUIDs for reading/writing.
"""

import hashlib
import logging
from typing import Dict, List, Optional
import uuid

from fulcra_api.core import FulcraAPI
from fulcra_client import get_fulcra_client

logger = logging.getLogger(__name__)

# Catalog name definitions & descriptions
RECORD_TYPE_DEFINITIONS: Dict[str, str] = {
    "GitHubBackfillProgress": "Resumable GitHub backfill progress checkpoints",
    "GitHubActivityRaw": "Raw GitHub activity items (commits, PRs, issues, reviews)",
    "ActivityRollup": "Aggregated engineering activity rollups over day/week/month/quarter/year periods",
    "NotabilitySignal": "Personal baseline notability signals and activity anomaly scores",
}

# In-memory UUID cache per process: name -> UUID string
_TYPE_UUID_CACHE: Dict[str, str] = {}

# In-memory Tag UUID cache per process: tag_name -> UUID string
_TAG_UUID_CACHE: Dict[str, str] = {}


def clear_custom_data_type_cache() -> None:
    """Clear the process-local in-memory custom data type and tag UUID caches."""
    global _TYPE_UUID_CACHE
    _TYPE_UUID_CACHE.clear()
    clear_tag_cache()


def clear_tag_cache() -> None:
    """Clear the process-local in-memory tag UUID cache."""
    global _TAG_UUID_CACHE
    _TAG_UUID_CACHE.clear()


def get_or_create_custom_data_type(
    name: str,
    description: Optional[str] = None,
    client: Optional[FulcraAPI] = None,
) -> str:
    """Ensure a custom Fulcra data type exists in the user's catalog and return its UUID.

    Args:
        name: The catalog name of the data type (e.g. 'GitHubBackfillProgress').
        description: Optional description if creating for the first time.
        client: Optional authenticated FulcraAPI client.

    Returns:
        The UUID string assigned by Fulcra to this custom data type.
    """
    if name in _TYPE_UUID_CACHE:
        return _TYPE_UUID_CACHE[name]

    if client is None:
        client = get_fulcra_client()

    if description is None:
        description = RECORD_TYPE_DEFINITIONS.get(name, f"Custom data type {name}")

    # Query catalog for existing type
    try:
        user_id = client.get_fulcra_userid()
        catalog = client.v1_catalog(fulcra_userid=user_id)
        for item in catalog:
            if item.get("name") == name and item.get("id", "").startswith(
                "MomentAnnotation/"
            ):
                parts = item["id"].split("/", 1)
                if len(parts) == 2:
                    uuid_str = parts[1]
                    _TYPE_UUID_CACHE[name] = uuid_str
                    return uuid_str
    except Exception:
        pass

    # If not found in catalog, create it
    res = client.create_annotation(
        annotation_type="moment",
        name=name,
        description=description,
        tags=[],
    )
    uuid_str = res["id"]
    _TYPE_UUID_CACHE[name] = uuid_str
    return uuid_str


def get_custom_source_tag(
    name: str,
    client: Optional[FulcraAPI] = None,
) -> str:
    """Return the source tag for a custom data type (f'com.fulcradynamics.annotation.{uuid}').

    Args:
        name: The catalog name of the custom data type.
        client: Optional authenticated FulcraAPI client.

    Returns:
        The full source tag string, e.g. 'com.fulcradynamics.annotation.<uuid>'.
    """
    uuid_str = get_or_create_custom_data_type(name, client=client)
    return f"com.fulcradynamics.annotation.{uuid_str}"


def get_or_create_tag_uuids(
    tag_names: List[str],
    client: Optional[FulcraAPI] = None,
) -> Dict[str, str]:
    """Ensure tag UUIDs exist for a list of tag names and return mapping of name -> UUID.

    Resolves tag UUIDs ONCE per distinct tag name and caches them for the duration of the run.
    Uses `client.create_tags(missing_names)` for batch resolution.

    Args:
        tag_names: List of tag names (e.g. ['schr3b3r/shimmer', 'commit']).
        client: Optional authenticated FulcraAPI client.

    Returns:
        Dict mapping tag_name -> tag UUID string.
    """
    if not tag_names:
        return {}

    unique_names = list(dict.fromkeys([t for t in tag_names if t]))
    missing = [n for n in unique_names if n not in _TAG_UUID_CACHE]

    if missing:
        if client is None:
            client = get_fulcra_client()
        try:
            created = client.create_tags(missing)
            for item in created:
                if isinstance(item, dict) and "name" in item and "id" in item:
                    _TAG_UUID_CACHE[item["name"]] = str(item["id"])
                elif hasattr(item, "name") and hasattr(item, "id"):
                    _TAG_UUID_CACHE[str(item.name)] = str(item.id)
        except Exception as exc:
            logger.warning("Failed to resolve/create tags %s: %s", missing, exc)
            for n in missing:
                if n not in _TAG_UUID_CACHE:
                    # Deterministic fallback UUID for mock/offline testing environments
                    _TAG_UUID_CACHE[n] = str(
                        uuid.UUID(bytes=hashlib.md5(f"tag:{n}".encode("utf-8")).digest())
                    )

    return {n: _TAG_UUID_CACHE[n] for n in unique_names if n in _TAG_UUID_CACHE}

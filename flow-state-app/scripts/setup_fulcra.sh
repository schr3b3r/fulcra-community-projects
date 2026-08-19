#!/usr/bin/env bash
set -euo pipefail

# setup_fulcra.sh
# Ensures the required custom data type exists in the user's Fulcra vault.

echo "Provisioning Fulcra Data Types for Flow State..."

# Check if MusicalIdea already exists in user catalog to ensure idempotency
if uvx fulcra-api catalog --category user_configured | grep -q '"name": "MusicalIdea"'; then
  echo "MusicalIdea data type already exists in Fulcra. Skipping creation."
else
  echo "Creating MusicalIdea data type..."
  uvx fulcra-api data-type create MomentAnnotation "MusicalIdea" \
    -d "A captured Flow State musical idea"
fi

echo "Provisioning complete."

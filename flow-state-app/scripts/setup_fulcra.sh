#!/bin/bash

# setup_fulcra.sh
# Ensures the required custom data type exists in the user's Fulcra vault.

echo "Provisioning Fulcra Data Types for Flow State..."

# We attempt to create the type. If it already exists, fulcra-api will safely error or ignore.
# Note: In a production app, the backend should query for this UUID dynamically.
# For this prototype, we are using the hardcoded UUID from the initial setup: c4480f1a-b80e-45b1-9eaa-190bf564485c
uvx fulcra-api data-type create \
  --name "MusicalIdea" \
  --description "A captured Flow State musical idea" \
  --base-type "MomentAnnotation"

echo "Provisioning complete."

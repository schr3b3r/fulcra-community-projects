#!/bin/bash

# setup_fulcra.sh
# Ensures the required custom data type exists in the user's Fulcra vault.

echo "Provisioning Fulcra Data Types for Flow State..."

# We attempt to create the type. If it already exists, fulcra-api will safely error or ignore.
uvx fulcra-api data-type create \
  --name "MusicalIdea" \
  --description "A captured Flow State musical idea" \
  --base-type "MomentAnnotation"

echo "Provisioning complete."

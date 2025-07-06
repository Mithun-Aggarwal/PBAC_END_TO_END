#!/bin/bash

# ==============================================================================
# manage_pinecone.sh
# Description: CLI tool for managing Pinecone indexes via .env credentials
# Author:      DevOps Automation Engineer
# ==============================================================================

# --- Configuration & Setup ---

# Set to exit script on any error
set -e

# 1. Load .env file and validate variables
load_and_validate_env() {
  ENV_FILE=".env"
  if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found. Please create one with PINECONE_API_KEY."
    exit 1
  fi

  set -a
  source "$ENV_FILE"
  set +a

  if [ -z "$PINECONE_API_KEY" ]; then
    echo "Error: PINECONE_API_KEY is not set in the .env file."
    exit 1
  fi

  if ! command -v jq &> /dev/null; then
    echo "Warning: 'jq' command not found. The 'clear' and 'stats' commands will not work."
    echo "Please install jq to use all features (e.g., 'sudo apt-get install jq')."
  fi
}

# --- API Definitions ---

API_BASE_URL="https://api.pinecone.io"

# --- Core Functions ---

usage() {
  echo "Pinecone Index Management CLI"
  echo "-------------------------------"
  echo "Usage: $0 <command> [arguments]"
  echo
  echo "Commands:"
  echo "  list                            List all indexes."
  echo "  create <name> <dimension>       Create a new index."
  echo "  delete <name>                   Delete an index structure and all its data."
  echo "  clear <name> [namespace]        Delete all vectors. Clears a specific namespace if provided."
  echo "  status <name>                   Check the status and details of a specific index."
  echo "  stats <name>                    Get vector count and namespace statistics for an index."
  echo
  echo "Examples:"
  echo "  ./manage_pinecone.sh clear my-app-index"
  echo "  ./manage_pinecone.sh clear my-app-index my-namespace"
}

# (Other functions remain the same)
list_indexes() { echo "Fetching all indexes..."; response=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE_URL/indexes" -H "Api-Key: $PINECONE_API_KEY"); body=$(echo "$response" | sed '$d'); http_code=$(echo "$response" | tail -n1); if [ "$http_code" -eq 200 ]; then echo "Success. Index list:"; if command -v python3 &> /dev/null; then echo "$body" | python3 -m json.tool; else echo "$body"; fi; else echo "Error: Failed to list indexes. Status: $http_code\nResponse: $body"; exit 1; fi; }
create_index() { if [ -z "$1" ] || [ -z "$2" ]; then echo "Error: Index name and dimension are required for 'create'."; usage; exit 1; fi; local name="$1"; local dim="$2"; local body=$(printf '{"name": "%s", "dimension": %d, "metric": "cosine"}' "$name" "$dim"); echo "Creating index '$name' with dimension '$dim'..."; response=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE_URL/indexes" -H "Content-Type: application/json" -H "Api-Key: $PINECONE_API_KEY" -d "$body"); body=$(echo "$response" | sed '$d'); http_code=$(echo "$response" | tail -n1); if [ "$http_code" -eq 201 ]; then echo "Success: Index '$name' creation initiated."; else echo "Error: Failed to create index. Status: $http_code\nResponse: $body"; exit 1; fi; }
delete_index() { if [ -z "$1" ]; then echo "Error: Index name is required for 'delete'."; usage; exit 1; fi; local name="$1"; read -p "Are you sure you want to PERMANENTLY DELETE index '$name'? (y/n) " -n 1 -r; echo; if [[ ! $REPLY =~ ^[Yy]$ ]]; then echo "Deletion cancelled."; exit 0; fi; echo "Deleting index '$name'..."; response=$(curl -s -w "\n%{http_code}" -X DELETE "$API_BASE_URL/indexes/$name" -H "Api-Key: $PINECONE_API_KEY"); body=$(echo "$response" | sed '$d'); http_code=$(echo "$response" | tail -n1); if [ "$http_code" -eq 202 ]; then echo "Success: Deletion request for index '$name' accepted."; else echo "Error: Failed to delete index. Status: $http_code\nResponse: $body"; exit 1; fi; }
check_status() { if [ -z "$1" ]; then echo "Error: Index name is required for 'status'."; usage; exit 1; fi; local name="$1"; echo "Checking status for index '$name'..."; response=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE_URL/indexes/$name" -H "Api-Key: $PINECONE_API_KEY"); body=$(echo "$response" | sed '$d'); http_code=$(echo "$response" | tail -n1); if [ "$http_code" -eq 200 ]; then echo "Success. Index details:"; if command -v python3 &> /dev/null; then echo "$body" | python3 -m json.tool; else echo "$body"; fi; else echo "Error: Failed to get status for index '$name'. Status: $http_code\nResponse: $body"; exit 1; fi; }
check_stats() { if [ -z "$1" ]; then echo "Error: Index name is required for 'stats'."; usage; exit 1; fi; if ! command -v jq &> /dev/null; then echo "Error: 'jq' command is required."; exit 1; fi; local name="$1"; echo "Fetching stats for index '$name'..."; status_response=$(curl -s -X GET "$API_BASE_URL/indexes/$name" -H "Api-Key: $PINECONE_API_KEY"); index_host=$(echo "$status_response" | jq -r '.host'); if [ -z "$index_host" ] || [ "$index_host" == "null" ]; then echo "Error: Could not retrieve host for index '$name'."; exit 1; fi; response=$(curl -s -w "\n%{http_code}" -X POST "https://$index_host/describe_index_stats" -H "Content-Type: application/json" -H "Api-Key: $PINECONE_API_KEY"); body=$(echo "$response" | sed '$d'); http_code=$(echo "$response" | tail -n1); if [ "$http_code" -eq 200 ]; then echo "Success. Index statistics:"; if command -v python3 &> /dev/null; then echo "$body" | python3 -m json.tool; else echo "$body"; fi; else echo "Error: Failed to get stats. Status: $http_code\nResponse: $body"; exit 1; fi; }

# --- MODIFIED FUNCTION ---
# Function to clear vectors, now with namespace support
# Arguments: $1 = index name, $2 = (optional) namespace
clear_index() {
  if [ -z "$1" ]; then echo "Error: Index name is required for 'clear'."; usage; exit 1; fi
  if ! command -v jq &> /dev/null; then echo "Error: 'jq' command is required."; exit 1; fi
  
  local name="$1"
  local namespace="$2" # Capture the optional namespace
  local target_desc=""
  local body=""

  # Build the correct JSON payload based on whether a namespace was provided
  if [ -n "$namespace" ]; then
    target_desc="namespace '$namespace'"
    body=$(printf '{"deleteAll": true, "namespace": "%s"}' "$namespace")
  else
    target_desc="the default namespace"
    body='{"deleteAll": true}'
  fi

  read -p "Are you sure you want to delete ALL VECTORS from $target_desc in index '$name'? (y/n) " -n 1 -r; echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then echo "Clear operation cancelled."; exit 0; fi

  # Get the index host
  echo "Fetching host URL for index '$name'..."
  status_response=$(curl -s -X GET "$API_BASE_URL/indexes/$name" -H "Api-Key: $PINECONE_API_KEY")
  index_host=$(echo "$status_response" | jq -r '.host')
  if [ -z "$index_host" ] || [ "$index_host" == "null" ]; then echo "Error: Could not retrieve host for index '$name'."; exit 1; fi

  echo "Sending request to clear $target_desc..."
  response=$(curl -s -w "\n%{http_code}" -X POST "https://$index_host/vectors/delete" \
    -H "Content-Type: application/json" \
    -H "Api-Key: $PINECONE_API_KEY" \
    -d "$body")

  body=$(echo "$response" | sed '$d')
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" -eq 200 ]; then
    echo "Success: All vectors have been cleared from $target_desc."
  else
    echo "Error: Failed to clear vectors (Status: $http_code). If you are clearing the default namespace, this can mean it's already empty."
    echo "Response: $body"
    exit 1
  fi
}


# --- Main Script Logic ---

load_and_validate_env
if [ -z "$1" ]; then usage; exit 1; fi
COMMAND=$1; shift

case $COMMAND in
  list) list_indexes ;;
  create) create_index "$1" "$2" ;;
  delete) delete_index "$1" ;;
  clear) clear_index "$1" "$2" ;; # Pass both args to the function
  status|refresh) check_status "$1" ;;
  stats) check_stats "$1" ;;
  *) echo "Error: Unknown command '$COMMAND'"; usage; exit 1 ;;
esac
#!/usr/bin/env bash
# Download official FastMCP and MCP Markdown files, without models or search indexes.
# Requirements: Bash, curl, jq, sha256sum and standard Unix utilities.
# Usage: bash scripts/sync-docs.sh [destination directory]
# Each run deletes the destination and downloads a fresh copy.
set -euo pipefail

# Paths shared by the download steps.
repo_dir=""
destination_dir=""
config_file=""

check_dependencies() {
    local tool

    for tool in curl jq sha256sum; do
        if ! command -v "$tool" >/dev/null; then
            echo "Required command not found: $tool" >&2
            return 1
        fi
    done
}

# Under Git Bash, native Windows jq must produce the same line endings as Linux.
json() {
    if [[ "${OSTYPE:-}" == msys* ]]; then
        jq -b "$@"
    else
        jq "$@"
    fi
}

configure_paths() {
    local destination_parent
    local destination_name

    repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
    destination_dir="${1:-$repo_dir/documentation}"
    config_file="${DOCS_CONFIG:-$repo_dir/src/mcp_builder/config/sources.json}"

    destination_parent="$(dirname -- "$destination_dir")"
    destination_name="$(basename -- "$destination_dir")"

    # Prevent an incorrect path from replacing a parent directory or the root.
    case "$destination_name" in
        .|..|/)
            echo "Invalid destination: $destination_dir" >&2
            return 1
            ;;
    esac

    mkdir -p -- "$destination_parent"
    destination_parent="$(cd -- "$destination_parent" && pwd)"
    destination_dir="$destination_parent/$destination_name"

    # Never delete the repository itself, one of its parents, or a linked directory.
    if [[ "$repo_dir/" == "$destination_dir/"* || -L "$destination_dir" ]]; then
        echo "Unsafe reset destination: $destination_dir" >&2
        return 1
    fi
}

reset_documentation() {
    local sources_json

    # Read configuration before deleting anything, including for relative config paths.
    sources_json="$(json -e '.sources | select(type == "object" and length > 0)' < "$config_file")"

    echo "Resetting documentation: $destination_dir"
    rm -rf -- "$destination_dir"
    mkdir -p -- "$destination_dir"
    cd -- "$destination_dir"

    printf '%s\n' "$sources_json" > sources.json
    mkdir indexes
    : > documents.jsonl
}

download_file() {
    local url="$1"
    local output_file="$2"

    mkdir -p -- "$(dirname -- "$output_file")"
    curl \
        --fail \
        --location \
        --silent \
        --show-error \
        --retry 3 \
        --connect-timeout 20 \
        --max-time 120 \
        --output "$output_file" \
        "$url"

    if [[ ! -s "$output_file" ]]; then
        echo "Empty page: $url" >&2
        return 1
    fi

    # Some website errors return an HTML page with HTTP status 200.
    if head -c 512 "$output_file" | grep -Eiq '^[[:space:]]*(<!doctype html|<html)'; then
        echo "Unexpected HTML response: $url" >&2
        return 1
    fi
}

# sha256sum also prints the filename; keep only the checksum.
file_sha256() {
    local checksum

    checksum="$(sha256sum "$1")"
    printf '%s\n' "${checksum%% *}"
}

extract_pages() {
    local source_name="$1"
    local index_url="$2"
    local origin="${index_url%/llms.txt}/"

    # Read [title](URL) links, keep Markdown pages from the same site and deduplicate.
    # Preserve official paths locally; use a date in the URL as the version, if present.
    json -Rsc --arg origin "$origin" --arg source "$source_name" '
        [
            scan("\\[([^\\]]+)\\]\\((https?://[^\\s)]+)\\)")
            | {title: .[0], url: (.[1] | split("#")[0])}
            | select(.url | startswith($origin))
            | select(.url | endswith(".md"))
            | . + {
                source: $source,
                path: ("docs/" + $source + "/" + (.url | ltrimstr($origin))),
                version: (
                    [.url | match("[0-9]{4}-[0-9]{2}-[0-9]{2}").string][0]
                    // "unversioned"
                )
            }
        ]
        | unique_by(.url)
        | .[]
    ' < "indexes/$source_name.txt" > pages.jsonl

    if [[ ! -s pages.jsonl ]]; then
        echo "No Markdown pages found: $index_url" >&2
        return 1
    fi
}

download_page() {
    local page_json="$1"
    local page_path
    local page_url
    local checksum

    page_path="$(json -r '.path' <<< "$page_json")"
    page_url="$(json -r '.url' <<< "$page_json")"

    # Remote links must never allow writes outside the docs/ directory.
    if [[ ! "$page_path" =~ ^docs/[a-zA-Z0-9_./-]+\.md$ || "/$page_path/" == *'/../'* ]]; then
        echo "Invalid page path: $page_path" >&2
        return 1
    fi

    download_file "$page_url" "$page_path"
    checksum="$(file_sha256 "$page_path")"

    json --arg hash "$checksum" '
        . + {id: .path, sha256: $hash}
    ' <<< "$page_json" >> documents.jsonl
}

download_sources() {
    local source_name
    local index_url
    local page_json

    while IFS=$'\t' read -r source_name index_url; do
        echo "Downloading: $source_name"
        download_file "$index_url" "indexes/$source_name.txt"
        extract_pages "$source_name" "$index_url"

        while IFS= read -r page_json; do
            download_page "$page_json"
        done < pages.jsonl
    done < <(json -r 'to_entries[] | [.key, .value] | @tsv' sources.json)
}

create_file_inventory() {
    local file_path
    local checksum

    # Inventory downloaded files only, excluding temporary JSON files.
    find docs indexes -type f | sort | while IFS= read -r file_path; do
        checksum="$(file_sha256 "$file_path")"
        json -n --arg path "$file_path" --arg hash "$checksum" '
            {key: $path, value: $hash}
        '
    done | json -s 'from_entries' > files.json
}

create_manifest() {
    create_file_inventory
    json -s '.' documents.jsonl > documents.json

    # The build uses this manifest to verify files and their provenance.
    json -n \
        --slurpfile docs documents.json \
        --slurpfile files files.json \
        --slurpfile sources sources.json \
        --arg date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
        {
            schema: 1,
            kind: "sources",
            complete: true,
            created_at: $date,
            documents: $docs[0],
            files: $files[0],
            sources: ($sources[0] | with_entries(.value = {index_url: .value}))
        }
    ' > manifest.json

    rm documents.jsonl documents.json pages.jsonl files.json sources.json
}

main() {
    check_dependencies
    configure_paths "$@"
    reset_documentation
    download_sources
    create_manifest
    chmod -R a+rX "$destination_dir"
    echo "Documentation ready to commit: $destination_dir"
}

main "$@"

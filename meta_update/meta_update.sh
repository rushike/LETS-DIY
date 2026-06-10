#!/usr/bin/env bash

# ==============================================================================
# Script Name: gmeta_update (Version 2 - Native EXIF Priority)
# Target path: /usr/local/bin/gmeta_update
# ==============================================================================

if ! command -v exiftool &> /dev/null; then
    echo "Error: 'exiftool' is required but not installed." >&2
    exit 1
fi

if [ "$#" -lt 1 ]; then
    echo "Usage: gmeta_update <file_or_takeout_directory_1> [directory_2 ...]"
    exit 1
fi

process_file() {
    local file="$1"
    local json_sidecar="${file}.json"
    
    # Check for extension-clipped JSON sidecar files (e.g. image.jpg -> image.json)
    if [ ! -f "$json_sidecar" ]; then
        json_sidecar="${file%.*}.json"
    fi

    # --- PHASE 1: CHOOSE THE CREATION DATE ---
    local target_date=""

    # 1. Look inside the actual file first for existing EXIF tags
    local native_date
    native_date=$(exiftool -s -s -s -DateTimeOriginal "$file" 2>/dev/null)
    [ -z "$native_date" ] && native_date=$(exiftool -s -s -s -CreateDate "$file" 2>/dev/null)

    if [ ! -z "$native_date" ] && [[ "$native_date" =~ [0-9]{4} ]]; then
        # Found existing internal metadata! Use it.
        target_date="$native_date"
    elif [ -f "$json_sidecar" ]; then
        # Native EXIF is empty, extract date from Google JSON schema
        local taken_time
        taken_time=$(grep -A 2 '"photoTakenTime":' "$json_sidecar" | grep '"timestamp":' | sed -E 's/.*"([^"]+)".*/\1/')
        [ -z "$taken_time" ] || [ "$taken_time" == "0" ] && taken_time=$(grep -A 2 '"creationTime":' "$json_sidecar" | grep '"timestamp":' | sed -E 's/.*"([^"]+)".*/\1/')

        if [ ! -z "$taken_time" ] && [ "$taken_time" != "0" ]; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                target_date=$(date -r "$taken_time" +"%Y:%m:%d %H:%M:%S" 2>/dev/null)
            else
                target_date=$(date -d "@$taken_time" +"%Y:%m:%d %H:%M:%S" 2>/dev/null)
            fi
        fi
    fi

    # Last resort fallback: if both file EXIF and JSON failed, parse the filename string
    if [ -z "$target_date" ]; then
        # ExifTool naturally interprets timestamp fragments inside names like 'IMG_20241011...'
        exiftool -m "-FileModifyDate<FileName" -overwrite_original "$file" &> /dev/null
        if [[ "$OSTYPE" == "darwin"* ]]; then
            exiftool -m "-FileCreateDate<FileName" -overwrite_original "$file" &> /dev/null
        fi
    fi

    # --- PHASE 2: INJECT ALL METADATA & SIDE FIELDS ---
    local args=("-m" "-overwrite_original")

    # If we settled on a clear target date, map it across all system and media attributes
    if [ ! -z "$target_date" ]; then
        args+=("-DateTimeOriginal=$target_date" "-CreateDate=$target_date" "-ModifyDate=$target_date")
        args+=("-FileModifyDate=$target_date")
        if [[ "$OSTYPE" == "darwin"* ]]; then
            args+=("-FileCreateDate=$target_date")
        fi
    fi

    # Always pull and update peripheral metadata fields if the JSON sidecar is present
    if [ -f "$json_sidecar" ]; then
        local desc title lat lon alt
        title=$(grep '"title":' "$json_sidecar" | sed -E 's/.*"title":\s*"(.*)".*/\1/')
        desc=$(grep '"description":' "$json_sidecar" | sed -E 's/.*"description":\s*"(.*)".*/\1/')
        lat=$(grep '"latitude":' "$json_sidecar" | sed -E 's/.*"latitude":\s*([0-9.-]+).*/\1/')
        lon=$(grep '"longitude":' "$json_sidecar" | sed -E 's/.*"longitude":\s*([0-9.-]+).*/\1/')
        alt=$(grep '"altitude":' "$json_sidecar" | sed -E 's/.*"altitude":\s*([0-9.-]+).*/\1/')

        [ ! -z "$title" ] && args+=("-Title=$title" "-ObjectName=$title")
        [ ! -z "$desc" ] && args+=("-Description=$desc" "-UserComment=$desc")

        if [ ! -z "$lat" ] && [ "$lat" != "0.0" ] && [ "$lat" != "0" ]; then
            args+=("-GPSLatitude=$lat" "-GPSLongitude=$lon" "-GPSAltitude=$alt")
            args+=("-GPSLatitudeRef=$([[ $(echo "$lat > 0" | bc -l 2>/dev/null) -eq 1 ]] && echo "N" || echo "S")")
            args+=("-GPSLongitudeRef=$([[ $(echo "$lon > 0" | bc -l 2>/dev/null) -eq 1 ]] && echo "E" || echo "W")")
        fi
    fi

    # Execute binary payload update
    exiftool "${args[@]}" "$file" &> /dev/null
}

# Main Target Iterator Loop
for item in "$@"; do
    if [ -f "$item" ]; then
        [[ "$item" == *.json ]] && continue
        process_file "$item"
    elif [ -d "$item" ]; then
        echo "Scanning Takeout Directory: $item"
        find "$item" -type f ! -name "*.json" | while read -r target; do
            process_file "$target"
        done
    else
        echo "Warning: Component structure '$item' is invalid. Skipping." >&2
    fi
done

echo "Metadata synchronization complete!"
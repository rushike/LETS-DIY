## Metadata Tag
### gmeta_update
This modifies create time of file, got from google take out. Instead of create time of downloaded it update file time to that of created, or uploaded to drive.

**High-level flow step summary**
1. Validate exiftool and parse options.
2. For each input file or directory:
    - Resolve JSON sidecar metadata if available.
    - Determine an accurate timestamp from EXIF or JSON.
    - Fallback to filename timestamp if needed.
    - Build ExifTool commands for timestamps, title/description, and GPS.
    - Apply metadata updates either in place or to an output folder.

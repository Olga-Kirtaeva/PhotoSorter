# PhotoSorter

PhotoSorter copies photos into event folders based on EXIF capture dates. When GPS metadata is available, it uses OpenStreetMap Nominatim reverse geocoding to include place names.

The original files are not modified. Existing destination files are skipped.

## Requirements

- Python 3.14 or newer
- Internet access for reverse geocoding
- `uv` (recommended) or another Python package manager

## Installation

```powershell
uv sync
```

## Usage

Pass the source and destination folders at runtime. Do not put personal paths into the source code.

```powershell
uv run python sort_photos.py --input "D:\Photos\Unsorted" --output "D:\Photos\Sorted"
```

The input and output folders must be different. The output directory is created automatically.

## Privacy

Photo files can contain sensitive EXIF and GPS metadata. Photos and common video formats are excluded by `.gitignore`; do not force-add them to Git. Local environment files, IDE settings, and virtual environments are excluded too.

Reverse geocoding sends GPS coordinates from up to ten photos per event to the public Nominatim service. Review the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) before processing a large collection.

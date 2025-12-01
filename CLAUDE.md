- GeoData Aggregator - Claude Code Project Specification

## What We're Building

A platform that aggregates geospatial datasets from many different geoservers into one searchable catalogue. Users can discover data by location, download it in various formats, and export to their own systems.

## Core Design Principles

1. **Change Detection Over Bulk Download**: Don't re-download data that hasn't changed. Probe sources cheaply (HTTP HEAD, metadata timestamps) before expensive downloads.

2. **Opt[...Truncated text #1 +1709 lines...]e** | Cheap check to see if data changed (no download) |
| **Crawl** | Full discovery of all datasets on a server |
| **Catalogue** | Our database of dataset metadata |
| **Cache** | Local copy of actual geodata (features) |
| **Chunk** | Portion of large dataset for parallel download |
| **OID** | ObjectID - unique feature identifier in ArcGIS |
| **Landing zone** | Object storage where downloads land before processing |
| **Strategy** | Download approach: simple, paged, chunked, distributed |
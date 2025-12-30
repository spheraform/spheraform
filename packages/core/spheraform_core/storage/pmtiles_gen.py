"""PMTiles generation utilities for vector tile serving."""

import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default zoom levels for PMTiles
DEFAULT_MIN_ZOOM = 0
DEFAULT_MAX_ZOOM = 22  # High zoom for detailed geometry preservation


class PMTilesGenerationError(Exception):
    """Raised when PMTiles generation fails."""
    pass


def check_tippecanoe_installed() -> bool:
    """
    Check if tippecanoe is installed and available.

    Returns:
        True if tippecanoe is available, False otherwise
    """
    return shutil.which("tippecanoe") is not None


def generate_from_geojson(
    geojson_path: str | Path,
    pmtiles_path: str | Path,
    min_zoom: int = DEFAULT_MIN_ZOOM,
    max_zoom: int = DEFAULT_MAX_ZOOM,
    layer_name: Optional[str] = None,
    simplification: int = 10,
    buffer: int = 64,
) -> dict:
    """
    Generate PMTiles from GeoJSON using tippecanoe.

    Requires tippecanoe to be installed on the system.
    Install with: brew install tippecanoe (macOS) or build from source

    Args:
        geojson_path: Path to input GeoJSON file
        pmtiles_path: Path to output PMTiles file
        min_zoom: Minimum zoom level (default: 0)
        max_zoom: Maximum zoom level (default: 14)
        layer_name: Layer name in PMTiles (default: filename without extension)
        simplification: Simplification level (default: 10)
        buffer: Buffer size in pixels (default: 256)

    Returns:
        Dict with metadata (size_bytes, min_zoom, max_zoom, layer_name)

    Raises:
        PMTilesGenerationError: If tippecanoe is not installed or generation fails
    """
    if not check_tippecanoe_installed():
        raise PMTilesGenerationError(
            "tippecanoe is not installed. "
            "Install with: brew install tippecanoe (macOS) "
            "or build from source: https://github.com/felt/tippecanoe"
        )

    geojson_path = Path(geojson_path)
    pmtiles_path = Path(pmtiles_path)

    if not geojson_path.exists():
        raise FileNotFoundError(f"GeoJSON file not found: {geojson_path}")

    # Determine layer name
    if layer_name is None:
        layer_name = geojson_path.stem

    logger.info(f"Generating PMTiles from {geojson_path}")
    logger.info(f"Zoom levels: {min_zoom}-{max_zoom}, Layer: {layer_name}")

    # Create parent directory if needed
    pmtiles_path.parent.mkdir(parents=True, exist_ok=True)

    # Build tippecanoe command
    # PMTiles v3 uses WGS84 (EPSG:4326) for metadata and bounds
    cmd = [
        "tippecanoe",
        "--output", str(pmtiles_path),
        "--force",  # Overwrite if exists
        "--minimum-zoom", str(min_zoom),
        "--maximum-zoom", str(max_zoom),
        "--layer", layer_name,
        "--simplification", str(simplification),
        "--buffer", str(buffer),
        "--projection=EPSG:4326",  # Input data is in WGS84, output bounds in WGS84
        "--no-feature-limit",  # Generate all zoom levels even for small/clustered datasets
        "--drop-densest-as-needed",  # Auto simplify if too many features
        "--extend-zooms-if-still-dropping",  # Preserve features
        str(geojson_path),
    ]

    logger.debug(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        logger.debug(f"tippecanoe stdout: {result.stdout}")

        if result.stderr:
            logger.warning(f"tippecanoe stderr: {result.stderr}")

    except subprocess.CalledProcessError as e:
        logger.error(f"tippecanoe failed: {e.stderr}")
        raise PMTilesGenerationError(f"PMTiles generation failed: {e.stderr}") from e

    # Get file size
    size_bytes = pmtiles_path.stat().st_size

    logger.info(f"PMTiles generated: {pmtiles_path} ({size_bytes} bytes)")

    return {
        "size_bytes": size_bytes,
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
        "layer_name": layer_name,
    }


def generate_from_geoparquet(
    parquet_path: str | Path,
    pmtiles_path: str | Path,
    min_zoom: int = DEFAULT_MIN_ZOOM,
    max_zoom: int = DEFAULT_MAX_ZOOM,
    layer_name: Optional[str] = None,
    simplification: int = 10,
    buffer: int = 64,
) -> dict:
    """
    Generate PMTiles from GeoParquet.

    Converts GeoParquet to GeoJSON first, then generates PMTiles using tippecanoe.

    Args:
        parquet_path: Path to input GeoParquet file
        pmtiles_path: Path to output PMTiles file
        min_zoom: Minimum zoom level (default: 0)
        max_zoom: Maximum zoom level (default: 14)
        layer_name: Layer name in PMTiles (default: filename without extension)
        simplification: Simplification level (default: 10)
        buffer: Buffer size in pixels (default: 256)

    Returns:
        Dict with metadata (size_bytes, min_zoom, max_zoom, layer_name)

    Raises:
        PMTilesGenerationError: If tippecanoe is not installed or generation fails
    """
    import tempfile
    from .geoparquet import geoparquet_to_geojson

    parquet_path = Path(parquet_path)
    pmtiles_path = Path(pmtiles_path)

    logger.info(f"Generating PMTiles from GeoParquet: {parquet_path}")

    # Convert to temporary GeoJSON
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".geojson", delete=False
    ) as temp_geojson:
        temp_geojson_path = Path(temp_geojson.name)

    try:
        # Convert GeoParquet to GeoJSON
        logger.debug(f"Converting to temporary GeoJSON: {temp_geojson_path}")
        geoparquet_to_geojson(parquet_path, temp_geojson_path)

        # Generate PMTiles from GeoJSON
        result = generate_from_geojson(
            temp_geojson_path,
            pmtiles_path,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            layer_name=layer_name,
            simplification=simplification,
            buffer=buffer,
        )

        return result

    finally:
        # Clean up temporary GeoJSON
        if temp_geojson_path.exists():
            temp_geojson_path.unlink()
            logger.debug(f"Cleaned up temporary GeoJSON: {temp_geojson_path}")


def validate_pmtiles(pmtiles_path: str | Path) -> dict:
    """
    Validate PMTiles file and extract metadata.

    Args:
        pmtiles_path: Path to PMTiles file

    Returns:
        Dict with validation info (valid, error, metadata)
    """
    pmtiles_path = Path(pmtiles_path)

    if not pmtiles_path.exists():
        return {"valid": False, "error": "File not found"}

    try:
        # Use pmtiles CLI if available
        if shutil.which("pmtiles"):
            result = subprocess.run(
                ["pmtiles", "show", str(pmtiles_path)],
                capture_output=True,
                text=True,
                check=True,
            )

            return {
                "valid": True,
                "metadata": result.stdout,
            }
        else:
            # Basic validation - just check file size
            size = pmtiles_path.stat().st_size

            if size < 100:  # PMTiles header is at least 127 bytes
                return {"valid": False, "error": "File too small to be valid PMTiles"}

            return {
                "valid": True,
                "metadata": f"File size: {size} bytes (pmtiles CLI not available for detailed validation)",
            }

    except subprocess.CalledProcessError as e:
        return {
            "valid": False,
            "error": f"Validation failed: {e.stderr}",
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
        }

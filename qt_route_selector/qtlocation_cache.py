from __future__ import annotations

from pathlib import Path

from .runtime_paths import runtime_root


_CACHE_PARAMETER = "osm.mapping.cache.directory"
_PLUGIN_MARKER = 'Plugin {\n        id: osmPlugin\n        name: "osm"\n'


def osm_tile_cache_dir(name: str) -> Path:
    """Return a dedicated writable QtLocation tile-cache directory."""
    safe_name = "".join(ch for ch in str(name).strip().lower() if ch.isalnum() or ch in {"-", "_"})
    if not safe_name:
        safe_name = "map"
    path = runtime_root() / "cache" / "qtlocation" / safe_name
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _qml_string(value: str | Path) -> str:
    # QML accepts forward slashes on Windows. Keeping the value slash-normalized
    # also avoids accidental backslash escape sequences in the generated source.
    return str(value).replace("\\", "/").replace('"', '\\"')


def inject_osm_cache_directory(qml_text: str, cache_directory: str | Path) -> str:
    """Add an explicit OSM disk-cache directory to one existing osmPlugin block."""
    if _CACHE_PARAMETER in qml_text:
        return qml_text
    if _PLUGIN_MARKER not in qml_text:
        raise RuntimeError("OSM-Pluginblock im QML wurde nicht gefunden.")

    block = (
        "\n        PluginParameter {\n"
        f'            name: "{_CACHE_PARAMETER}"\n'
        f'            value: "{_qml_string(cache_directory)}"\n'
        "        }\n"
    )
    return qml_text.replace(_PLUGIN_MARKER, _PLUGIN_MARKER + block, 1)


def prepared_qml_directory(source_file: str | Path, cache_name: str) -> Path:
    """Write a runtime QML copy whose OSM plugin uses an isolated disk cache.

    The repository QML remains the source of truth. A fresh generated copy is
    written on every start, so normal git updates are picked up immediately.
    """
    source = Path(source_file).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"QML-Datei nicht gefunden: {source}")

    cache_directory = osm_tile_cache_dir(cache_name)
    generated_directory = runtime_root() / "cache" / "qml" / cache_name
    generated_directory.mkdir(parents=True, exist_ok=True)
    generated_file = generated_directory / source.name

    text = source.read_text(encoding="utf-8")
    patched = inject_osm_cache_directory(text, cache_directory)
    generated_file.write_text(patched, encoding="utf-8")
    return generated_directory.resolve()


__all__ = [
    "inject_osm_cache_directory",
    "osm_tile_cache_dir",
    "prepared_qml_directory",
]

"""Construye el paquete portable y reproducible de HeatGuard v0.31."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile


ROOT_NAME = "HeatGuard_Clip_v0.31_STABLE"
SKIP_DIRS = {
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv",
    "__pycache__", "heatguard_backend.egg-info",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".sqlite", ".sqlite3", ".db"}


def included(source: Path, path: Path) -> bool:
    relative = path.relative_to(source)
    if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in relative.parts):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return path.is_file()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(source: Path, output: Path) -> tuple[Path, Path]:
    source = source.resolve()
    output = output.resolve()
    release_dir = output / ROOT_NAME
    archive = output / f"{ROOT_NAME}.zip"
    if release_dir.exists() or archive.exists():
        raise FileExistsError("El destino v0.31 ya existe; use un directorio de salida nuevo")
    output.mkdir(parents=True, exist_ok=True)

    files = sorted((p for p in source.rglob("*") if included(source, p)),
                   key=lambda p: p.relative_to(source).as_posix())
    for path in files:
        destination = release_dir / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as bundle:
        for path in files:
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(f"{ROOT_NAME}/{relative}", (2026, 11, 15, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes(), compresslevel=9)

    for name in ("CHANGELOG_v0.31.md", "TEST_REPORT.md", "INFORME_INTEGRACION.md", "README.md"):
        shutil.copy2(source / name, output / name)
    evidence_out = output / "evidence"
    evidence_out.mkdir()
    for path in sorted((source / "docs" / "evidence").glob("panel_v031_*.png")):
        shutil.copy2(path, evidence_out / path.name)

    checksum = output / "SHA256SUMS_v0.31.txt"
    checksum.write_text(f"{sha256(archive)}  {archive.name}\n", encoding="utf-8", newline="\n")
    return release_dir, archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    release_dir, archive = build(args.source, args.output)
    print(release_dir)
    print(archive)
    print(sha256(archive))


if __name__ == "__main__":
    main()

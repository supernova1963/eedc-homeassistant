"""
Infothek Datei-Service

Verarbeitet Bilder (Resize, Thumbnail, EXIF-Rotation, HEIC→JPEG)
und validiert PDFs.
"""

import io
import logging
from PIL import Image, ExifTags

logger = logging.getLogger(__name__)

# Limits
MAX_IMAGE_BYTES = 500_000       # 500 KB nach Resize
MAX_THUMBNAIL_BYTES = 50_000    # ~50 KB
MAX_PDF_BYTES = 5_242_880       # 5 MB
MAX_DATEIEN_PRO_EINTRAG = 3
THUMBNAIL_SIZE = (200, 200)

ERLAUBTE_BILD_TYPES = {"image/jpeg", "image/png", "image/heic", "image/heif"}
ERLAUBTE_PDF_TYPES = {"application/pdf"}
ERLAUBTE_TYPES = ERLAUBTE_BILD_TYPES | ERLAUBTE_PDF_TYPES


def ist_bild(mime_type: str) -> bool:
    return mime_type in ERLAUBTE_BILD_TYPES


def ist_pdf(mime_type: str) -> bool:
    return mime_type in ERLAUBTE_PDF_TYPES


def validiere_dateityp(mime_type: str) -> str:
    """Gibt 'image' oder 'pdf' zurück, oder wirft ValueError."""
    if ist_bild(mime_type):
        return "image"
    if ist_pdf(mime_type):
        return "pdf"
    raise ValueError(
        f"Dateityp '{mime_type}' nicht erlaubt. "
        f"Erlaubt: JPEG, PNG, HEIC (Bilder) und PDF."
    )


def _korrigiere_exif_rotation(img: Image.Image) -> Image.Image:
    """Dreht das Bild basierend auf EXIF-Orientierung (iPhone-Fotos)."""
    try:
        exif = img.getexif()
        if not exif:
            return img

        orientation_tag = None
        for tag, name in ExifTags.TAGS.items():
            if name == "Orientation":
                orientation_tag = tag
                break

        if orientation_tag is None or orientation_tag not in exif:
            return img

        orientation = exif[orientation_tag]
        if orientation == 3:
            img = img.rotate(180, expand=True)
        elif orientation == 6:
            img = img.rotate(270, expand=True)
        elif orientation == 8:
            img = img.rotate(90, expand=True)
    except Exception:
        pass  # EXIF-Fehler ignorieren
    return img


def _heic_zu_jpeg(daten: bytes) -> Image.Image:
    """Konvertiert HEIC-Daten zu einem PIL Image."""
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        raise ValueError("HEIC-Support nicht verfügbar (pillow-heif nicht installiert)")

    return Image.open(io.BytesIO(daten))


def _resize_bild(img: Image.Image, max_bytes: int, min_quality: int = 60) -> bytes:
    """Resized ein Bild iterativ bis es unter max_bytes liegt."""
    # RGBA → RGB konvertieren (JPEG unterstützt kein Alpha)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Erst versuchen ohne Resize
    for quality in range(85, min_quality - 1, -5):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= max_bytes:
            return buf.getvalue()

    # Bild schrittweise verkleinern
    current = img
    for scale in [0.75, 0.5, 0.35, 0.25]:
        new_size = (int(img.width * scale), int(img.height * scale))
        current = img.resize(new_size, Image.LANCZOS)
        for quality in range(80, min_quality - 1, -10):
            buf = io.BytesIO()
            current.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= max_bytes:
                return buf.getvalue()

    # Letzter Versuch: kleinste Variante
    buf = io.BytesIO()
    current.save(buf, format="JPEG", quality=min_quality, optimize=True)
    return buf.getvalue()


def verarbeite_bild(daten: bytes, mime_type: str) -> tuple[bytes, bytes, str]:
    """
    Verarbeitet ein hochgeladenes Bild.

    Returns:
        (bild_daten, thumbnail_daten, mime_type)
    """
    # HEIC konvertieren
    if mime_type in ("image/heic", "image/heif"):
        img = _heic_zu_jpeg(daten)
    else:
        img = Image.open(io.BytesIO(daten))

    # EXIF-Rotation korrigieren
    img = _korrigiere_exif_rotation(img)

    # Hauptbild resizen
    bild_daten = _resize_bild(img, MAX_IMAGE_BYTES)

    # Thumbnail erzeugen
    thumb = img.copy()
    thumb.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
    if thumb.mode in ("RGBA", "P"):
        thumb = thumb.convert("RGB")
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=70, optimize=True)
    thumbnail_daten = buf.getvalue()

    # Falls Thumbnail immer noch zu groß
    if len(thumbnail_daten) > MAX_THUMBNAIL_BYTES:
        thumbnail_daten = _resize_bild(thumb, MAX_THUMBNAIL_BYTES, min_quality=40)

    logger.info(
        f"Bild verarbeitet: {len(daten)} → {len(bild_daten)} bytes, "
        f"Thumbnail: {len(thumbnail_daten)} bytes"
    )

    return bild_daten, thumbnail_daten, "image/jpeg"


def validiere_pdf(daten: bytes) -> bytes:
    """Validiert PDF-Größe und gibt die Daten zurück."""
    if len(daten) > MAX_PDF_BYTES:
        mb = len(daten) / 1_048_576
        raise ValueError(
            f"PDF zu groß ({mb:.1f} MB). Maximum: {MAX_PDF_BYTES / 1_048_576:.0f} MB."
        )
    # Einfache PDF-Signatur-Prüfung
    if not daten[:5] == b"%PDF-":
        raise ValueError("Ungültige PDF-Datei.")
    return daten

import base64
from pathlib import Path


def read_multiline(prompt: str) -> str:
    """Collect input lines until the user submits a blank line."""
    print(prompt)
    lines = []
    while True:
        line = input()
        if line == "":
            if lines:
                break
        else:
            lines.append(line)
    return "\n".join(lines)


def encode_file_as_images(file_path: str) -> list[tuple[str, str]]:
    """Return a list of (base64_data, mime_type) for each page/image in the file."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            pages.append((base64.b64encode(pix.tobytes("png")).decode(), "image/png"))
        doc.close()
        return pages

    elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        with open(file_path, "rb") as f:
            return [(base64.b64encode(f.read()).decode(), mime)]

    else:
        raise ValueError(f"Unsupported file type: {suffix}. Supported: .pdf, .png, .jpg, .jpeg, .webp, .gif")

import sys
import base64
from pathlib import Path
from langchain_core.messages import HumanMessage
from llms import chat_llm

# PLACEHOLDER QUERY - Fill this with your question about the document
DOCUMENT_QUERY = """from the given document, extract if present - 
- Doctor name, registration number, specialization
- Patient name, age, gender, date
- Diagnosis (primary and secondary if any)
- Medicines with dosage and duration
- Tests ordered
- Hospital/clinic name and address

print it all out as a json object.
"""


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


def test_gpt5_document_reading(file_path: str):
    """Test if GPT-5 can read and understand documents using vision."""

    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {file_path}")
        return

    print(f"Encoding document as image(s): {path.name}")
    try:
        pages = encode_file_as_images(str(path))
    except Exception as e:
        print(f"Error encoding document: {e}")
        return

    print(f"  {len(pages)} page(s) encoded.")

    # Build the message content: instruction text + one image block per page
    content = [{"type": "text", "text": f"Please read and analyze the following document.\n\n{DOCUMENT_QUERY}"}]
    for b64_data, mime in pages:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64_data}"},
        })

    print("Sending document to GPT-5...")
    print("-" * 60)

    response = chat_llm.invoke([HumanMessage(content=content)])

    print("Response from GPT-5:")
    print("-" * 60)
    print(response.content)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_gpt5_document.py <file_path>")
        print("Example: python test_gpt5_document.py document.pdf")
        sys.exit(1)

    test_gpt5_document_reading(sys.argv[1])

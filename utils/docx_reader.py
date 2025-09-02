import docx

def extract_text_from_docx(filepath):
    """Extract plain text from a .docx file."""
    doc = docx.Document(filepath)
    text = []
    for para in doc.paragraphs:
        if para.text.strip():
            text.append(para.text.strip())
    return "\n".join(text)

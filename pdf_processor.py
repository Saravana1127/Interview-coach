import pypdf

def extract_text_from_pdf(file_obj) -> str:
    """
    Extract raw text from a PDF file-like object.
    Returns a string of extracted text.
    """
    try:
        reader = pypdf.PdfReader(file_obj)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        raise RuntimeError(f"Error parsing PDF: {str(e)}")

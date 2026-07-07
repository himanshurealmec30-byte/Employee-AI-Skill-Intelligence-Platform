import io
from pypdf import PdfReader
from docx import Document

def read_pdf(file_bytes):
    """Extracts text from PDF file bytes."""
    try:
        pdf_file = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        raise ValueError(f"Failed to read PDF: {e}")

def read_docx(file_bytes):
    """Extracts text from DOCX file bytes."""
    try:
        docx_file = io.BytesIO(file_bytes)
        doc = Document(docx_file)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    except Exception as e:
        raise ValueError(f"Failed to read DOCX: {e}")

def read_txt(file_bytes):
    """Extracts text from plain text file bytes."""
    try:
        return file_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        raise ValueError(f"Failed to read TXT: {e}")

def extract_text_from_file(uploaded_file):
    """
    Extracts text from a Streamlit UploadedFile object.
    
    Args:
        uploaded_file: Streamlit UploadedFile
        
    Returns:
        str: Extracted text content.
    """
    if uploaded_file is None:
        return ""
        
    file_bytes = uploaded_file.read()
    # Reset file pointer for future reads if needed
    uploaded_file.seek(0)
    
    filename = uploaded_file.name.lower()
    
    if filename.endswith('.pdf'):
        return read_pdf(file_bytes)
    elif filename.endswith('.docx'):
        return read_docx(file_bytes)
    elif filename.endswith('.txt'):
        return read_txt(file_bytes)
    else:
        # Fallback to text decoding
        return read_txt(file_bytes)

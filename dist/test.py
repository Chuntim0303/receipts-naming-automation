import fitz  # PyMuPDF
import os
from pathlib import Path

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text += f"\n{'='*60}\n"
            text += f"PAGE {page_num + 1}\n"
            text += f"{'='*60}\n"
            text += page.get_text()
        
        doc.close()
        return text
    except Exception as e:
        return f"Error processing PDF: {e}"

def extract_all_pdfs(input_folder):
    """Extract text from all PDFs in folder and display"""
    input_path = Path(input_folder)
    pdf_files = [f for f in input_path.iterdir() if f.suffix.lower() == '.pdf']
    
    if not pdf_files:
        print(f"No PDF files found in '{input_folder}' folder.")
        return
    
    print(f"Found {len(pdf_files)} PDF file(s)\n")
    
    for idx, pdf_file in enumerate(pdf_files, 1):
        print("\n" + "="*80)
        print(f"FILE {idx}/{len(pdf_files)}: {pdf_file.name}")
        print("="*80)
        
        text = extract_text_from_pdf(str(pdf_file))
        print(text)
        
        print("\n" + "-"*80)
        print("END OF FILE")
        print("-"*80 + "\n")

if __name__ == "__main__":
    input_folder = "receipts"
    
    if os.path.exists(input_folder):
        extract_all_pdfs(input_folder)
    else:
        print(f"ERROR: Folder '{input_folder}' not found.")
        print("Please create a 'receipts' folder and add your PDF files.")
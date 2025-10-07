import fitz  # PyMuPDF
import os
import re
import csv
from pathlib import Path

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text += page.get_text()
        
        doc.close()
        return text
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return ""

def extract_recipient_name(text):
    """
    Extract recipient name from bank transfer receipt.
    Looks for patterns like:
    - "To Account No. / DuitNow ID: ... / NAME"
    - "Transfer To\nNAME"
    """
    lines = text.split('\n')
    
    # Pattern 1: CIMB format - "6467026903/ TIEU POH SIN"
    for line in lines:
        if 'To Account No.' in line or 'DuitNow ID' in line:
            # Look for pattern: number / NAME
            match = re.search(r':\s*[\d\s/]+/\s*([A-Z\s]+(?:[A-Z\s]+)*)', line)
            if match:
                name = match.group(1).strip()
                if len(name) > 3 and not name.isdigit():
                    return name
    
    # Pattern 2: Maybank format - "Transfer To" followed by name on next line
    for i, line in enumerate(lines):
        if 'Transfer To' in line and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # Check if next line looks like a name (all caps, letters and spaces)
            if next_line and len(next_line) > 3:
                # Should be mostly uppercase letters
                if re.match(r'^[A-Z\s]+$', next_line):
                    return next_line
    
    # Pattern 3: Look for "/ NAME" pattern after account numbers
    for line in lines:
        match = re.search(r'/\s*([A-Z][A-Z\s]+[A-Z])\s*$', line)
        if match:
            name = match.group(1).strip()
            words = name.split()
            if 2 <= len(words) <= 6 and len(name) > 5:
                return name
    
    return None

def extract_amount(text):
    """Extract payment amount from receipt text"""
    patterns = [
        r'Amount[\s:]*(?:MYR|RM)\s*([\d,]+\.?\d*)',
        r'Total Debit Amount[\s:]*(?:MYR|RM)\s*([\d,]+\.?\d*)',
        r'(?:MYR|RM)\s*([\d,]+\.?\d{2})',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            amount = matches[0].replace(',', '')
            try:
                amount_float = float(amount)
                if amount_float > 0:
                    return f"RM{amount_float:.2f}"
            except ValueError:
                continue
    
    return None

def sanitize_filename(name):
    """Remove invalid characters from filename"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '')
    return name.strip()

def process_pdf_receipts(input_folder, output_csv):
    """
    Process all PDF receipts in a folder and rename them.
    
    Args:
        input_folder: Path to folder containing PDF receipts
        output_csv: Path to output CSV file
    """
    results = []
    renamed_count = 0
    
    input_path = Path(input_folder)
    pdf_files = [f for f in input_path.iterdir() if f.suffix.lower() == '.pdf']
    
    print(f"Found {len(pdf_files)} PDF receipts to process...")
    print("-" * 60)
    
    for idx, pdf_file in enumerate(pdf_files, 1):
        print(f"\nProcessing {idx}/{len(pdf_files)}: {pdf_file.name}")
        
        text = extract_text_from_pdf(str(pdf_file))
        
        new_filename = pdf_file.name
        
        if text:
            print(f"Text extracted: {len(text)} characters")
            
            recipient_name = extract_recipient_name(text)
            amount = extract_amount(text)
            
            print(f"Recipient name: {recipient_name if recipient_name else 'Not found'}")
            print(f"Amount: {amount if amount else 'Not found'}")
            
            if recipient_name and amount:
                safe_name = sanitize_filename(f"{recipient_name} - {amount}")
                new_filename = f"{safe_name}.pdf"
                new_path = pdf_file.parent / new_filename
                
                counter = 1
                while new_path.exists() and new_path != pdf_file:
                    safe_name = sanitize_filename(f"{recipient_name} - {amount}_{counter}")
                    new_filename = f"{safe_name}.pdf"
                    new_path = pdf_file.parent / new_filename
                    counter += 1
                
                try:
                    pdf_file.rename(new_path)
                    print(f"✓ Renamed to: {new_filename}")
                    renamed_count += 1
                except Exception as e:
                    print(f"✗ Failed to rename: {e}")
                    new_filename = pdf_file.name
            else:
                print("✗ Skipped renaming (missing recipient name or amount)")
        else:
            recipient_name = None
            amount = None
            print("Warning: No text was extracted from PDF")
        
        results.append({
            'original_filename': pdf_file.name,
            'new_filename': new_filename,
            'recipient_name': recipient_name if recipient_name else 'Not found',
            'amount': amount if amount else 'Not found',
            'full_text': text.replace('\n', ' ')[:300]
        })
    
    print("\n" + "=" * 60)
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['original_filename', 'new_filename', 'recipient_name', 'amount', 'full_text'])
        writer.writeheader()
        writer.writerows(results)
    
    print(f"Processing complete! Results saved to: {output_csv}")
    print(f"Successfully processed {len(results)} receipts")
    print(f"Files renamed: {renamed_count}/{len(results)}")
    
    found = sum(1 for r in results if r['recipient_name'] != 'Not found' and r['amount'] != 'Not found')
    print(f"Complete data found: {found}/{len(results)}")
    print("=" * 60)
    
    return results

if __name__ == "__main__":
    input_folder = "receipts"
    output_csv = "receipt_results.csv"
    
    if os.path.exists(input_folder):
        results = process_pdf_receipts(input_folder, output_csv)
        
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        for result in results:
            print(f"Original: {result['original_filename']}")
            print(f"     New: {result['new_filename']}")
            print(f"Recipient: {result['recipient_name']}")
            print(f"   Amount: {result['amount']}")
            print()
    else:
        print(f"ERROR: Folder '{input_folder}' not found.")
        print("Please create a 'receipts' folder and add your PDF receipts.")
import pytesseract
from PIL import Image
import os
import re
import csv
import json
from pathlib import Path
import sys

# Load bank configuration
def load_config():
    """Load bank configuration from JSON file"""
    try:
        with open('bank_config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Warning: bank_config.json not found. Using default settings.")
        return {
            "name_keywords": ["customer", "name", "from", "sender"],
            "excluded_words": ["details", "transaction", "transfer"],
            "settings": {"min_name_length": 3, "max_name_words": 5}
        }

CONFIG = load_config()

# Configure Tesseract path for Windows
if sys.platform == 'win32':
    possible_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Users\chunt\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            print(f"Found Tesseract at: {path}\n")
            break
    else:
        print("ERROR: Tesseract not found!")
        print("Please install from: https://github.com/UB-Mannheim/tesseract/wiki")
        sys.exit(1)

def extract_text_from_image(image_path):
    """Extract text from receipt image using Tesseract OCR"""
    try:
        img = Image.open(image_path)
        # Use PSM 6 (assume uniform block of text)
        text = pytesseract.image_to_string(img, config='--psm 6')
        return text
    except Exception as e:
        print(f"Error processing {image_path}: {e}")
        return ""

def detect_bank(text):
    """Detect which bank the receipt is from"""
    text_lower = text.lower()
    
    for bank_name, bank_info in CONFIG.get('banks', {}).items():
        # Check for bank keywords and app names
        for keyword in bank_info.get('keywords', []):
            if keyword.lower() in text_lower:
                return bank_name, bank_info
        for app_name in bank_info.get('app_names', []):
            if app_name.lower() in text_lower:
                return bank_name, bank_info
    
    return None, None

def clean_name(name, excluded_words):
    """Clean extracted name by removing excluded words"""
    words = name.split()
    cleaned_words = []
    
    for word in words:
        word_lower = word.lower()
        # Skip if word is in excluded list or is just numbers/symbols
        if word_lower not in excluded_words and not word.replace('-', '').replace('/', '').isdigit():
            if len(word) > 1:  # Skip single characters
                cleaned_words.append(word)
    
    return ' '.join(cleaned_words)

def is_valid_name(name, min_length, max_words):
    """Validate if extracted text is a valid name"""
    if not name or len(name) < min_length:
        return False
    
    words = name.split()
    if len(words) > max_words:
        return False
    
    # Should contain at least some letters
    if not any(c.isalpha() for c in name):
        return False
    
    return True

def extract_customer_name(text):
    """
    Extract customer name from receipt text using bank_config.json patterns.
    """
    settings = CONFIG.get('settings', {})
    min_length = settings.get('min_name_length', 3)
    max_words = settings.get('max_name_words', 5)
    excluded_words = [w.lower() for w in CONFIG.get('excluded_words', [])]
    
    # Detect bank and get specific keywords
    bank_name, bank_info = detect_bank(text)
    
    # Build list of keywords to search for
    keywords = CONFIG.get('name_keywords', [])
    if bank_info:
        # Add bank-specific keywords at the front (higher priority)
        bank_keywords = bank_info.get('keywords', [])
        keywords = bank_keywords + [k for k in keywords if k not in bank_keywords]
        if settings.get('debug_mode', False):
            print(f"Detected bank: {bank_name}")
    
    # Search for name using keywords
    lines = text.split('\n')
    
    for keyword in keywords:
        for i, line in enumerate(lines):
            # Case-insensitive search for keyword
            if keyword.lower() in line.lower():
                # Try to extract name from same line
                pattern = re.escape(keyword) + r'[\s:]*(.+?)(?:\n|$)'
                match = re.search(pattern, line, re.IGNORECASE)
                
                if match:
                    potential_name = match.group(1).strip()
                    potential_name = clean_name(potential_name, excluded_words)
                    
                    if is_valid_name(potential_name, min_length, max_words):
                        return potential_name
                
                # If not found on same line, check next line
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    next_line = clean_name(next_line, excluded_words)
                    
                    if is_valid_name(next_line, min_length, max_words):
                        return next_line
    
    # Fallback: Look for capitalized names in first 15 lines
    for line in lines[:15]:
        words = line.strip().split()
        if 2 <= len(words) <= max_words:
            # Check if words are capitalized (likely a name)
            if all(word[0].isupper() for word in words if word and word[0].isalpha()):
                potential_name = ' '.join(words)
                potential_name = clean_name(potential_name, excluded_words)
                
                if is_valid_name(potential_name, min_length, max_words):
                    return potential_name
    
    return "Name not found"

def sanitize_filename(name):
    """Remove invalid characters from filename"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '')
    return name.strip()

def process_receipts_bulk(input_folder, output_csv):
    """
    Process all receipt images in a folder and extract customer names.
    
    Args:
        input_folder: Path to folder containing receipt images
        output_csv: Path to output CSV file
    """
    image_extensions = ['.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp']
    
    results = []
    renamed_count = 0
    
    input_path = Path(input_folder)
    image_files = [f for f in input_path.iterdir() 
                   if f.suffix.lower() in image_extensions]
    
    print(f"Found {len(image_files)} receipt images to process...")
    print("-" * 60)
    
    for idx, image_file in enumerate(image_files, 1):
        print(f"\nProcessing {idx}/{len(image_files)}: {image_file.name}")
        
        # Extract text from image
        text = extract_text_from_image(str(image_file))
        
        new_filename = image_file.name
        
        if text:
            print(f"Text extracted: {len(text)} characters")
            
            # Extract customer name
            customer_name = extract_customer_name(text)
            print(f"Customer name: {customer_name}")
            
            # Rename file if customer name was found
            if customer_name not in ["Name not found", "Error - No text extracted"]:
                safe_name = sanitize_filename(customer_name)
                new_filename = f"{safe_name}{image_file.suffix}"
                new_path = image_file.parent / new_filename
                
                # Handle duplicate names
                counter = 1
                while new_path.exists() and new_path != image_file:
                    new_filename = f"{safe_name}_{counter}{image_file.suffix}"
                    new_path = image_file.parent / new_filename
                    counter += 1
                
                # Rename the file
                try:
                    image_file.rename(new_path)
                    print(f"✓ Renamed to: {new_filename}")
                    renamed_count += 1
                except Exception as e:
                    print(f"✗ Failed to rename: {e}")
                    new_filename = image_file.name
            else:
                print("✗ Skipped renaming (no customer name found)")
        else:
            customer_name = "Error - No text extracted"
            print("Warning: No text was extracted from image")
        
        results.append({
            'original_filename': image_file.name,
            'new_filename': new_filename,
            'customer_name': customer_name,
            'full_text': text.replace('\n', ' ')[:200]
        })
    
    # Save results to CSV
    print("\n" + "=" * 60)
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['original_filename', 'new_filename', 'customer_name', 'full_text'])
        writer.writeheader()
        writer.writerows(results)
    
    print(f"Processing complete! Results saved to: {output_csv}")
    print(f"Successfully processed {len(results)} receipts")
    print(f"Files renamed: {renamed_count}/{len(results)}")
    
    found = sum(1 for r in results if r['customer_name'] not in ["Name not found", "Error - No text extracted"])
    print(f"Customer names found: {found}/{len(results)}")
    print("=" * 60)
    
    return results

# Main execution
if __name__ == "__main__":
    input_folder = "receipts"
    output_csv = "customer_names.csv"
    
    if os.path.exists(input_folder):
        results = process_receipts_bulk(input_folder, output_csv)
        
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        for result in results:
            print(f"Original: {result['original_filename']}")
            print(f"     New: {result['new_filename']}")
            print(f"Customer: {result['customer_name']}")
            print()
    else:
        print(f"ERROR: Folder '{input_folder}' not found.")
        print("Please create a 'receipts' folder and add your receipt images.")
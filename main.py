import boto3
import os
import re
from dotenv import load_dotenv
from pathlib import Path
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

class MalaysianBankReceiptProcessor:
    def __init__(self, config_file='bank_config.json', region_name='us-east-1'):
        """Initialize processor with configuration"""
        load_dotenv()
        
        # Load AWS Textract client
        self.textract = boto3.client(
            'textract',
            region_name=region_name,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        
        # Load configuration from JSON file
        self.config = self.load_config(config_file)
        self.name_keywords = self.config.get('name_keywords', [])
        self.banks = self.config.get('banks', {})
        self.excluded_words = self.config.get('excluded_words', [])
        self.settings = self.config.get('settings', {})
        
        self.results = []
        
        print(f"✓ Configuration loaded from {config_file}")
        print(f"  - {len(self.name_keywords)} name keywords")
        print(f"  - {len(self.banks)} Malaysian banks configured")
        print(f"  - Debug mode: {'ON' if self.settings.get('debug_mode') else 'OFF'}")
    
    def load_config(self, config_file):
        """Load configuration from JSON file"""
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                print(f"⚠️  Config file '{config_file}' not found. Using defaults.")
                return self.get_default_config()
        except Exception as e:
            print(f"⚠️  Error loading config: {e}. Using defaults.")
            return self.get_default_config()
    
    def get_default_config(self):
        """Return default configuration"""
        return {
            "name_keywords": [
                "receive from", "sender", "from", "customer", "name"
            ],
            "banks": {},
            "excluded_words": ["details", "transaction", "payment"],
            "settings": {
                "min_name_length": 3,
                "max_name_words": 5,
                "parallel_workers": 3,
                "debug_mode": False
            }
        }
    
    def extract_text_from_image(self, image_path):
        """Extract text from image using AWS Textract"""
        try:
            with open(image_path, 'rb') as document:
                image_bytes = document.read()
            
            response = self.textract.detect_document_text(
                Document={'Bytes': image_bytes}
            )
            
            # Extract all text lines
            text_lines = []
            for block in response['Blocks']:
                if block['BlockType'] == 'LINE':
                    text_lines.append(block['Text'])
            
            return text_lines, '\n'.join(text_lines)
        except Exception as e:
            if self.settings.get('debug_mode'):
                print(f"  ✗ Error extracting text: {e}")
            return [], ""
    
    def detect_bank(self, full_text):
        """Detect which Malaysian bank this receipt is from"""
        text_lower = full_text.lower()
        
        for bank_name, bank_config in self.banks.items():
            # Check if any bank-specific keywords are present
            bank_keywords = bank_config.get('keywords', [])
            app_names = bank_config.get('app_names', [])
            
            all_indicators = bank_keywords + app_names
            
            for indicator in all_indicators:
                if indicator.lower() in text_lower:
                    if self.settings.get('debug_mode'):
                        print(f"  🏦 Detected bank: {bank_name}")
                    return bank_name
        
        if self.settings.get('debug_mode'):
            print(f"  🏦 Bank not identified")
        return None
    
    def extract_customer_name(self, text_lines, full_text):
        """Extract customer name from Malaysian bank receipts - FIXED VERSION"""
        
        # Detect bank first (optional, for better accuracy)
        detected_bank = self.detect_bank(full_text)
        
        # Get settings
        min_length = self.settings.get('min_name_length', 3)
        max_words = self.settings.get('max_name_words', 5)
        
        if self.settings.get('debug_mode'):
            print(f"\n  🔍 Starting name extraction...")
            print(f"  📋 Total lines: {len(text_lines)}")
            print(f"  📏 Min length: {min_length}, Max words: {max_words}\n")
        
        # Method 1: Line-by-line search (MOST RELIABLE)
        for i, line in enumerate(text_lines):
            line_lower = line.lower()
            
            # Check if line contains any configured keyword
            matched_keyword = None
            for keyword in self.name_keywords:
                if keyword in line_lower:
                    matched_keyword = keyword
                    break
            
            if matched_keyword:
                if self.settings.get('debug_mode'):
                    print(f"  📍 Line {i}: Found keyword '{matched_keyword}'")
                    print(f"     Current line: '{line}'")
                
                # Next line is the name (SINGLE LINE ONLY!)
                if i + 1 < len(text_lines):
                    potential_name = text_lines[i + 1].strip()
                    
                    if self.settings.get('debug_mode'):
                        print(f"     Next line: '{potential_name}'")
                    
                    # Check if it looks like a name (only letters and spaces)
                    is_alpha = potential_name.replace(' ', '').replace('.', '').isalpha()
                    
                    if self.settings.get('debug_mode'):
                        print(f"     Is alphabetic: {is_alpha}")
                    
                    if potential_name and is_alpha:
                        # Clean the name
                        clean_name = re.sub(r'\s+', ' ', potential_name)
                        clean_name = re.sub(r'[^A-Za-z\s]', '', clean_name).strip()
                        
                        # Validate length and word count
                        words = clean_name.split()
                        
                        if self.settings.get('debug_mode'):
                            print(f"     Cleaned name: '{clean_name}'")
                            print(f"     Length: {len(clean_name)}, Words: {len(words)}")
                        
                        # Check length and word count
                        if len(clean_name) > min_length and len(words) <= max_words:
                            # Check against excluded words
                            has_excluded = any(excluded.lower() in clean_name.lower() 
                                             for excluded in self.excluded_words)
                            
                            if self.settings.get('debug_mode'):
                                print(f"     Has excluded words: {has_excluded}")
                            
                            if not has_excluded:
                                print(f"  ✓ Found customer name: {clean_name}")
                                return clean_name
                            else:
                                if self.settings.get('debug_mode'):
                                    print(f"     ✗ Rejected: contains excluded words\n")
                        else:
                            if self.settings.get('debug_mode'):
                                print(f"     ✗ Rejected: invalid length or word count\n")
                    else:
                        if self.settings.get('debug_mode'):
                            print(f"     ✗ Rejected: not alphabetic\n")
        
        # Method 2: Smart detection - look for names in top portion
        if self.settings.get('debug_mode'):
            print("  🔍 Method 1 failed. Trying smart detection...\n")
        
        top_lines = text_lines[:max(10, len(text_lines) // 3)]
        
        for i, line in enumerate(top_lines):
            # Skip very short lines
            if len(line) < 6:
                continue
            
            # Check if line looks like a person's name (only letters and spaces)
            is_alpha = line.replace(' ', '').isalpha()
            
            if is_alpha:
                words = line.split()
                
                if self.settings.get('debug_mode'):
                    print(f"  📝 Line {i}: '{line}' ({len(words)} words)")
                
                # Check word count (names usually have 2-5 words)
                if 2 <= len(words) <= max_words:
                    # Check against excluded words
                    has_excluded = any(excluded.lower() in line.lower() 
                                     for excluded in self.excluded_words)
                    
                    if self.settings.get('debug_mode'):
                        print(f"     Has excluded words: {has_excluded}")
                    
                    if not has_excluded:
                        print(f"  ✓ Found customer name: {line}")
                        return line
                    else:
                        if self.settings.get('debug_mode'):
                            print(f"     ✗ Rejected: contains excluded words\n")
        
        print("  ✗ No customer name found")
        return None
    
    def rename_file(self, file_path, customer_name):
        """Rename file with customer name"""
        if not customer_name:
            return False
        
        try:
            directory = os.path.dirname(file_path)
            extension = os.path.splitext(file_path)[1]
            
            # Convert to proper filename format
            # "WONG CHUN TIM" -> "Wong_Chun_Tim"
            safe_name = customer_name.title().replace(' ', '_')
            
            # Remove any invalid characters
            safe_name = re.sub(r'[^\w\s-]', '', safe_name)
            
            # Create new filename
            new_filename = f"{safe_name}_receipt{extension}"
            new_path = os.path.join(directory, new_filename)
            
            # Handle duplicate names
            counter = 1
            while os.path.exists(new_path):
                new_filename = f"{safe_name}_receipt_{counter}{extension}"
                new_path = os.path.join(directory, new_filename)
                counter += 1
            
            # Rename the file
            os.rename(file_path, new_path)
            print(f"  ✓ Renamed to: {new_filename}")
            return new_filename
            
        except Exception as e:
            print(f"  ✗ Error renaming file: {e}")
            return False
    
    def process_single_file(self, file_path):
        """Process a single receipt file"""
        filename = os.path.basename(file_path)
        
        if self.settings.get('debug_mode'):
            print(f"\n{'─'*60}")
            print(f"Processing: {filename}")
            print(f"{'─'*60}")
        else:
            print(f"\nProcessing: {filename}")
        
        try:
            # Extract text
            text_lines, full_text = self.extract_text_from_image(file_path)
            
            if not text_lines:
                return {
                    'original_file': filename,
                    'status': 'error',
                    'error': 'No text extracted',
                    'timestamp': datetime.now().isoformat()
                }
            
            print(f"  ✓ Extracted {len(text_lines)} lines")
            
            # Show extracted text in debug mode
            if self.settings.get('debug_mode'):
                print("\n  Extracted text (first 15 lines):")
                for i, line in enumerate(text_lines[:15], 1):
                    print(f"    {i:2d}. {line}")
                if len(text_lines) > 15:
                    print(f"    ... and {len(text_lines) - 15} more lines")
            
            # Extract customer name
            customer_name = self.extract_customer_name(text_lines, full_text)
            
            if customer_name:
                # Rename file
                new_filename = self.rename_file(file_path, customer_name)
                
                if new_filename:
                    return {
                        'original_file': filename,
                        'customer_name': customer_name,
                        'new_filename': new_filename,
                        'status': 'success',
                        'timestamp': datetime.now().isoformat()
                    }
                else:
                    return {
                        'original_file': filename,
                        'customer_name': customer_name,
                        'status': 'rename_failed',
                        'timestamp': datetime.now().isoformat()
                    }
            else:
                return {
                    'original_file': filename,
                    'status': 'no_name_found',
                    'timestamp': datetime.now().isoformat()
                }
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return {
                'original_file': filename,
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def process_folder(self, folder_path, max_workers=None):
        """
        Process all receipt files in a folder
        
        Args:
            folder_path: Path to folder containing receipts
            max_workers: Number of parallel workers (default: from config)
        """
        if max_workers is None:
            max_workers = self.settings.get('parallel_workers', 3)
        
        print(f"\n{'='*60}")
        print(f"MALAYSIAN BANK RECEIPT PROCESSOR")
        print(f"{'='*60}")
        print(f"Folder: {folder_path}")
        print(f"Workers: {max_workers}")
        print(f"{'='*60}\n")
        
        # Find all image files - FIXED: Prevent duplicates
        folder = Path(folder_path)
        supported_formats = ['.jpg', '.jpeg', '.png', '.pdf', '.JPG', '.JPEG', '.PNG', '.PDF']
        
        files = []
        seen_files = set()  # Track unique files by lowercase name
        
        for ext in supported_formats:
            for file_path in folder.glob(f'*{ext}'):
                # Use lowercase filename to avoid case-sensitive duplicates
                file_key = file_path.name.lower()
                
                if file_key not in seen_files:
                    files.append(file_path)
                    seen_files.add(file_key)
                else:
                    if self.settings.get('debug_mode'):
                        print(f"⚠️  Skipping duplicate: {file_path.name}")
        
        if not files:
            print("⚠️  No receipt files found in folder!")
            return []
        
        print(f"Found {len(files)} unique receipt file(s) to process\n")
        
        # Process files
        self.results = []
        
        if max_workers == 1:
            # Sequential processing
            for i, file_path in enumerate(files, 1):
                print(f"\n[{i}/{len(files)}]")
                result = self.process_single_file(str(file_path))
                self.results.append(result)
        else:
            # Parallel processing
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {
                    executor.submit(self.process_single_file, str(f)): (i, f)
                    for i, f in enumerate(files, 1)
                }
                
                for future in as_completed(future_to_file):
                    i, file_path = future_to_file[future]
                    print(f"\n[{i}/{len(files)}]")
                    try:
                        result = future.result()
                        self.results.append(result)
                    except Exception as e:
                        print(f"  ✗ Unexpected error: {e}")
                        self.results.append({
                            'original_file': file_path.name,
                            'status': 'error',
                            'error': str(e),
                            'timestamp': datetime.now().isoformat()
                        })
        
        # Generate and save report
        self.save_report(folder_path)
        
        return self.results
    
    def save_report(self, folder_path):
        """Save processing report"""
        report_filename = f"receipt_processing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = os.path.join(folder_path, report_filename)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        # Print summary
        print(f"\n{'='*60}")
        print("PROCESSING SUMMARY")
        print(f"{'='*60}")
        
        total = len(self.results)
        success = sum(1 for r in self.results if r['status'] == 'success')
        no_name = sum(1 for r in self.results if r['status'] == 'no_name_found')
        errors = sum(1 for r in self.results if r['status'] == 'error')
        rename_failed = sum(1 for r in self.results if r['status'] == 'rename_failed')
        
        print(f"Total files processed: {total}")
        print(f"✓ Successfully renamed: {success} ({success/total*100:.1f}%)" if total > 0 else "✓ Successfully renamed: 0")
        print(f"⚠ No name found: {no_name}")
        print(f"⚠ Rename failed: {rename_failed}")
        print(f"✗ Errors: {errors}")
        
        print(f"\n📊 Detailed report saved to: {report_filename}")
        print(f"{'='*60}\n")
        
        # Show successfully renamed files
        if success > 0:
            print("✓ Successfully renamed files:")
            for r in self.results:
                if r['status'] == 'success':
                    print(f"  {r['original_file']} → {r['new_filename']}")
            print()
        
        # Show failed files details
        if no_name > 0:
            print("❌ Files where no name was found:")
            for r in self.results:
                if r['status'] == 'no_name_found':
                    print(f"  - {r['original_file']}")
            print()
        
        if errors > 0:
            print("❌ Files with errors:")
            for r in self.results:
                if r['status'] == 'error':
                    print(f"  - {r['original_file']}: {r.get('error', 'Unknown error')}")
            print()


# Interactive mode for manual review
class InteractiveMalaysianReceiptProcessor(MalaysianBankReceiptProcessor):
    """Extended processor with interactive mode for failed receipts"""
    
    def process_folder_interactive(self, folder_path):
        """Process folder with interactive fallback for failed receipts"""
        
        # First pass: automatic processing
        results = self.process_folder(folder_path)
        
        # Find failed receipts
        failed = [r for r in results if r['status'] in ['no_name_found', 'error']]
        
        if not failed:
            print("\n✓ All receipts processed successfully!")
            return results
        
        print(f"\n{'='*60}")
        print(f"INTERACTIVE MODE - MANUAL REVIEW")
        print(f"{'='*60}")
        print(f"{len(failed)} receipt(s) need manual review\n")
        
        response = input("Do you want to manually review failed receipts? (yes/no): ").strip().lower()
        
        if response not in ['yes', 'y']:
            print("Skipping manual review.")
            return results
        
        # Process failed receipts interactively
        for i, result in enumerate(failed, 1):
            original_file = result['original_file']
            file_path = os.path.join(folder_path, original_file)
            
            # Check if file still exists
            if not os.path.exists(file_path):
                print(f"\n[{i}/{len(failed)}] File not found: {original_file}")
                continue
            
            print(f"\n{'─'*60}")
            print(f"[{i}/{len(failed)}] {original_file}")
            print(f"{'─'*60}")
            
            # Extract and show text
            text_lines, full_text = self.extract_text_from_image(file_path)
            
            if text_lines:
                print("Extracted text:")
                for j, line in enumerate(text_lines[:20], 1):
                    print(f"  {j:2d}. {line}")
                
                if len(text_lines) > 20:
                    print(f"  ... and {len(text_lines) - 20} more lines")
            else:
                print("⚠️  Could not extract text from this file")
            
            print(f"{'─'*60}")
            
            # Ask user for customer name
            customer_name = input("Enter customer name (or press Enter to skip): ").strip()
            
            if customer_name:
                new_filename = self.rename_file(file_path, customer_name)
                if new_filename:
                    # Update result
                    result['customer_name'] = customer_name
                    result['new_filename'] = new_filename
                    result['status'] = 'success_manual'
                    print(f"✓ Manually renamed to: {new_filename}")
            else:
                print("⊘ Skipped")
        
        # Save updated report
        self.save_report(folder_path)
        
        return self.results


# Main execution
if __name__ == "__main__":
    # ============================================
    # CONFIGURATION - EDIT THESE SETTINGS
    # ============================================
    
    # Set your receipt folder path here
    FOLDER_PATH = r'C:\Users\chunt\automate-receipt\receipts'
    
    # Processing mode
    INTERACTIVE_MODE = False  # Set to True for manual review of failed files
    
    # Number of parallel workers (1-5, lower = safer for AWS rate limits)
    MAX_WORKERS = 3
    
    # ============================================
    # MAIN SCRIPT - DO NOT EDIT BELOW
    # ============================================
    
    print("\n🇲🇾 Malaysian Bank Receipt Auto-Renamer")
    print("=" * 60)
    print(f"Folder: {FOLDER_PATH}")
    print(f"Mode: {'Interactive' if INTERACTIVE_MODE else 'Automatic'}")
    print(f"Workers: {MAX_WORKERS}")
    print("=" * 60)
    
    # Check if config file exists
    if not os.path.exists('bank_config.json'):
        print("\n⚠️  Warning: bank_config.json not found!")
        print("Creating default configuration file...")
        
        # Create default config
        default_config = {
            "name_keywords": [
                "receive from",
                "received from",
                "transfer from",
                "sender",
                "sender name",
                "from",
                "payer",
                "paid by",
                "customer",
                "customer name",
                "name",
                "bill to",
                "client",
                "recipient",
                "beneficiary",
                "transferred from",
                "remitter",
                "remitter name",
                "debited from",
                "originator",
                "originator name"
            ],
            "banks": {
                "Maybank": {
                    "keywords": ["transferred from", "sender's name", "maybank2u", "mae"],
                    "app_names": ["Maybank2u", "MAE by Maybank2u"]
                },
                "CIMB": {
                    "keywords": ["remitter", "remitter name", "cimb clicks", "cimb octo"],
                    "app_names": ["CIMB Clicks", "CIMB Octo"]
                },
                "Public Bank": {
                    "keywords": ["originator", "originator name", "pbe"],
                    "app_names": ["PBe", "PB engage"]
                },
                "Hong Leong Bank": {
                    "keywords": ["debited from", "hlb connect"],
                    "app_names": ["HLB Connect"]
                },
                "RHB": {
                    "keywords": ["from account", "sender", "rhb mobile"],
                    "app_names": ["RHB Mobile Banking"]
                },
                "AmBank": {
                    "keywords": ["from", "sender name", "ambank"],
                    "app_names": ["AmOnline"]
                },
                "Bank Islam": {
                    "keywords": ["from", "sender", "bank islam"],
                    "app_names": ["Bank Islam GO"]
                }
            },
            "excluded_words": [
                "details",
                "transaction",
                "transfer",
                "payment",
                "receipt",
                "duitnow",
                "instant",
                "online",
                "banking",
                "mobile",
                "maybank",
                "cimb",
                "public",
                "hong leong",
                "rhb",
                "ambank",
                "success",
                "successful",
                "completed",
                "pending",
                "failed",
                "processing",
                "date",
                "time",
                "amount",
                "balance",
                "reference",
                "status",
                "wallet",
                "account",
                "number",
                "total"
            ],
            "settings": {
                "min_name_length": 3,
                "max_name_words": 5,
                "parallel_workers": 3,
                "debug_mode": False
            }
        }
        
        with open('bank_config.json', 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2)
        
        print("✓ Created bank_config.json with default settings\n")
    
    # Check if folder exists
    if not os.path.exists(FOLDER_PATH):
        print(f"\n❌ Error: Folder '{FOLDER_PATH}' does not exist!")
        print("\n💡 Tips:")
        print("   1. Make sure the folder path is correct")
        print("   2. Use raw string: r'C:\\path\\to\\folder'")
        print("   3. Or use forward slashes: 'C:/path/to/folder'")
        print(f"\n   Current working directory: {os.getcwd()}")
        input("\nPress Enter to exit...")
        exit(1)
    
    # Check if there are any receipt files
    supported_formats = ['.jpg', '.jpeg', '.png', '.pdf', '.JPG', '.JPEG', '.PNG', '.PDF']

    # Deduplicate files (Windows is case-insensitive)
    files = []
    seen_files = set()

    for ext in supported_formats:
        for file_path in Path(FOLDER_PATH).glob(f'*{ext}'):
            file_key = file_path.name.lower()
            
            if file_key not in seen_files:
                files.append(file_path)
                seen_files.add(file_key)

    if not files:
        print(f"\n⚠️  No receipt files found in '{FOLDER_PATH}'")
        print("\nSupported formats: .jpg, .jpeg, .png, .pdf")
        print(f"\nFiles in folder:")
        try:
            for item in os.listdir(FOLDER_PATH):
                print(f"  - {item}")
        except:
            pass
        input("\nPress Enter to exit...")
        exit(1)

    print(f"\n✓ Found {len(files)} receipt file(s)")

    # Optionally show file list
    if len(files) <= 10:  # Only show if 10 or fewer files
        for i, f in enumerate(files, 1):
            print(f"  {i}. {f.name}")
    
    # Cost calculation
    cost_per_page = 0.0015  # detect_document_text API
    estimated_cost = len(files) * cost_per_page
    
    # Confirm before processing
    print("\nReady to process receipts. This will:")
    print("  1. Extract text from each receipt using AWS Textract")
    print("  2. Identify customer names")
    print("  3. Rename files with customer names")
    print(f"\n💰 Estimated cost: ${estimated_cost:.4f} USD")
    print(f"   (${cost_per_page} per page × {len(files)} files)")
    print(f"   API: detect_document_text (text extraction only)")
    
    response = input("\nContinue? (yes/no): ").strip().lower()
    
    if response not in ['yes', 'y']:
        print("\n⊘ Processing cancelled")
        input("Press Enter to exit...")
        exit(0)
    
    # Process receipts
    try:
        if INTERACTIVE_MODE:
            processor = InteractiveMalaysianReceiptProcessor()
            processor.process_folder_interactive(FOLDER_PATH)
        else:
            processor = MalaysianBankReceiptProcessor()
            processor.process_folder(FOLDER_PATH, max_workers=MAX_WORKERS)
        
        print("\n" + "="*60)
        print("✓ PROCESSING COMPLETE!")
        print("="*60)
        
        # Show summary of renamed files
        success_count = sum(1 for r in processor.results if r['status'] == 'success')
        if success_count > 0:
            print(f"\n✓ Successfully renamed {success_count} file(s)")
        
        input("\nPress Enter to exit...")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Processing interrupted by user")
        input("\nPress Enter to exit...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nFull error details:")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
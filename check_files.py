from pathlib import Path

FOLDER_PATH = r'C:\Users\chunt\automate-receipt\receipts'

supported_formats = ['.jpg', '.jpeg', '.png', '.pdf', '.JPG', '.JPEG', '.PNG', '.PDF']

print(f"\nChecking folder: {FOLDER_PATH}\n")
print("Files found:")
print("="*60)

files = []
seen_files = set()

for ext in supported_formats:
    for file_path in Path(FOLDER_PATH).glob(f'*{ext}'):
        file_key = file_path.name.lower()
        
        if file_key not in seen_files:
            files.append(file_path)
            seen_files.add(file_key)
            print(f"✓ {file_path.name}")
            print(f"   Full path: {file_path}")
            print(f"   Size: {file_path.stat().st_size} bytes")
            print()
        else:
            print(f"⚠ DUPLICATE (skipped): {file_path.name}")
            print()

print("="*60)
print(f"Total unique files: {len(files)}")
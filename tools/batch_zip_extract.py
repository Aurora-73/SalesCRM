import os
import sys
import subprocess
import shutil
import argparse
import logging
import time
from pathlib import Path

SEVEN_ZIP_PATH = r"D:\7-Zip\7z.exe"
SUPPORTED_EXTENSIONS = (".zip", ".rar", ".7z", ".tar", ".tar.gz", ".tar.bz2", ".tgz", ".tbz2")
EXTRACT_TIMEOUT = 3600


def setup_logging(log_file):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )


def is_7zip_available():
    return os.path.exists(SEVEN_ZIP_PATH)


def get_file_extension(file_path):
    path = Path(file_path)
    suffixes = path.suffixes
    if len(suffixes) >= 2:
        double_ext = ''.join(suffixes[-2:]).lower()
        if double_ext in SUPPORTED_EXTENSIONS:
            return double_ext
    if suffixes:
        return suffixes[-1].lower()
    return ""


def get_file_name_without_ext(file_path):
    path = Path(file_path)
    ext = get_file_extension(path)
    if ext:
        return path.name[:-len(ext)]
    return path.stem


def list_archive_contents(archive_path):
    try:
        result = subprocess.run(
            [SEVEN_ZIP_PATH, "l", "-slt", str(archive_path)],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            check=False,
            timeout=120
        )
        if result.returncode != 0:
            return None, False
        
        entries = []
        is_encrypted = False
        in_content = False
        for line in result.stdout.split("\n"):
            if line.startswith("----------"):
                in_content = True
                continue
            if in_content and line.startswith("Path = "):
                entries.append(line[7:])
            if line.startswith("Encrypted = "):
                if line[12] == "+":
                    is_encrypted = True
        return entries, is_encrypted
    except subprocess.TimeoutExpired:
        logging.error(f"Timeout listing contents of {archive_path}")
        return None, False
    except Exception as e:
        logging.error(f"Failed to list contents of {archive_path}: {e}")
        return None, False


def extract_with_7zip(archive_path, dest_dir):
    try:
        os.makedirs(dest_dir, exist_ok=True)
        start_time = time.time()
        
        cmd = [SEVEN_ZIP_PATH, "x", str(archive_path), f"-o{dest_dir}", "-y", "-bso0", "-bse0", "-bsp0"]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL
        )
        
        try:
            stdout, stderr = process.communicate(timeout=EXTRACT_TIMEOUT)
            elapsed = time.time() - start_time
            
            if process.returncode == 0:
                return True, ""
            else:
                error_msg = stderr.decode('mbcs', errors='replace').strip() if stderr else f"exit code {process.returncode}"
                return False, f"7z error: {error_msg}"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return False, f"Timeout after {elapsed:.1f}s"
    except Exception as e:
        return False, str(e)


def extract_zip_python(archive_path, dest_dir):
    import zipfile
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with zipfile.ZipFile(archive_path, 'r') as zf:
            zf.extractall(dest_dir)
        return True, ""
    except Exception as e:
        return False, str(e)


def extract_tar_python(archive_path, dest_dir):
    import tarfile
    try:
        os.makedirs(dest_dir, exist_ok=True)
        ext = get_file_extension(archive_path)
        if ext in ('.gz', '.tgz', '.tar.gz'):
            mode = 'r:gz'
        elif ext in ('.bz2', '.tbz2', '.tar.bz2'):
            mode = 'r:bz2'
        else:
            mode = 'r'
        with tarfile.open(archive_path, mode) as tf:
            tf.extractall(dest_dir)
        return True, ""
    except Exception as e:
        return False, str(e)


def extract_python_fallback(archive_path, dest_dir):
    ext = get_file_extension(archive_path)
    
    if ext == ".zip":
        return extract_zip_python(archive_path, dest_dir)
    elif ext in (".tar", ".gz", ".tgz", ".bz2", ".tbz2", ".tar.gz", ".tar.bz2"):
        return extract_tar_python(archive_path, dest_dir)
    else:
        return False, f"Unsupported format for Python fallback: {ext}"


def extract_archive(archive_path, dest_dir):
    if is_7zip_available():
        return extract_with_7zip(archive_path, dest_dir)
    else:
        logging.warning(f"7-Zip not found, using Python fallback for {archive_path}")
        return extract_python_fallback(archive_path, dest_dir)


def find_compressed_files(search_path):
    compressed_files = []
    search_path = Path(search_path).resolve()
    
    for root, dirs, files in os.walk(search_path):
        for file in files:
            ext = get_file_extension(file)
            if ext in SUPPORTED_EXTENSIONS:
                compressed_files.append(Path(root) / file)
    
    return compressed_files


def get_single_root_folder(entries):
    if not entries:
        return None
    
    first_entry = entries[0]
    if not first_entry:
        return None
    
    normalized_entry = first_entry.replace("\\", "/")
    if "/" not in normalized_entry:
        return None
    
    root_name = normalized_entry.split("/")[0]
    
    all_under_root = True
    for entry in entries:
        normalized = entry.replace("\\", "/")
        if not normalized.startswith(root_name + "/"):
            all_under_root = False
            break
    
    if all_under_root:
        return root_name
    return None


def process_archive(archive_path, dry_run=False):
    archive_name = get_file_name_without_ext(archive_path)
    archive_dir = archive_path.parent
    log_entry = {
        "file": str(archive_path),
        "status": "pending",
        "reason": "",
        "is_password_protected": False
    }
    
    try:
        if not archive_path.exists():
            log_entry["status"] = "skipped"
            log_entry["reason"] = "File does not exist"
            return log_entry
        
        file_size = archive_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        logging.info(f"Processing: {archive_path} ({file_size_mb:.2f} MB)")
        
        entries, is_encrypted = list_archive_contents(archive_path)
        if entries is None:
            log_entry["status"] = "failed"
            log_entry["reason"] = "Failed to read archive contents"
            return log_entry
        
        if not entries:
            log_entry["status"] = "skipped"
            log_entry["reason"] = "Empty archive"
            return log_entry
        
        if is_encrypted:
            log_entry["status"] = "password"
            log_entry["reason"] = "Password protected"
            log_entry["is_password_protected"] = True
            logging.warning(f"  ⚠ Password protected, skipping")
            return log_entry
        
        root_folder = get_single_root_folder(entries)
        
        if root_folder:
            if len(root_folder) >= len(archive_name):
                target_name = root_folder
            else:
                target_name = archive_name
            
            temp_dir = archive_dir / f"_extract_temp_{archive_name}"
            final_dir = archive_dir / target_name
            
            if dry_run:
                logging.info(f"[DRY RUN] Would extract {archive_path} -> {final_dir} (single folder mode)")
                log_entry["status"] = "dry_run"
                log_entry["reason"] = f"Would extract to {final_dir}"
                return log_entry
            
            success, error = extract_archive(archive_path, temp_dir)
            if not success:
                log_entry["status"] = "failed"
                log_entry["reason"] = f"Extraction failed: {error}"
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                return log_entry
            
            temp_root = temp_dir / root_folder
            if temp_root.exists() and temp_root.is_dir():
                if final_dir.exists():
                    shutil.rmtree(final_dir)
                shutil.move(str(temp_root), str(final_dir))
                shutil.rmtree(temp_dir)
            else:
                if final_dir.exists():
                    shutil.rmtree(final_dir)
                shutil.move(str(temp_dir), str(final_dir))
            
            logging.info(f"✓ Successfully extracted: {archive_path} -> {final_dir}")
            log_entry["status"] = "success"
            log_entry["reason"] = f"Extracted to {final_dir}"
        
        else:
            target_dir = archive_dir / archive_name
            
            if dry_run:
                logging.info(f"[DRY RUN] Would extract {archive_path} -> {target_dir} (multi-file mode)")
                log_entry["status"] = "dry_run"
                log_entry["reason"] = f"Would extract to {target_dir}"
                return log_entry
            
            if target_dir.exists():
                shutil.rmtree(target_dir)
            
            success, error = extract_archive(archive_path, target_dir)
            if success:
                logging.info(f"✓ Successfully extracted: {archive_path} -> {target_dir}")
                log_entry["status"] = "success"
                log_entry["reason"] = f"Extracted to {target_dir}"
            else:
                log_entry["status"] = "failed"
                log_entry["reason"] = f"Extraction failed: {error}"
        
        return log_entry
    
    except PermissionError as e:
        log_entry["status"] = "failed"
        log_entry["reason"] = f"Permission denied: {e}"
        logging.error(f"✗ Permission error: {archive_path} - {e}")
        return log_entry
    except Exception as e:
        log_entry["status"] = "failed"
        log_entry["reason"] = f"Unexpected error: {e}"
        logging.error(f"✗ Unexpected error: {archive_path} - {e}")
        return log_entry


def main():
    parser = argparse.ArgumentParser(description="Batch extract compressed files")
    parser.add_argument("path", nargs="?", default=".", help="Target path to scan for compressed files")
    parser.add_argument("--dry-run", action="store_true", help="Preview extraction without actually extracting")
    parser.add_argument("--log-file", default="batch_extract.log", help="Log file path")
    args = parser.parse_args()
    
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    
    target_path = Path(args.path).resolve()
    
    if not target_path.exists():
        print(f"Error: Target path '{target_path}' does not exist")
        sys.exit(1)
    
    setup_logging(args.log_file)
    
    logging.info("=" * 60)
    logging.info("Batch Extract Script Started")
    logging.info(f"Target Path: {target_path}")
    logging.info(f"Dry Run Mode: {args.dry_run}")
    logging.info(f"7-Zip Available: {is_7zip_available()}")
    logging.info(f"Extraction Timeout: {EXTRACT_TIMEOUT}s")
    logging.info("=" * 60)
    
    compressed_files = find_compressed_files(target_path)
    
    if not compressed_files:
        logging.info("No compressed files found in the target path.")
        return
    
    total_size = sum(f.stat().st_size for f in compressed_files) / (1024 * 1024)
    logging.info(f"Found {len(compressed_files)} compressed files ({total_size:.2f} MB total)")
    for f in compressed_files:
        f_size = f.stat().st_size / (1024 * 1024)
        logging.info(f"  - {f} ({f_size:.2f} MB)")
    logging.info("-" * 60)
    
    results = []
    for i, archive in enumerate(compressed_files, 1):
        logging.info(f"\n[{i}/{len(compressed_files)}]")
        result = process_archive(archive, dry_run=args.dry_run)
        results.append(result)
    
    logging.info("=" * 60)
    logging.info("Batch Extract Script Completed")
    logging.info("=" * 60)
    
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    skipped_count = sum(1 for r in results if r["status"] == "skipped")
    password_count = sum(1 for r in results if r["status"] == "password")
    dry_count = sum(1 for r in results if r["status"] == "dry_run")
    
    logging.info(f"Summary:")
    logging.info(f"  Total: {len(results)}")
    logging.info(f"  Success: {success_count}")
    logging.info(f"  Failed: {failed_count}")
    logging.info(f"  Skipped: {skipped_count}")
    logging.info(f"  Password Protected: {password_count}")
    if dry_count > 0:
        logging.info(f"  Dry Run: {dry_count}")
    
    if failed_count > 0:
        logging.info("\nFailed files:")
        for r in results:
            if r["status"] == "failed":
                logging.info(f"  - {r['file']}: {r['reason']}")
    
    if password_count > 0:
        logging.info("\n⚠ Password protected files (need manual extraction):")
        for r in results:
            if r["status"] == "password":
                logging.info(f"  - {r['file']}")
    
    print(f"\nBatch extraction completed. Log saved to {args.log_file}")
    print(f"Summary: {success_count} succeeded, {failed_count} failed, {skipped_count} skipped")
    if password_count > 0:
        print(f"⚠ {password_count} files are password protected, please extract manually")


if __name__ == "__main__":
    main()

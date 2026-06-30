"""Convert PDF files to Markdown text without extracting images.

Usage:
    python pdf2md.py <pdf_path> [output_md_path]
    python pdf2md.py --batch <directory> [--delete]
"""

import glob
import os
import sys

import pymupdf4llm
from pymupdf4llm.helpers.document_layout import OCRMode


def _to_markdown(pdf_path: str, use_ocr=OCRMode.SELECT_REMOVING_OLD) -> str:
    return pymupdf4llm.to_markdown(
        pdf_path,
        write_images=False,
        image_path=None,
        page_chunks=False,
        use_ocr=use_ocr,
    )


def convert_pdf(pdf_path: str, md_path: str | None = None) -> str:
    """Convert a single PDF to Markdown and return the output path."""
    if md_path is None:
        md_path = os.path.splitext(pdf_path)[0] + ".md"

    try:
        md_text = _to_markdown(pdf_path)
    except TypeError as exc:
        if "'NoneType' object is not iterable" not in str(exc):
            raise
        print("OCR returned no lines on one page; retrying without OCR.", file=sys.stderr)
        md_text = _to_markdown(pdf_path, use_ocr=OCRMode.NEVER)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    return md_path


def batch_convert(dir_path: str, delete_source: bool = False):
    """Convert all PDFs in a directory."""
    pdfs = sorted(glob.glob(os.path.join(dir_path, "*.pdf")))
    if not pdfs:
        print(f"No PDF files found in directory: {dir_path}")
        return

    print(f"Found {len(pdfs)} PDF files\n")
    ok, fail = 0, 0

    for i, pdf in enumerate(pdfs, 1):
        name = os.path.basename(pdf)
        md_path = os.path.splitext(pdf)[0] + ".md"
        print(f"[{i}/{len(pdfs)}] {name} ... ", end="", flush=True)
        try:
            convert_pdf(pdf, md_path)
            size_kb = os.path.getsize(md_path) // 1024
            print(f"OK ({size_kb} KB)")
            if delete_source:
                os.remove(pdf)
            ok += 1
        except Exception as e:
            print(f"FAIL: {e}")
            fail += 1

    print(f"\nDone: {ok} succeeded, {fail} failed")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python pdf2md.py <pdf_file>              # Convert one file")
        print("  python pdf2md.py --batch <directory>     # Batch convert")
        print("  python pdf2md.py --batch <directory> --delete  # Delete source PDFs after conversion")
        sys.exit(1)

    if sys.argv[1] == "--batch":
        if len(sys.argv) < 3:
            print("Missing directory path")
            sys.exit(1)
        dir_path = sys.argv[2]
        delete = "--delete" in sys.argv
        batch_convert(dir_path, delete_source=delete)
    else:
        pdf_path = sys.argv[1]
        md_path = sys.argv[2] if len(sys.argv) > 2 else None
        out = convert_pdf(pdf_path, md_path)
        print(f"Generated: {out}")


if __name__ == "__main__":
    main()

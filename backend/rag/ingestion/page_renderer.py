import hashlib
import os
from pathlib import Path
from typing import Dict, List
import fitz  # PyMuPDF
from PIL import Image
from rag.utils.config import RENDER_DPI


class PageRenderer:
    def __init__(self, dpi: int = RENDER_DPI):
        self.dpi = dpi
        # Store cached images in a cache dir under backend/data/cache
        self.cache_dir = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _compute_file_hash(self, file_path: str) -> str:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def render(self, pdf_path: str) -> List[Dict]:
        """Return [{"page": int, "image": PIL.Image, "width": int, "height": int}, ...]"""
        file_hash = self._compute_file_hash(pdf_path)
        doc = fitz.open(pdf_path)
        pages = []

        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            cache_file = self.cache_dir / f"{file_hash}_p{page_num}_dpi{self.dpi}.png"

            if cache_file.exists():
                # Load from cache
                image = Image.open(cache_file)
                image.load()
            else:
                # Render page
                page = doc.load_page(page_idx)
                zoom = self.dpi / 72.0  # 72 is the default PDF DPI
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Save to cache
                image.save(cache_file, "PNG")

            pages.append({
                "page": page_num,
                "image": image,
                "width": image.width,
                "height": image.height
            })
            
        doc.close()
        return pages

from pathlib import Path
from typing import Dict, Any
import pdfplumber
from rag.ingestion.table_recognizer import TableRecognizer


class RegionExtractor:
    def __init__(self, table_recognizer: TableRecognizer, pdf_path: str):
        self.table_recognizer = table_recognizer
        self.pdf_path = pdf_path
        self.pdf = pdfplumber.open(pdf_path)
        # Store figures under backend/static/figures
        self.figures_dir = Path(__file__).resolve().parent.parent.parent / "static" / "figures"
        self.figures_dir.mkdir(parents=True, exist_ok=True)

    def extract(self, region: Dict[str, Any], page_data: Dict[str, Any], region_idx: int) -> Dict[str, Any]:
        """
        region: {"type": str, "bbox": (x1, y1, x2, y2), "score": float, "page": int}
        page_data: {"page": int, "image": PIL.Image, "width": int, "height": int}
        region_idx: index of this region on the page (for figure naming)
        """
        page_num = region["page"]
        r_type = region["type"]
        bbox = region["bbox"]
        
        pdf_page = self.pdf.pages[page_num - 1]
        
        chunk_text = ""
        chunk_type = "body"
        image_path = None
        
        if r_type in ("text", "title", "list"):
            # Map page image coords to pdf coordinates
            img_w, img_h = page_data["image"].size
            pdf_w = float(pdf_page.width)
            pdf_h = float(pdf_page.height)
            
            scale_x = pdf_w / img_w
            scale_y = pdf_h / img_h
            
            pdf_bbox = (
                bbox[0] * scale_x,
                bbox[1] * scale_y,
                bbox[2] * scale_x,
                bbox[3] * scale_y
            )
            
            try:
                cropped = pdf_page.crop(pdf_bbox)
                chunk_text = cropped.extract_text() or ""
            except Exception as e:
                print(f"[RegionExtractor] Text extraction failed: {e}")
                chunk_text = ""
                
            if r_type == "title":
                chunk_type = "title"
            elif r_type == "list":
                chunk_type = "list"
            else:
                chunk_type = "body"
                
        elif r_type == "table":
            chunk_type = "table"
            chunk_text = self.table_recognizer.to_markdown(page_data["image"], bbox, pdf_page)
            
        elif r_type == "figure":
            chunk_type = "figure"
            # Crop image and save
            doc_name = Path(self.pdf_path).stem
            figure_filename = f"{doc_name}_p{page_num}_fig{region_idx}.png"
            figure_filepath = self.figures_dir / figure_filename
            
            try:
                cropped_img = page_data["image"].crop(bbox)
                cropped_img.save(figure_filepath, "PNG")
                image_path = f"static/figures/{figure_filename}"
            except Exception as e:
                print(f"[RegionExtractor] Figure cropping/saving failed: {e}")
                image_path = None
                
            chunk_text = f"Figure on page {page_num}"
            
        return {
            "text": chunk_text,
            "metadata": {
                "page": page_num,
                "chunk_type": chunk_type,
                "image_path": image_path,
                "bbox": [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
                "score": float(region.get("score", 1.0))
            }
        }

    def close(self):
        if self.pdf:
            self.pdf.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

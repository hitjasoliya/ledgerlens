import PIL.Image
from typing import List, Dict, Any
import layoutparser as lp
from rag.utils.config import LAYOUT_MODEL, LAYOUT_CONFIDENCE_THRESHOLD


class LayoutDetector:
    def __init__(
        self,
        model_name: str = LAYOUT_MODEL,
        threshold: float = LAYOUT_CONFIDENCE_THRESHOLD
    ):
        # Enforce CPU on macOS
        self.model = lp.PaddleDetectionLayoutModel(
            config_path=model_name,
            enforce_cpu=True
        )
        self.threshold = threshold
        self.label_map = {
            "Text": "text",
            "Title": "title",
            "List": "list",
            "Table": "table",
            "Figure": "figure"
        }

    def detect(self, page_image: PIL.Image.Image, page_num: int, pdf_path: str = None) -> List[Dict[str, Any]]:
        """Return list of {"type": str, "bbox": (x1,y1,x2,y2), "score": float, "page": int}"""
        layout = self.model.detect(page_image)
        
        regions = []
        for block in layout:
            label = block.type
            mapped_type = self.label_map.get(label, label.lower())
            
            x1, y1, x2, y2 = block.coordinates
            score = getattr(block, "score", 1.0)
            
            if score < self.threshold:
                continue
            
            regions.append({
                "type": mapped_type,
                "bbox": (int(x1), int(y1), int(x2), int(y2)),
                "score": float(score),
                "page": page_num
            })
            
        # Fallback for missing sections using PyMuPDF (fitz)
        if pdf_path:
            import fitz
            doc = fitz.open(pdf_path)
            if 0 <= page_num - 1 < len(doc):
                page = doc.load_page(page_num - 1)
                blocks = page.get_text("blocks")
                
                img_w, img_h = page_image.size
                pdf_w = float(page.rect.width)
                pdf_h = float(page.rect.height)
                
                scale_x = img_w / pdf_w if pdf_w > 0 else 1.0
                scale_y = img_h / pdf_h if pdf_h > 0 else 1.0
                
                for b in blocks:
                    # b is (x0, y0, x1, y1, "lines in block", block_no, block_type)
                    x0, y0, x1, y1, text, block_no, block_type = b
                    # Skip image blocks (block_type == 1)
                    if block_type != 0:
                        continue
                    if not text.strip():
                        continue
                        
                    # Map to image coordinates
                    ix0, iy0, ix1, iy1 = x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y
                    
                    # Check overlap with existing regions
                    is_covered = False
                    for r in regions:
                        if r["type"] in ["figure"]:
                            continue  # Ignore figures, as they often contain valid text/tables we want to extract
                        rx0, ry0, rx1, ry1 = r["bbox"]
                        # Calculate intersection
                        inter_x0 = max(ix0, rx0)
                        inter_y0 = max(iy0, ry0)
                        inter_x1 = min(ix1, rx1)
                        inter_y1 = min(iy1, ry1)
                        
                        if inter_x0 < inter_x1 and inter_y0 < inter_y1:
                            inter_area = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
                            block_area = (ix1 - ix0) * (iy1 - iy0)
                            if block_area > 0 and inter_area / block_area > 0.5:
                                is_covered = True
                                break
                    
                    if not is_covered:
                        regions.append({
                            "type": "text",
                            "bbox": (int(ix0), int(iy0), int(ix1), int(iy1)),
                            "score": 1.0,
                            "page": page_num
                        })
                        
            doc.close()
            
            # Fallback for tables using pdfplumber
            import pdfplumber
            with pdfplumber.open(pdf_path) as plumber_pdf:
                if 0 <= page_num - 1 < len(plumber_pdf.pages):
                    p_page = plumber_pdf.pages[page_num - 1]
                    tables = p_page.find_tables()
                    
                    plumber_table_regions = []
                    for t in tables:
                        tx0, ty0, tx1, ty1 = t.bbox
                        ix0, iy0, ix1, iy1 = tx0 * scale_x, ty0 * scale_y, tx1 * scale_x, ty1 * scale_y
                        plumber_table_regions.append({
                            "type": "table",
                            "bbox": (int(ix0), int(iy0), int(ix1), int(iy1)),
                            "score": 1.0,
                            "page": page_num
                        })
                        
                    if plumber_table_regions:
                        # Remove LayoutParser tables that overlap with pdfplumber tables
                        # because pdfplumber is generally more accurate when vector lines exist.
                        filtered_regions = []
                        for r in regions:
                            if r["type"] == "table":
                                rx0, ry0, rx1, ry1 = r["bbox"]
                                r_area = (rx1 - rx0) * (ry1 - ry0)
                                is_overlapped_by_plumber = False
                                for ptr in plumber_table_regions:
                                    px0, py0, px1, py1 = ptr["bbox"]
                                    inter_x0 = max(px0, rx0)
                                    inter_y0 = max(py0, ry0)
                                    inter_x1 = min(px1, rx1)
                                    inter_y1 = min(py1, ry1)
                                    if inter_x0 < inter_x1 and inter_y0 < inter_y1:
                                        # If there's any intersection, we drop the LayoutParser table
                                        # to favor the pdfplumber tables inside or around it.
                                        is_overlapped_by_plumber = True
                                        break
                                if not is_overlapped_by_plumber:
                                    filtered_regions.append(r)
                            else:
                                filtered_regions.append(r)
                                
                        regions = filtered_regions + plumber_table_regions
                        
        # Sort regions: top-to-bottom, left-to-right
        regions.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
        return regions

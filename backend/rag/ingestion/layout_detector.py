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

    def detect(self, page_image: PIL.Image.Image, page_num: int) -> List[Dict[str, Any]]:
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
            
        # Sort regions: top-to-bottom, left-to-right
        regions.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
        return regions

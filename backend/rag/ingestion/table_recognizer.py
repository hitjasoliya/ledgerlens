import logging
from typing import List, Dict, Any, Optional
import PIL.Image
import torch
from transformers import AutoImageProcessor, TableTransformerForObjectDetection
from rag.utils.config import TABLE_MODEL, TABLE_DEVICE

logger = logging.getLogger(__name__)


class TableRecognizer:
    def __init__(self, model_name: str = TABLE_MODEL, device: str = TABLE_DEVICE):
        self.model_name = model_name
        self.device = device
        self.processor = None
        self.model = None

    def _load_model(self):
        if self.model is None:
            self.processor = AutoImageProcessor.from_pretrained(self.model_name)
            self.model = TableTransformerForObjectDetection.from_pretrained(self.model_name)
            self.model.to(self.device)

    def to_markdown(self, page_image: PIL.Image.Image, region_bbox: tuple, pdf_page: Any = None) -> str:
        """Return the table as a Markdown string (header row + data rows)."""
        # Crop the table image
        cropped_image = page_image.crop(region_bbox)

        try:
            # Load model lazily
            self._load_model()

            # Convert to grayscale then RGB (TATR expects RGB)
            gray_image = cropped_image.convert("L").convert("RGB")

            inputs = self.processor(images=gray_image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)

            # Post-process outputs
            target_sizes = torch.tensor([gray_image.size[::-1]]).to(self.device)
            results = self.processor.post_process_object_detection(
                outputs, threshold=0.3, target_sizes=target_sizes
            )[0]

            rows = []
            cols = []

            for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
                box = [float(val) for val in box]
                label_idx = int(label)
                # 1: column, 2: row
                if label_idx == 2:
                    rows.append((box, float(score)))
                elif label_idx == 1:
                    cols.append((box, float(score)))

            # Sort rows by top-to-bottom
            rows.sort(key=lambda r: r[0][1])
            # Sort columns by left-to-right
            cols.sort(key=lambda c: c[0][0])

            if not rows or not cols:
                # Fall back to pdfplumber if model couldn't find rows/cols
                if pdf_page is not None:
                    return self._extract_via_pdfplumber(pdf_page, region_bbox, page_image.size)
                return ""

            # Build cell grid using row and column intersections
            grid = []
            for row_box, _ in rows:
                row_cells = []
                for col_box, _ in cols:
                    cell_img_bbox = (col_box[0], row_box[1], col_box[2], row_box[3])
                    cell_text = ""
                    if pdf_page is not None:
                        # Absolute coordinates on the page image
                        abs_img_bbox = (
                            region_bbox[0] + cell_img_bbox[0],
                            region_bbox[1] + cell_img_bbox[1],
                            region_bbox[0] + cell_img_bbox[2],
                            region_bbox[1] + cell_img_bbox[3],
                        )
                        cell_text = self._extract_cell_text(pdf_page, abs_img_bbox, page_image.size)
                    row_cells.append(cell_text)
                grid.append(row_cells)

            markdown_table = self._format_table_to_markdown(grid)
            if markdown_table.strip():
                return markdown_table

        except Exception as e:
            logger.warning("TATR failed: %s. Falling back to pdfplumber.", e)

        # Fallback to pdfplumber
        if pdf_page is not None:
            return self._extract_via_pdfplumber(pdf_page, region_bbox, page_image.size)

        return ""

    def _extract_cell_text(self, pdf_page: Any, abs_img_bbox: tuple, page_img_size: tuple) -> str:
        img_w, img_h = page_img_size
        pdf_w, pdf_h = float(pdf_page.width), float(pdf_page.height)
        scale_x = pdf_w / img_w
        scale_y = pdf_h / img_h

        pdf_bbox = (
            abs_img_bbox[0] * scale_x,
            abs_img_bbox[1] * scale_y,
            abs_img_bbox[2] * scale_x,
            abs_img_bbox[3] * scale_y,
        )
        try:
            cropped = pdf_page.crop(pdf_bbox)
            text = cropped.extract_text()
            return text.strip().replace("\n", " ") if text else ""
        except Exception:
            return ""

    def _extract_via_pdfplumber(self, pdf_page: Any, region_bbox: tuple, page_img_size: tuple) -> str:
        img_w, img_h = page_img_size
        pdf_w, pdf_h = float(pdf_page.width), float(pdf_page.height)
        scale_x = pdf_w / img_w
        scale_y = pdf_h / img_h

        pdf_bbox = (
            region_bbox[0] * scale_x,
            region_bbox[1] * scale_y,
            region_bbox[2] * scale_x,
            region_bbox[3] * scale_y,
        )
        try:
            cropped = pdf_page.crop(pdf_bbox)
            tables = cropped.extract_tables()
            if tables:
                return self._format_table_to_markdown(tables[0])
        except Exception as e:
            logger.error("pdfplumber extraction failed: %s", e)
        return ""

    def _format_table_to_markdown(self, grid: List[List[Optional[str]]]) -> str:
        if not grid or not grid[0]:
            return ""

        cleaned_grid = []
        for row in grid:
            cleaned_row = []
            for cell in row:
                if cell is None:
                    cell = ""
                cell = str(cell).replace("\n", " ").replace("|", "\\|").strip()
                cleaned_row.append(cell)
            cleaned_grid.append(cleaned_row)

        markdown = []
        header = cleaned_grid[0]
        markdown.append("| " + " | ".join(header) + " |")

        separator = ["---"] * len(header)
        markdown.append("| " + " | ".join(separator) + " |")

        for row in cleaned_grid[1:]:
            if len(row) < len(header):
                row += [""] * (len(header) - len(row))
            markdown.append("| " + " | ".join(row[: len(header)]) + " |")

        return "\n".join(markdown)

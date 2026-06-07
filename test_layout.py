import sys
import fitz
from rag.ingestion.page_renderer import PageRenderer
from rag.ingestion.layout_detector import LayoutDetector

pdf_path = "backend/sample_pdfs/adani_report.pdf" # Replace with actual if missing
if len(sys.argv) > 1:
    pdf_path = sys.argv[1]

renderer = PageRenderer()
detector = LayoutDetector()

pages = renderer.render(pdf_path)
for p in pages:
    print(f"Page {p['page']} dims: {p['width']} x {p['height']}")
    regions = detector.detect(p["image"], p["page"])
    for r in regions[:3]:
        print(f"  {r['type']}: {r['bbox']} (score: {r['score']})")
    break

# FILE: src/document_processing/_pass_1_structure.py
# Kilo-Architect - Structural Analysis Module V8.5 (Enhanced Content Filtering)

"""
This module is the dedicated home for all Pass 1 structural analysis logic.

Its sole responsibility is to take a raw PDF path and produce a complete,
structured Pass1Layout object, including a rich, multi-level hierarchy of
document headers.

V8.5 Changes:
- Further enhanced `_is_repetitive_non_content_text` to include a new heuristic
  for filtering common "title-like" or "meta-info" text blocks often found
  on the first few pages (e.g., product names, company details). These blocks
  are usually short, high on the page, and contain commercial keywords or are
  in all caps. This aims to prevent them from becoming low-value chunks.
"""

import fitz
import logging
import re
import os
from datetime import datetime
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict
from pydantic import TypeAdapter

from .schemas import (
    Page, Block, Span, HeaderElement, TOCEntry, Pass1Layout
)
from .llm_client import call_gemini
from .prompt_loader import load_prompt

# --- HELPER SCHEMAS & ADAPTERS ---
TocListAdapter = TypeAdapter(List[TOCEntry])

# ==============================================================================
# INTERNAL HELPER FUNCTIONS
# ==============================================================================

def _triage_pdf(doc: fitz.Document) -> dict:
    """Inspects a PDF to determine if it is text-based."""
    num_pages_to_check = min(5, len(doc))
    if num_pages_to_check == 0:
        return {"processing_method": "empty_document", "confidence": 0.0}
    text_lengths = [len(doc.load_page(i).get_text("text").strip()) for i in range(num_pages_to_check)]
    avg_text_length = sum(text_lengths) / num_pages_to_check if num_pages_to_check > 0 else 0
    logging.info(f"Triage: Document identified as text-based. Avg text length: {avg_text_length:.1f}.")
    return {"processing_method": "vector_analysis", "confidence": 1.0}


def _infer_toc_from_text(doc: fitz.Document) -> Dict[str, Any]:
    """Uses an LLM to parse a text-based Table of Contents if bookmarks are missing."""
    toc_page_num, toc_text = -1, ""
    for i in range(min(len(doc), 10)): # Check first 10 pages
        page = doc.load_page(i)
        text_content = page.get_text("text").lower()
        # Heuristic to find a likely ToC page
        if "table of contents" in text_content or ("contents" in text_content and len(text_content) < 2000):
            toc_text = page.get_text("text")
            toc_page_num = i + 1
            logging.info(f"Found potential text-based Table of Contents on page {toc_page_num}.")
            break

    if not toc_text:
        return {"source": "none", "tree": []}

    try:
        logging.info("Dispatching LLM to infer ToC from page text...")
        prompt_template = load_prompt("toc_inference_v1")
        formatted_prompt = prompt_template.format(context_text=toc_text)
        llm_response_str = call_gemini(formatted_prompt, "gemini-1.5-pro-latest")
        validated_data = TocListAdapter.validate_json(llm_response_str)
        toc_tree = [entry.model_dump() for entry in validated_data]
        logging.info(f"LLM successfully inferred {len(toc_tree)} ToC entries.")
        return {"source": "llm_inference", "tree": toc_tree}
    except Exception as e:
        logging.error(f"Failed to infer ToC using LLM: {e}", exc_info=False)
        return {"source": "none", "tree": []}


def _extract_table_of_contents(doc: fitz.Document) -> dict:
    """Extracts ToC from bookmarks, with a fallback to LLM inference."""
    toc = doc.get_toc(simple=False)
    if toc:
        tree = [{"level": entry[0], "text": entry[1], "page": int(entry[2])} for entry in toc]
        logging.info(f"Extracted ToC from bookmarks with {len(tree)} entries.")
        return {"source": "bookmarks", "tree": tree}
    else:
        logging.warning("No embedded ToC bookmarks found. Attempting LLM-based text inference.")
        return _infer_toc_from_text(doc)


def _is_semantic_header(text: str) -> bool:
    """Applies heuristics to filter out noise from header candidates."""
    text = text.strip()
    if not text or len(text) > 300: return False
    if text.startswith(('\u2022', '\uf0b7', '-', '*', 'o ')):
        if len(text) > 1 and text[1].isspace():
            return False
    if text.count('|') >= 3: return False
    if text.isdigit(): return False
    if len(text) <= 3 and not re.search('[a-zA-Z]', text): return False
    if re.fullmatch(r'^[ivxIVX]+$', text.lower()): return False
    return bool(re.search('[a-zA-Z]', text))


def _profile_document_fonts(doc: fitz.Document) -> list:
    """Analyzes font usage across the document to identify rare (potential header) fonts."""
    font_counter = defaultdict(int)
    for page in doc:
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font_counter[(span["font"], span["size"], span["flags"])] += 1
    profiles = [{"font": f, "size": s, "flags": g, "count": c} for (f, s, g), c in font_counter.items()]
    return sorted(profiles, key=lambda x: x["count"], reverse=True)


def _detect_headers(doc: fitz.Document, font_profile: list) -> list:
    """Detects candidate headers using font heuristics and semantic filtering."""
    total_spans = sum(p["count"] for p in font_profile)
    if total_spans == 0: return []
    header_fonts = {(p["font"], p["size"], p["flags"]) for p in font_profile if (p["count"] / total_spans < 0.05) and p['size'] > 10.5}
    candidates = []
    for page_idx, page in enumerate(doc, 1):
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") == 0 and len(block.get("lines", [])) == 1:
                spans = block["lines"][0].get("spans", [])
                if spans and (spans[0]["font"], spans[0]["size"], spans[0]["flags"]) in header_fonts:
                    text = " ".join(s["text"] for s in spans).strip()
                    if _is_semantic_header(text):
                        candidates.append({
                            "text": text,
                            "font_size": spans[0]["size"],
                            "page_number": page_idx,
                            "bbox": block["bbox"]
                        })
    logging.info(f"Heuristic detection found {len(candidates)} semantic header candidates.")
    return candidates


def _isolate_headers_and_footers(doc: fitz.Document, threshold: float) -> Dict[str, List[str]]:
    """Identifies repetitive header and footer text by analyzing content and position."""
    candidates = defaultdict(list)
    if not doc or len(doc) == 0: return {"headers": [], "footers": []}
    page_height = doc[0].rect.height
    num_pages = len(doc)
    min_pages_for_match = int(num_pages * threshold)
    if min_pages_for_match <= 1: return {"headers": [], "footers": []}

    for page in doc:
        for block in page.get_text("dict").get("blocks", []):
            if block.get('type') == 0:
                block_text = " ".join(s['text'] for l in block.get('lines', []) for s in l.get('spans', [])).strip()
                if block_text and len(block_text) < 150: # Only consider reasonably short blocks for headers/footers
                    candidates[block_text].append(block['bbox'][1])

    headers, footers = set(), set()
    for text, positions in candidates.items():
        if len(positions) > min_pages_for_match:
            # Check if this text looks like a typical repetitive page header/footer
            # This is a key line: "Guidelines for preparing a submission to the PBAC, Version 5.0, September 2016   62"
            # It's caught by `_is_repetitive_non_content_text` below, but `_isolate_headers_and_footers` helps find the *repetitive text*.
            is_common_footer_pattern = re.search(r'Guidelines for preparing a submission to the PBAC, Version \d+\.\d+, September \d+', text)
            if len(text) < 50 or is_common_footer_pattern: # Stronger filter for what constitutes a repetitive header/footer
                avg_y = sum(positions) / len(positions)
                if avg_y < page_height * 0.15: headers.add(text)
                elif avg_y > page_height * 0.85: footers.add(text)

    logging.info(f"Identified {len(headers)} repetitive headers and {len(footers)} footers using a {threshold:.0%} page threshold.")
    return {"headers": list(headers), "footers": list(footers)}


def _merge_and_refine_structure(doc: fitz.Document, toc_entries: List[Dict], header_candidates: List[Dict]) -> List[HeaderElement]:
    """
    Implements a True Hierarchical Merge (V7.0) with improved bbox resolution for TOC entries.
    V8.4: Added `doc` parameter to resolve BBoxes for TOC entries.
    """
    all_headers: List[HeaderElement] = []
    
    # Add TOC entries, trying to resolve bounding boxes if they are missing
    for entry in toc_entries:
        if entry.get('text', '').strip():
            header_text = entry['text'].strip()
            page_num = entry['page']
            bbox = (0,0,0,0) # Default dummy bbox

            # Try to find the actual block for TOC entry to get its real bbox
            page_obj = next((p for p in doc if p.number + 1 == page_num), None)
            if page_obj:
                for block in page_obj.get_text("dict").get("blocks", []):
                    if block.get("type") == 0:
                        block_text = " ".join(s["text"] for l in block.get("lines", []) for s in l.get("spans", [])).strip()
                        if block_text == header_text and \
                           len(block_text) > 5 and len(block_text) < 200: # Ensure reasonable text length
                            bbox = tuple(block["bbox"])
                            logging.debug(f"Resolved bbox for TOC header '{header_text}' on page {page_num} to {bbox}")
                            break
            all_headers.append(HeaderElement(text=header_text, level=entry['level'], page_number=page_num, bounding_box=bbox))

    # Add heuristic header candidates
    if header_candidates:
        font_sizes = sorted(list({h.get('font_size', 0) for h in header_candidates if h.get('font_size')}), reverse=True)
        max_toc_level = max((e.get('level', 0) for e in toc_entries), default=0)
        size_to_level = {size: i + 1 + max_toc_level for i, size in enumerate(font_sizes)}
        all_headers.extend(HeaderElement(text=h['text'], level=size_to_level.get(h.get('font_size',0), max_toc_level + len(font_sizes) + 1), page_number=h['page_number'], bounding_box=h['bbox']) for h in header_candidates)
    
    if not all_headers:
        logging.warning("No structural headers found. Returning empty structure map.")
        return []

    # Sort all headers by page and then Y-position
    all_headers.sort(key=lambda h: (h.page_number, h.bounding_box[1] if h.bounding_box != (0,0,0,0) else float('-inf')))

    final_structure_map: List[HeaderElement] = []
    path_stack: List[HeaderElement] = [] # To keep track of current hierarchy

    for header in all_headers:
        # Adjust level based on true hierarchy (using previous header's level)
        # Pop headers from stack that are at the same or higher level as the current header
        while path_stack and header.level <= path_stack[-1].level:
            path_stack.pop()
        
        # Determine the effective level based on the stack.
        # If stack is empty, it's a top-level (level 1). Otherwise, it's one level below the last element in the stack.
        computed_level = (path_stack[-1].level + 1) if path_stack else 1
        
        # Trust explicit TOC levels if element has a resolved bbox and its level is reasonable.
        # This prevents font-based heuristics from overriding good TOC structure.
        final_level = header.level
        if header.bounding_box == (0,0,0,0): # If it's a dummy bbox (e.g. TOC entry without resolved location)
            final_level = computed_level # Fallback to computed level
        elif header.level > computed_level + 2: # Prevent large, implausible level jumps from heuristics
            final_level = computed_level
        
        finalized_header = HeaderElement(
            text=header.text,
            level=final_level,
            page_number=header.page_number,
            bounding_box=header.bounding_box
        )
        
        # Avoid adding duplicate headers (same text, same page, similar position)
        if not final_structure_map or \
           not (final_structure_map[-1].text == finalized_header.text and \
                final_structure_map[-1].page_number == finalized_header.page_number and \
                # Allow for slight bbox variations if the text is identical (within 5 units on Y-axis)
                abs(final_structure_map[-1].bounding_box[1] - finalized_header.bounding_box[1]) < 5):
            final_structure_map.append(finalized_header)
            path_stack.append(finalized_header)
        else:
            logging.debug(f"Skipping near-duplicate header: '{finalized_header.text}' on page {finalized_header.page_number}")

    logging.info(f"Final structure map has {len(final_structure_map)} unique headers after refinement.")
    return final_structure_map


def _is_repetitive_non_content_text(
    text: str,
    page_num: int,
    bbox: Tuple[float, float, float, float],
    page_height: float,
    all_repetitive_texts: Set[str]
) -> bool:
    """
    Heuristic to identify text blocks that are likely repetitive headers/footers,
    page numbers, or other non-narrative elements that should be filtered out.
    V8.5: Added specific filtering for title-like/meta-info blocks on early pages.
    """
    text = text.strip()
    if not text:
        return True

    # 1. Match against known repetitive header/footer text (from _isolate_headers_and_footers)
    if text in all_repetitive_texts:
        logging.debug(f"Filtered (Repetitive text match): '{text[:50]}...'")
        return True

    # 2. Check for common page number patterns
    if len(text) < 15 and (
        re.fullmatch(r'^\s*\d+\s*$', text) or  # Pure number (e.g., "62")
        re.fullmatch(r'^\s*\d+\s+of\s+\d+\s*$', text, re.IGNORECASE) or # X of Y pattern
        re.fullmatch(r'^\s*[ivxIVX]+\s*$', text) # Roman numeral page numbers
    ):
        logging.debug(f"Filtered (Page number pattern): '{text}'")
        return True

    # 3. Filter out single-character or very short non-alphanumeric noise
    if len(text) <= 3 and not any(c.isalnum() for c in text):
        logging.debug(f"Filtered (Short non-alphanumeric): '{text}'")
        return True

    # 4. Filter out common footers/headers that are not caught by `_isolate_headers_and_footers` but look like boilerplate.
    # These often combine boilerplate with page numbers or are single-page specific.
    # Example: "Guidelines for preparing a submission to the PBAC, Version 5.0, September 2016   62"
    # Example: "Flowchart 1.1 Overview of information requests for Section 1 of a submission to the PBAC"
    is_in_top_or_bottom_margin = (page_height - bbox[3] < 100 or bbox[1] < 100) # Check if in footer/header area
    
    if is_in_top_or_bottom_margin and len(text) > 30: # Apply to reasonably long strings in margins
        # Updated regex to include "Flowchart" specifically for captions.
        if re.search(r'Guidelines for preparing a submission to the PBAC, Version \d+\.\d+, September \d+|^Flowchart \d+\.\d+\s+Overview of|^Figure \d+\.\d+', text, re.IGNORECASE):
            logging.debug(f"Filtered (Boilerplate margin text): '{text[:50]}...'")
            return True
    
    # Also filter table/figure captions if they start with common prefixes, regardless of margin
    if re.match(r'^(Table|Figure|Flowchart) \d+\.?\d*(\.?\d*)?\s+.*', text, re.IGNORECASE) and len(text) < 300: # Limit length to avoid catching actual text that happens to start this way
        logging.debug(f"Filtered (Identified as a caption): '{text[:50]}...'")
        return True

    # 5. V8.5 NEW: Filter for common "title-like" elements on first few pages that aren't structural headers.
    # These often contain product names, company names, or legal disclaimers.
    if page_num <= 5: # Only check on initial pages where such meta-info usually appears
        if (bbox[1] < page_height * 0.3): # Appears high on the page (top 30% of page height)
            if len(text) > 10 and len(text) < 150: # Not too short, not too long (to avoid cutting off actual content)
                # Patterns for commercial/legal/product-related meta info
                # - Contains common company/legal terms (PTY LTD, INC, PHARMACEUTICAL, etc.)
                # - Or, is predominantly uppercase (e.g., product names or short headings)
                if re.search(r'(?:PTY LTD|LIMITED|INC|CORP|PHARMACEUTICAL|DRUG|MEDICINE|PRODUCT)\b', text, re.IGNORECASE) or \
                   (len(text) > 15 and sum(1 for c in text if c.isupper()) / len(text) > 0.7) or \
                   re.search(r'^\s*\(?\w+\s+([A-Z\s]+)\)?$', text): # Catches patterns like "(New PBS Listing)" or "SPONSOR NAME"
                    logging.debug(f"Filtered (Page-specific title/meta info, page {page_num}): '{text[:50]}...'")
                    return True

    return False


def _is_valid_data_table(markdown_content: str, table_bbox: Tuple[float, float, float, float]) -> bool:
    """
    Heuristic to determine if a detected table is a 'data table' (containing structured information)
    vs. a 'layout table' (e.g., TOCs, forewords, or text formatted with pipes).
    """
    if not markdown_content:
        return False

    lines = markdown_content.strip().split('\n')
    # Filter out markdown separator lines (`|---|`) and very short lines that might be empty or noise
    data_lines = [line for line in lines if not line.startswith('|---') and len(line.strip()) > 5]

    # Rule 1: Check for common non-data table keywords in the content
    non_data_table_keywords = ["foreword", "contents", "table of contents", "record of updates", "abbreviations and acronyms"]
    if any(keyword in markdown_content.lower() for keyword in non_data_table_keywords):
        logging.debug(f"Table at {table_bbox} contains non-data table keywords. Reclassifying as text.")
        return False

    # Rule 2: Assess the structural integrity - does it have enough actual columns?
    structured_lines_count = 0
    for line in data_lines:
        # A data table typically has at least 3 columns (2 internal pipes) in multiple rows.
        if line.count('|') >= 3:
            structured_lines_count += 1
    
    # If there are very few structured lines relative to total lines, or if it's very short overall
    if len(data_lines) > 0:
        if structured_lines_count / len(data_lines) < 0.2: # Less than 20% of lines are truly structured with multiple columns
            logging.debug(f"Table at {table_bbox} has low structured line count ratio ({structured_lines_count}/{len(data_lines)}). Reclassifying as text.")
            return False
        if len(data_lines) < 3 and structured_lines_count < 2: # Very few lines and not clearly structured
             logging.debug(f"Table at {table_bbox} is too short and unstructured. Reclassifying as text.")
             return False
    
    # Rule 3: Check if the content is predominantly non-tabular narrative despite having some pipes.
    # If the ratio of alphanumeric characters to pipes is very high (meaning mostly text, few separators)
    alphanumeric_chars = sum(1 for char in markdown_content if char.isalnum())
    pipe_chars = markdown_content.count('|')
    
    if pipe_chars > 0 and alphanumeric_chars / pipe_chars > 50: # Arbitrary ratio to detect text-heavy "tables"
        logging.debug(f"Table at {table_bbox} is text-heavy with few pipes. Reclassifying as text.")
        return False

    logging.debug(f"Table at {table_bbox} considered a valid data table.")
    return True


def _extract_content_blocks(
    doc: fitz.Document,
    isolated_texts: Dict[str, List[str]], # From _isolate_headers_and_footers
    all_structure_elements: List[HeaderElement] # From _merge_and_refine_structure
) -> List[Page]:
    """
    Extracts main content blocks, identifying text and tables, and excluding headers/footers.
    V8.3 FIX: Overhauls table and text block delineation to prevent misclassification.
    - Stricter validation for 'data tables'.
    - More robust filtering of repetitive headers/footers and page numbers.
    """
    pages_data = []
    
    # 1. Pre-process known repetitive text content for filtering (from _isolate_headers_and_footers)
    all_repetitive_text_set = set(isolated_texts.get("headers", [])) | set(isolated_texts.get("footers", []))

    # 2. Pre-process all structure map header bounding boxes for filtering text blocks
    # These are elements that should define structure, not be content blocks themselves.
    all_structure_header_bboxes_set = set(h.bounding_box for h in all_structure_elements)


    for page_idx, page in enumerate(doc, 1):
        current_page = Page(page_number=page_idx, dimensions=(page.rect.width, page.rect.height))
        
        # Collect potential tables from PyMuPDF
        raw_tables_from_fitz = []
        try:
            table_finder = page.find_tables(strategy="text")
            raw_tables_from_fitz = table_finder.tables
            logging.debug(f"Page {page_idx}: PyMuPDF found {len(raw_tables_from_fitz)} potential tables.")
        except ValueError as e:
            logging.warning(f"Page {page_idx}: Could not perform table extraction due to an internal PyMuPDF error: {e}. Skipping table detection for this page.")
            raw_tables_from_fitz = []
        
        # Store confirmed data tables and their bboxes to exclude from text processing
        confirmed_data_tables = []
        table_bboxes_to_exclude_from_text_blocks = []

        for table in raw_tables_from_fitz:
            markdown_content = table.to_markdown(clean=False)
            if _is_valid_data_table(markdown_content, table.bbox):
                confirmed_data_tables.append(table)
                table_bboxes_to_exclude_from_text_blocks.append(fitz.Rect(table.bbox))
            else:
                # If it's not a valid data table, its content will be processed as regular text blocks below
                logging.debug(f"Page {page_idx}: Discarding PyMuPDF table at {table.bbox} as it's not a valid data table.")
        
        # Process all raw blocks from the page (text and image)
        blocks_dict = page.get_text("dict")["blocks"]
        block_index = 0

        for block_data in blocks_dict:
            block_bbox = fitz.Rect(block_data['bbox'])
            block_id_prefix = f"p{page_idx}-b{block_index}" # Unique ID for each raw block

            # Skip this block if it overlaps with a confirmed data table's bounding box
            if any(block_bbox.intersects(t_bbox) for t_bbox in table_bboxes_to_exclude_from_text_blocks):
                logging.debug(f"Page {page_idx}: Skipping block {block_bbox} due to overlap with a confirmed data table.")
                continue

            if block_data['type'] == 0: # It's a text block
                block_text = "".join(s['text'] for l in block_data.get('lines', []) for s in l.get('spans', [])).strip()
                
                # Filter out repetitive non-content text (headers, footers, page numbers, boilerplate)
                if _is_repetitive_non_content_text(block_text, page_idx, block_data['bbox'], page.rect.height, all_repetitive_text_set):
                    logging.debug(f"Page {page_idx}: Filtering out repetitive/non-content text: '{block_text[:50]}...'")
                    continue
                
                # Filter out text blocks that are actually identified headers from the structure map.
                # These should be used for structure, not content.
                if block_bbox in all_structure_header_bboxes_set:
                    logging.debug(f"Page {page_idx}: Filtering out text block as it's an identified HeaderElement: '{block_text[:50]}...'")
                    continue

                spans_data = [Span(span_id=f"{block_id_prefix}-s{s_idx}", **s) for l_idx, l in enumerate(block_data.get("lines",[])) for s_idx, s in enumerate(l.get("spans",[]))]
                current_page.blocks.append(Block(block_id=block_id_prefix, block_type="text", bounding_box=tuple(block_data['bbox']), spans=spans_data))
                block_index += 1
            
            # For future expansion: handle image blocks (block_data['type'] == 1)
            # For now, we only process text and tables for RAG.
            
        # Add confirmed data tables to the page's blocks list
        for t_idx, table in enumerate(confirmed_data_tables):
            current_page.blocks.append(Block(
                block_id=f"p{page_idx}-t{t_idx}", # Use 't' prefix for tables for clarity
                block_type="table",
                bounding_box=table.bbox,
                table_markdown=table.to_markdown(clean=False)
            ))
            
        pages_data.append(current_page)
    return pages_data

# ==============================================================================
# PUBLIC ORCHESTRATION FUNCTION
# ==============================================================================

def run_pass_1_layout_analysis(pdf_path: str, config: Dict[str, Any]) -> Pass1Layout:
    """Orchestrates the complete Pass 1 structural analysis of a PDF."""
    logging.info(f"Starting Pass 1 layout analysis for {pdf_path}.")
    doc = None
    try:
        doc = fitz.open(pdf_path)
        doc_id = os.path.splitext(os.path.basename(pdf_path))[0]
        
        processing_method_data = _triage_pdf(doc)
        toc_data = _extract_table_of_contents(doc)
        font_profiles = _profile_document_fonts(doc)
        header_candidates = _detect_headers(doc, font_profiles)
        
        footer_threshold = config.get("deconstruction_configs", {}).get("footer_header_page_threshold", 0.7)
        isolated_elements_dict = _isolate_headers_and_footers(doc, threshold=footer_threshold)
        
        # Synthesize structure_map first, as it's needed for _extract_content_blocks
        logging.info("Synthesizing final structure_map from ToC and heuristic headers...")
        structure_map = _merge_and_refine_structure(
            doc=doc, # Pass doc to _merge_and_refine_structure for bbox resolution
            toc_entries=toc_data.get("tree", []),
            header_candidates=header_candidates
        )

        # Pass the newly created structure_map and isolated_elements_dict to _extract_content_blocks
        pages_data = _extract_content_blocks(doc, isolated_elements_dict, structure_map)
        
        pass1_layout = Pass1Layout(
            doc_id=doc_id,
            processing_metadata={
                "timestamp": datetime.now().isoformat(),
                "pdf_path": pdf_path,
                "toc_source": toc_data.get("source", "none"),
                **processing_method_data
            },
            structure_map=structure_map,
            pages=pages_data,
        )
        return pass1_layout
    finally:
        if doc: doc.close()
# FILE: src/document_processing/utils.py
# Kilo-Architect - Document Processing Utilities V2.5 (Location Tracking)

import logging
from typing import List, Tuple

from .schemas import HeaderElement, Pass1Layout


def get_text_for_section(
    header: HeaderElement,
    layout_data: Pass1Layout
) -> Tuple[str, List[Tuple[int, Tuple[float, float, float, float]]]]:
    """
    Retrieves all text belonging to a specific section header.

    The section's content is defined as all text on the same page as the header
    that appears *after* it, and all text on subsequent pages *until* the next
    header of the same or higher level is encountered.

    V2.5 Change: This function now returns a tuple containing:
    1. The aggregated section text.
    2. A list of unique locations (page_num, bbox) of all text blocks
       that were included in the section. This is crucial for the main
       chunker to identify and process "orphaned" text that doesn't fall
       under any section.
    """
    text_parts = []
    claimed_locations: List[Tuple[int, Tuple[float, float, float, float]]] = []
    
    start_page_idx = header.page_number - 1  # Page numbers are 1-based
    header_level = header.level
    header_y_pos = header.bounding_box[1]

    # Iterate from the header's page to the end of the document
    for page_idx in range(start_page_idx, len(layout_data.pages)):
        page = layout_data.pages[page_idx]
        is_start_page = (page.page_number == header.page_number)
        
        # Check for a stop condition: another header of same/higher level on the current page.
        # But we don't apply this stop condition ON the very first page of the section.
        if page_idx > start_page_idx:
            # Look for a terminating header on subsequent pages
            stop_header_found = any(
                h.level <= header_level and h.page_number == page.page_number
                for h in layout_data.structure_map if h != header
            )
            if stop_header_found:
                logging.debug(f"Stopping text collection for header '{header.text}' at page {page.page_number} due to new significant header.")
                break
        
        # Iterate through blocks on the current page
        for block in page.blocks:
            # We only care about text blocks
            if block.block_type != "text":
                continue

            # On the starting page, only include blocks that appear below the header
            if is_start_page and block.bounding_box[1] <= header_y_pos:
                continue

            # Now, check if this block is actually another header that should terminate collection
            # We identify a block as a header if its text and position match an entry in the structure map
            is_another_header = False
            for h in layout_data.structure_map:
                block_text_unspaced = "".join(span.text for span in block.spans)
                if (h.page_number == page.page_number and
                    h.bounding_box == block.bounding_box and
                    h.text.replace(" ", "") == block_text_unspaced.replace(" ", "") and # Compare content
                    h != header and
                    h.level <= header_level):
                    
                    is_another_header = True
                    break
            
            if is_another_header:
                logging.debug(f"Stopping text collection for '{header.text}' because subsequent header '{h.text}' was found.")
                # We return here because we've hit the next section.
                # The 'claimed_locations' only contains text from the *previous* section.
                return "".join(text_parts).strip(), claimed_locations

            # If all checks pass, append the text and record its location
            block_text = " ".join(span.text for span in block.spans)
            text_parts.append(block_text)
            text_parts.append("\n\n")  # Add separation between blocks
            claimed_locations.append((page.page_number, block.bounding_box))

    return "".join(text_parts).strip(), claimed_locations
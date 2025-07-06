# FILE: src/document_processing/chunker.py
# Kilo-Architect - Intelligent Chunking Engine V3.6 (Robust Raw Table Content)

"""
This module has been fundamentally re-architected to address critical information
loss and chunk redundancy issues.

V3.6 Changes:
- Implemented robust handling for `table.markdown_representation` when creating
  `ChunkMetadata.raw_table_content`. It explicitly converts any `None` or
  whitespace-only string to `None` for the `raw_table_content` field, or ensures
  it's a stripped string otherwise. This addresses the data integrity issue
  where `raw_table_content` was becoming `None` by the time it reached the validation.
"""

import logging
import uuid
import re
from typing import List, Dict, Any, Tuple, Optional, Set

# NLTK imports...
try:
    import nltk
    nltk.data.find('tokenizers/punkt')
except LookupError:
    logging.info("NLTK 'punkt' tokenizer not found. Downloading...")
    nltk.download('punkt', quiet=True)
except ImportError:
    logging.error("NLTK library not found. Please install it with 'pip install nltk'")
    raise

from .schemas import MasterRecord, Pass1Layout, Chunk, ChunkMetadata, HeaderElement


# --- V3.3 REINFORCED HELPER FUNCTIONS (unchanged in logic from V3.3) ---

def _clean_section_path(path: List[str]) -> List[str]:
    """
    Removes consecutive duplicates from a section path.
    """
    if not path:
        return []
    cleaned_path = [path[0]]
    for i in range(1, len(path)):
        if path[i] != cleaned_path[-1]:
            cleaned_path.append(path[i])
    return cleaned_path

def _get_text_for_section(
    header_index: int,
    layout_data: Pass1Layout,
    all_structure_header_locations: Set[Tuple[int, Tuple[float, float, float, float]]]
) -> Tuple[str, Set[Tuple[int, Tuple[float, float, float, float]]]]:
    """
    Retrieves text belonging to a specific section, explicitly skipping blocks
    that are identified as headers in the `structure_map` or are repetitive
    non-content elements filtered by Pass 1.
    """
    text_parts = []
    claimed_locations: Set[Tuple[int, Tuple[float, float, float, float]]] = set()
    
    structure_map = layout_data.structure_map
    current_header = structure_map[header_index]
    start_page_num = current_header.page_number
    
    end_page_num = float('inf')
    next_header_y_pos = float('inf')

    # Find the boundary of the next significant header
    for next_header_idx in range(header_index + 1, len(structure_map)):
        next_header = structure_map[next_header_idx]
        if next_header.level <= current_header.level:
            end_page_num = next_header.page_number
            next_header_y_pos = next_header.bounding_box[1]
            break

    # Iterate through all pages within the logical section boundaries
    for page in layout_data.pages:
        if page.page_number < start_page_num:
            continue
        if page.page_number > end_page_num: # If we passed the end boundary page, stop.
            break
        
        for block in page.blocks:
            if block.block_type != "text":
                continue

            block_location = (page.page_number, block.bounding_box)

            # Skip text blocks that are identified as headers from the structure map.
            if block_location in all_structure_header_locations:
                logging.debug(f"Skipping block at {block_location} as it's a known header from structure map: '{' '.join(span.text for span in block.spans)}'")
                continue

            # On the first page of the section, only take text blocks that appear
            # *after* the current header's bottom Y coordinate.
            if page.page_number == start_page_num and block.bounding_box[1] <= current_header.bounding_box[3]:
                continue
            
            # On the boundary page for the next header, stop before that header's content.
            if page.page_num == end_page_num and block.bounding_box[1] >= next_header_y_pos:
                logging.debug(f"Stopping text collection for section '{current_header.text}' at block {block.block_id} (page {page.page_num}) due to next significant header boundary.")
                return "\n\n".join(text_parts).strip(), claimed_locations

            block_text = " ".join(span.text for span in block.spans).strip()
            if block_text:
                text_parts.append(block_text)
                claimed_locations.add(block_location)

    # Return remaining text if loop finishes without hitting a next header boundary
    return "\n\n".join(text_parts).strip(), claimed_locations


def _identify_leaf_nodes(structure_map: List[HeaderElement]) -> List[int]:
    """
    Identifies headers that are "leafs" in the hierarchy (have no sub-headers).
    Returns a list of their indices in the original structure_map.
    """
    leaf_indices = []
    num_headers = len(structure_map)
    for i in range(num_headers):
        header = structure_map[i]
        is_leaf = True
        # A header is a leaf if there is no next header, or the next header is
        # of the same or higher level.
        if i + 1 < num_headers:
            next_header = structure_map[i+1]
            if next_header.level > header.level:
                is_leaf = False
        
        if is_leaf:
            leaf_indices.append(i)
            
    logging.debug(f"Identified {len(leaf_indices)} leaf node sections for chunking.")
    return leaf_indices


# --- Unchanged Helper Functions ---
def _build_section_hierarchy(structure_map: List[HeaderElement]) -> Dict[int, List[str]]:
    hierarchy = {}
    current_path: List[Tuple[int, str]] = []
    for i, header in enumerate(structure_map):
        header_level = header.level
        header_text = header.text.strip()
        while current_path and current_path[-1][0] >= header_level:
            current_path.pop()
        current_path.append((header_level, header_text))
        breadcrumb = [text for level, text in current_path]
        hierarchy[i] = breadcrumb
    return hierarchy

def _split_text_semantically(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    if not text: return []
    sentences = nltk.sent_tokenize(text)
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 > chunk_size and current_chunk:
            chunks.append(current_chunk)
            overlap_sentences = []
            temp_len = 0
            for s in reversed(nltk.sent_tokenize(current_chunk)):
                if temp_len + len(s) + 1 < chunk_overlap:
                    temp_len += len(s) + 1
                    overlap_sentences.insert(0, s)
                else: break
            current_chunk = " ".join(overlap_sentences)
        current_chunk = f"{current_chunk} {sentence}".strip()
    if current_chunk: chunks.append(current_chunk)
    return chunks

def _get_adaptive_config(section_path: List[str], config: Dict[str, Any]) -> Tuple[int, int]:
    path_str = " ".join(section_path).lower()
    for rule in config.get("adaptive_chunking_rules", []):
        for keyword in rule.get("keywords", []):
            if keyword.lower() in path_str: return rule["chunk_size"], rule["overlap"]
    default_config = config["default_chunking"]
    return default_config["chunk_size"], default_config["overlap"]


# --- V3.6 MAIN FUNCTION ---
def create_chunks_from_record(
    master_record: MasterRecord,
    pass_1_layout: Pass1Layout,
    config: Dict[str, Any]
) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    doc_id = master_record.doc_id
    default_chunk_config = config.get("default_chunking", {"chunk_size": 1500, "overlap": 200})
    claimed_block_locations: Set[Tuple[int, Tuple[float, float, float, float]]] = set()

    # Pre-calculate all header locations from structure_map for efficient filtering.
    all_structure_header_locations = set(
        (h.page_number, h.bounding_box) for h in pass_1_layout.structure_map
    )

    if pass_1_layout.structure_map:
        logging.info("Starting 'Leaf Node' and 'Orphan Capture' chunking process (document has structure).")
        hierarchy_map = _build_section_hierarchy(pass_1_layout.structure_map)
        leaf_node_indices = _identify_leaf_nodes(pass_1_layout.structure_map)

        for header_idx in leaf_node_indices:
            header = pass_1_layout.structure_map[header_idx]
            raw_section_path = hierarchy_map.get(header_idx, [header.text.strip()])
            section_path = _clean_section_path(raw_section_path)
            
            section_text, processed_locations = _get_text_for_section(
                header_idx, pass_1_layout, all_structure_header_locations
            )
            claimed_block_locations.update(processed_locations)
            
            if not section_text.strip():
                logging.debug(f"No narrative text found for leaf section: {section_path} (Header: '{header.text}')")
                continue

            chunk_size, overlap = _get_adaptive_config(section_path, config)
            text_chunks = _split_text_semantically(section_text, chunk_size, overlap)
            
            page_numbers_in_section = sorted(list({loc[0] for loc in processed_locations}))
            if not page_numbers_in_section:
                page_numbers_in_section = [header.page_number]

            for text_chunk in text_chunks:
                metadata = ChunkMetadata(doc_id=doc_id, section_path=section_path, page_numbers=page_numbers_in_section, chunk_type="semantic_text")
                all_chunks.append(Chunk(chunk_id=f"chunk-{uuid.uuid4()}", text=text_chunk, metadata=metadata))
        
        # Orphan Capture for structured documents
        logging.info("Scanning for and processing orphaned text content in structured document...")
        orphan_text_parts = []
        orphan_pages = set()
        for page in pass_1_layout.pages:
            for block in page.blocks:
                if block.block_type == "text":
                    block_location = (page.page_number, block.bounding_box)
                    if block_location not in claimed_block_locations and \
                       block_location not in all_structure_header_locations:
                        block_text = " ".join(span.text for span in block.spans).strip()
                        if block_text:
                            orphan_text_parts.append(block_text)
                            orphan_pages.add(page.page_number)
        
        if orphan_text_parts:
            logging.info(f"Found {len(orphan_text_parts)} orphaned text blocks. Chunking them as 'Miscellaneous Content'.")
            full_orphan_text = "\n\n".join(orphan_text_parts)
            text_chunks = _split_text_semantically(full_orphan_text, default_chunk_config["chunk_size"], default_chunk_config["overlap"])
            for text_chunk in text_chunks:
                metadata = ChunkMetadata(doc_id=doc_id, section_path=["Miscellaneous Content"], page_numbers=sorted(list(orphan_pages)), chunk_type="semantic_text")
                all_chunks.append(Chunk(chunk_id=f"chunk-{uuid.uuid4()}", text=text_chunk, metadata=metadata))

    else:
        # Fallback for documents with no detected structure map (flat documents)
        logging.warning("No structure_map found. Activating fallback to chunk all non-table document text.")
        all_non_table_text_parts = []
        all_non_table_text_pages = set()

        for page in pass_1_layout.pages:
            for block in page.blocks:
                if block.block_type == "text":
                    block_location = (page.page_number, block.bounding_box)
                    if block_location not in all_structure_header_locations:
                        block_text = " ".join(span.text for span in block.spans).strip()
                        if block_text:
                            all_non_table_text_parts.append(block_text)
                            all_non_table_text_pages.add(page.page_number)
        
        logging.info(f"Fallback mode: Aggregated {len(all_non_table_text_parts)} raw text blocks from {len(all_non_table_text_pages)} pages.")
        
        full_text_from_fallback = "\n\n".join(part for part in all_non_table_text_parts if part.strip())
        
        if not full_text_from_fallback.strip():
            logging.info("Fallback mode: No substantial non-table text found after aggregation and filtering. No semantic chunks created.")
        else:
            logging.info(f"Fallback mode: Attempting to semantically chunk {len(full_text_from_fallback)} characters of unstructured text.")
            text_chunks = _split_text_semantically(full_text_from_fallback, default_chunk_config["chunk_size"], default_chunk_config["overlap"])
            
            if not text_chunks:
                logging.warning("Fallback mode: Semantic text chunking resulted in 0 chunks, possibly due to highly unstructured content or NLTK issues.")
            else:
                page_nums_for_fallback_chunks = sorted(list(all_non_table_text_pages))
                if not page_nums_for_fallback_chunks:
                    page_nums_for_fallback_chunks = [p.page_number for p in pass_1_layout.pages]

                for text_chunk in text_chunks:
                    metadata = ChunkMetadata(doc_id=doc_id, section_path=["Unstructured Document"], page_numbers=page_nums_for_fallback_chunks, chunk_type="semantic_text")
                    all_chunks.append(Chunk(chunk_id=f"chunk-{uuid.uuid4()}", text=text_chunk, metadata=metadata))
                logging.info(f"Fallback mode: Created {len(text_chunks)} semantic_text chunks.")

    # Table chunking logic (for confirmed data tables from master_record)
    logging.info(f"Chunking {len(master_record.tables)} table summaries from MasterRecord for doc: {doc_id}")
    table_summaries_created_count = 0
    for table in master_record.tables:
        if not table.llm_summary:
            logging.debug(f"Skipping table {table.table_id}: no LLM summary available.")
            continue
        
        # V3.6 FIX: Robustly handle raw_table_content.
        # Ensure it's None if empty/whitespace only, otherwise strip it.
        processed_raw_table_content = None
        if table.markdown_representation is not None:
            stripped_content = table.markdown_representation.strip()
            if stripped_content:
                processed_raw_table_content = stripped_content
        
        # Debug: Trace processed raw_table_content before ChunkMetadata creation
        processed_len = len(processed_raw_table_content) if processed_raw_table_content is not None else 0
        logging.debug(f"[{doc_id}] Table {table.table_id}: processed_raw_table_content is_None={processed_raw_table_content is None}, length={processed_len}")

        metadata = ChunkMetadata(
            doc_id=doc_id, section_path=["Tables", f"Page {table.page_number}"],
            page_numbers=[table.page_number], chunk_type="table_summary", table_id=table.table_id,
            raw_table_content=processed_raw_table_content # Pass the robustly handled content
        )
        all_chunks.append(Chunk(chunk_id=f"chunk-{uuid.uuid4()}", text=table.llm_summary, metadata=metadata))
        table_summaries_created_count += 1
    logging.info(f"Created {table_summaries_created_count} table_summary chunks.")


    logging.info(f"Total chunks created for doc '{doc_id}': {len(all_chunks)}")
    return all_chunks
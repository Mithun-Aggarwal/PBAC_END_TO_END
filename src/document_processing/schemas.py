# FILE: src/document_processing/schemas.py
# --- V9.1 - V5 Hardened Data Contracts with Enums & Optional markdown_representation ---

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum # V9.0 - Imported for strict vocabulary validation

# ==============================================================================
# Schemas for Pass 1 Layout Analysis & Pass 2 Semantic Analysis
# These are required by 'ingestion_pipeline.py'
# ==============================================================================

class Span(BaseModel):
    span_id: str = Field(..., description="Unique identifier for the span")
    text: str = Field(..., description="Text content of the span")
    font: str = Field(..., description="Font name")
    size: float = Field(..., description="Font size")
    color: int = Field(..., description="Integer representation of font color (e.g., RGB integer)")
    flags: int = Field(..., description="Integer bitmask for font flags (bold, italic, etc.)")

class Block(BaseModel):
    block_id: str = Field(..., description="Unique identifier for the block")
    block_type: str # This was a Literal, keeping as str for flexibility with existing files
    bounding_box: Tuple[float, float, float, float] = Field(..., description="(x0, y0, x1, y1) coordinates")
    spans: List[Span] = Field(default_factory=list, description="List of spans in this block")
    image_path: Optional[str] = Field(None, description="Path to image if block_type is image")
    table_markdown: Optional[str] = Field(None, description="The full table represented as a Markdown string.")

class HeaderElement(BaseModel):
    font_size: Optional[float] = None
    text: str = Field(..., description="Header text")
    level: int = Field(..., description="Header level (e.g., 1 for top-level)")
    page_number: int = Field(..., description="Page number where header appears")
    bounding_box: Tuple[float, float, float, float] = Field(..., description="(x0, y0, x1, y1) coordinates of the header")

class Page(BaseModel):
    page_number: int = Field(..., description="Page number (1-based)")
    dimensions: Tuple[float, float] = Field(..., description="(width, height) of the page")
    blocks: List[Block] = Field(default_factory=list, description="Blocks on the page")

class Pass1Layout(BaseModel):
    doc_id: str = Field(..., description="Document identifier")
    processing_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata about processing")
    structure_map: List[HeaderElement] = Field(default_factory=list, description="Detected headers in the document")
    pages: List[Page] = Field(default_factory=list, description="All pages in the document")
    isolated_elements: List[Dict[str, Any]] = Field(default_factory=list, exclude=True)

class TOCEntry(BaseModel):
    level: int = Field(..., description="The hierarchical level of the entry, starting from 1.")
    text: str = Field(..., description="The text of the section heading.")
    page: int = Field(..., description="The page number associated with the entry.")

class TableSummary(BaseModel):
    summary: str = Field(..., description="A concise, one-sentence summary of the table's content and purpose.")

class LLMResponseValue(BaseModel):
    value: Optional[str] = None
    confidence: Optional[float] = None
    justification: Optional[str] = None

class GlobalMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")
    doc_title: Optional[LLMResponseValue] = Field(default_factory=LLMResponseValue)
    drug_name: Optional[LLMResponseValue] = Field(default_factory=LLMResponseValue)
    indication: Optional[LLMResponseValue] = Field(default_factory=LLMResponseValue)
    sponsor: Optional[LLMResponseValue] = Field(default_factory=LLMResponseValue)

class ProcessedTable(BaseModel):
    table_id: str = Field(..., description="The unique block_id of the table.")
    page_number: int = Field(..., description="The page number where the table is located.")
    bounding_box: Tuple[float, float, float, float] = Field(..., description="(x0, y0, x1, y1) coordinates of the table.")
    llm_summary: Optional[str] = Field(None, description="The LLM-generated summary of the table.")
    # V9.1 FIX: Change to Optional[str] to handle potential None from PyMuPDF or pickling issues
    markdown_representation: Optional[str] = Field(None, description="The full table represented as a Markdown string.")

class MasterRecord(BaseModel):
    doc_id: str = Field(..., description="Document identifier, derived from the filename.")
    global_metadata: GlobalMetadata = Field(..., description="LLM-extracted global metadata like title, sponsor, etc.")
    pass_1_metadata: Dict[str, Any] = Field(..., description="Processing metadata from the Pass 1 layout analysis.")
    tables: List[ProcessedTable] = Field(default_factory=list, description="A list of all processed tables found in the document.")
    sections: List[Any] = Field(default_factory=list, description="Placeholder for specialist section extraction.")


# ==============================================================================
# Schemas for Base RAG Chunking (Output of Phase 0)
# ==============================================================================
class ChunkMetadata(BaseModel):
    doc_id: str = Field(..., description="The ID of the source document.")
    section_path: List[str] = Field(..., description="The hierarchical path of headers leading to this chunk.")
    page_numbers: List[int] = Field(..., description="List of page numbers from which the chunk's content originates.")
    chunk_type: str = Field(..., description="The nature of the chunk's content.")
    table_id: Optional[str] = Field(None, description="Unique ID of the source table if chunk_type is 'table_summary'.")
    raw_table_content: Optional[str] = Field(None, description="The raw markdown content of the table, if chunk_type is 'table_summary'.") # This is already Optional

class Chunk(BaseModel):
    chunk_id: str = Field(..., description="A unique identifier for the chunk (e.g., UUID).")
    text: str = Field(..., description="The text content of the chunk to be embedded.")
    metadata: ChunkMetadata = Field(..., description="The structured metadata associated with this chunk.")


# ==============================================================================
# SCHEMAS for Pass 3 Semantic Enrichment (V5 - FORMALIZED & HARDENED)
# These schemas provide an ironclad data contract for the final artifacts.
# ==============================================================================

# --- V5 Controlled Vocabularies ---
# Using Enums provides a single source of truth and the strictest validation.

class SemanticPurposeEnum(str, Enum):
    BACKGROUND_CONTEXT = "Background/Context"
    DRUG_THERAPY_DESCRIPTION = "Drug/Therapy Description"
    CLINICAL_TRIAL_DESIGN = "Clinical Trial Design"
    EFFICACY_RESULTS = "Efficacy Results"
    SAFETY_ADVERSE_EVENTS = "Safety/Adverse Events"
    PHARMACOECONOMIC_ANALYSIS = "Pharmacoeconomic Analysis"
    DOSAGE_ADMINISTRATION = "Dosage and Administration"
    REGULATORY_HISTORY = "Regulatory History"
    PBAC_RECOMMENDATION = "PBAC Recommendation"
    SPONSORS_JUSTIFICATION = "Sponsor's Justification"
    STAKEHOLDER_COMMENTARY = "Stakeholder Commentary"
    MISCELLANEOUS = "Miscellaneous"

class EntityTypeEnum(str, Enum):
    DRUG = "DRUG"
    THERAPEUTIC_CLASS = "THERAPEUTIC_CLASS"
    TRIAL_ACRONYM = "TRIAL_ACRONYM"
    SPONSOR = "SPONSOR"
    INDICATION = "INDICATION"
    MECHANISM_OF_ACTION = "MECHANISM_OF_ACTION"
    ENDPOINT = "ENDPOINT"
    REGULATORY_BODY = "REGULATORY_BODY"

# --- V5 Auditable Sub-Models ---

class JustifiedStringValue(BaseModel):
    """A container for a string value that includes confidence and justification."""
    value: SemanticPurposeEnum = Field(..., description="The classified value from the controlled vocabulary.")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in the classification (0.0-1.0).")
    justification: str = Field(..., min_length=1, description="Evidence-based reason for the value.")

class JustifiedScore(BaseModel):
    """A container for a float score that includes a justification."""
    score: float = Field(..., ge=0, le=1, description="The assigned score (0.0-1.0).")
    justification: str = Field(..., min_length=1, description="Evidence-based reason for the score.")

class PersonaRelevanceV5(BaseModel):
    """Stores justified relevance scores for different expert personas."""
    clinical_analyst: JustifiedScore
    health_economist: JustifiedScore
    regulatory_specialist: JustifiedScore

class TypedEntityV5(BaseModel):
    """A container for a named entity that includes its specific type."""
    name: str = Field(..., description="The normalized name of the extracted entity.")
    type: EntityTypeEnum = Field(..., description="The entity's type from the controlled vocabulary.")

class QualityAssessmentV5(BaseModel):
    """A container for the LLM's self-assessment of its own analysis quality."""
    confidence: float = Field(..., ge=0, le=1, description="Overall confidence in the analysis of the chunk (0.0-1.0).")
    is_ambiguous: bool = Field(..., description="True if the text is unclear or lacks detail.")
    justification: str = Field(..., min_length=1, description="Explanation for ambiguity or low confidence.")


# --- V5 Final Composite Schemas ---

class EnrichedChunkMetadataV5(ChunkMetadata):
    """The full metadata object for a V5 enriched chunk. Inherits base fields and adds rich, auditable attributes."""
    model_config = ConfigDict(extra="forbid")
    semantic_purpose: JustifiedStringValue
    persona_relevance_scores: PersonaRelevanceV5
    typed_entities: List[TypedEntityV5]
    quality_assessment: QualityAssessmentV5

class EnrichedChunkV5(Chunk):
    """A V5 enriched chunk, ensuring the metadata field conforms to the new auditable schema."""
    metadata: EnrichedChunkMetadataV5
# Project: Intelligent Regulatory Document Analysis Platform

## 1. Project Vision & Mission

The mission of this project is to transform static, unstructured regulatory and clinical documents (such as PBAC Public Summary Documents) from information silos into a dynamic, interconnected, and queryable knowledge base.

We are moving beyond simple text extraction and OCR. Our goal is to achieve deep contextual understanding of each document's structure, semantics, and the relationships between the entities within and across documents. This will serve as the foundation for a powerful AI assistant capable of sophisticated analysis and summarization.

---

## 2. Core Capabilities

The system is engineered to provide the following core capabilities:

1.  **Deep Document Deconstruction:** Perform a "digital autopsy" on raw PDFs to understand not just the text, but the document's intrinsic hierarchy, layout, tables, and visual elements.
2.  **Guided Semantic Inquiry:** Use a managed panel of LLM "specialists" to perform targeted, schema-enforced extractions of key information (e.g., economic data, clinical trial details) from specific sections.
3.  **Context-Aware Knowledge Chunking:** Create information-rich text chunks for semantic search. Each chunk is enriched with metadata about its origin, including its full hierarchical path within the document (e.g., *Document > Section 4 > Economic Analysis*).
4.  **Dual-Database Knowledge Storage:** Persist the extracted knowledge into two specialized databases to enable powerful, multi-modal querying:
    *   A **Vector Database** for semantic similarity search ("what's relevant?").
    *   A **Knowledge Graph** for querying explicit relationships ("how are things connected?").

---

## 3. High-Level Architecture

The platform follows a multi-stage, sequential data processing pipeline. The core of the architecture is a **Two-Pass Deconstruction Engine** that creates a definitive **Master Record** for each document, which then becomes the source of truth for populating the downstream databases.


---

## 4. Deep Dive: The Two-Pass Deconstruction Engine

### Pass 1: The Digital Blueprint Generator (`run_pass_1_layout_analysis`)

The philosophy of Pass 1 is to create a perfect, machine-readable blueprint of the PDF before any complex semantic analysis occurs. This is our `pass_1_layout.json` artifact.

**Key Processes:**
*   **Triage:** Automatically determines if a PDF is text-based (high-fidelity) or image-based (requires OCR), and routes it accordingly.
*   **Structure Mapping:** Extracts the "golden" document hierarchy from embedded PDF bookmarks. If bookmarks are absent, it uses advanced font-profiling heuristics to detect headers and infer the document's structure.
*   **Element Isolation:** Intelligently identifies and isolates recurring headers and footers to clean the main content stream.
*   **Deep Content Extraction:** Captures not just text, but rich, span-level metadata including font type, size, color, and bounding box coordinates for every piece of text.
*   **Component Tagging:** Identifies and tags non-textual elements like tables, images, and vector graphics, preparing them for potential multi-modal analysis in Pass 2.

### Pass 2: The Guided Semantic Inquiry Engine

The philosophy of Pass 2 is to treat Large Language Models (LLMs) as a managed panel of on-demand domain specialists, not as an unpredictable black box. We use the perfect blueprint from Pass 1 to conduct targeted inquiries.

**Key Architectural Features:**
*   **Prompt Registry (`prompts.yml`):** All LLM prompts are versioned and stored externally, allowing for easy updates and A/B testing without changing application code.
*   **Specialist Dispatcher (`dispatch_specialist`):** An intelligent router that reads a section heading (e.g., "4.1 Economic Analysis") and dispatches the correct specialist—a combination of a specific prompt and a Pydantic validation model.
*   **Automated Validation & Repair Loop:** Every LLM call is part of a resilient loop.
    1.  The LLM response is first validated against a strict Pydantic schema.
    2.  If validation fails (e.g., malformed JSON), the system automatically triggers a second "repair" call, feeding the LLM its own faulty output and asking it to fix it.
    3.  This makes the system highly resilient to common LLM errors.
*   **Targeted Context:** Specialists are only fed the text relevant to their specific section (using the `get_text_for_section` function), making the process highly efficient and cost-effective.

### The "Master Record"

The final output of the deconstruction engine is the `master_record.json`. This is the single, auditable source of truth for each document. It contains:
*   The high-level global metadata (title, drug name, etc.).
*   A complete list of all document sections.
*   For each section, the validated, structured data extracted by the relevant specialist, along with processing metadata (status, prompt version, etc.).

This Master Record is the ideal input for the final chunking, embedding, and database loading stages of the overall pipeline.


## 5. Pipeline Execution & Advanced Usage

This section details how to run the full data processing pipeline and explains the key strategies and flags that control its behavior.

### How to Run the Pipeline

The pipeline is controlled via the main orchestrator script. From your activated virtual environment (`source venv/bin/activate`), use the following command structure:

```bash

python3 ingestion_pipeline.py \
    --input-dir ./input_data \
    --output-dir ./output_data \
    --force-reprocess \
    --num-workers 8 \
    --log-file phase_0_ingestion.log

python3 run_enrichment.py \
    --output-dir ./output_data \
    --force-reprocess \
    --num-workers 10 \
    --log-file phase_3_enrichment.log

rm -rf ./output_data ./logs ./phase*.log

python3 -m src.database_loaders.pinecone_loader \
    --input-dir data/ \
    --pinecone-index-name "pbac-documents" \
    --log-file pinecone_loader.log \
    --state-file upload_status.json


python3 scripts/migrate_enrichment_format.py \
    --artifacts-dir ./output_data/pbac_guidelines_version_5_artifacts/ \
    --enriched-chunks-filename enriched_chunks_v5.json \
    --output-filename pbac_guidelines_version_5_reconciled.json

rm upload_status.json
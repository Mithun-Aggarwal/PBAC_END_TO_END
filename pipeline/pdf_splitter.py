import os
import fitz  # PyMuPDF
import logging
from urllib.parse import unquote

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def split_pdf_pages(source_filepath: str, output_directory: str):
    """
    Splits a single PDF file into individual pages and saves each page as a new
    PDF file in the specified output directory.

    The naming convention for the output files is:
    [original_filename]_page_[page_number].pdf

    Args:
        source_filepath (str): The path to the source PDF file.
        output_directory (str): The path to the directory where split pages will be saved.
    """
    logging.info(f"Starting PDF splitting process for source: '{source_filepath}'")
    
    # Decode the filename to handle URL-encoded characters
    decoded_filepath = unquote(source_filepath)
    filename = os.path.basename(decoded_filepath)
    original_filename_without_ext = os.path.splitext(filename)[0]
    
    logging.info(f"Processing decoded filename: '{filename}'")

    # Create the output directory if it doesn't exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
        logging.info(f"Created output directory: '{output_directory}'")

    try:
        # Open the source PDF
        with fitz.open(decoded_filepath) as doc:
            if doc.page_count == 0:
                logging.warning(f"Skipping '{filename}' as it has no pages.")
                return
            
            logging.info(f"Processing '{filename}' with {doc.page_count} pages.")

            # Iterate through each page and save it as a new PDF
            for page_num in range(doc.page_count):
                # Page numbers are 0-indexed in PyMuPDF, but we use 1-based for filenames
                output_filename = f"{original_filename_without_ext}_page_{page_num + 1}.pdf"
                output_filepath = os.path.join(output_directory, output_filename)

                # Create a new single-page PDF
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                
                # Save the new PDF
                new_doc.save(output_filepath)
                new_doc.close()
            
            logging.info(f"Successfully split '{filename}' into {doc.page_count} pages.")
            logging.info(f"Inside 'with' block: Document '{filename}' is_closed: {doc.is_closed}")
        
        # The 'doc' object is closed outside the 'with' block, so we can't access doc.is_closed
        # logging.info(f"Outside 'with' block: Document '{filename}' is_closed: {doc.is_closed}")

    except fitz.fitz.FitzError as e:
        logging.error(f"Fitz error processing '{filename}': {e}")
    except RuntimeError as e:
        logging.error(f"Could not process '{filename}'. It may be corrupted or not a valid PDF. Error: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while processing '{filename}': {e}")

if __name__ == '__main__':
    # This allows the script to be run directly for testing or manual use.
    # Example usage: python pipeline/pdf_splitter.py path/to/source_docs path/to/output_split_pages
    import argparse

    parser = argparse.ArgumentParser(description="Split all PDF documents in a directory into single-page PDF files.")
    parser.add_argument("source_dir", help="The directory containing the source PDF files.")
    parser.add_argument("output_dir", help="The directory where the split-page PDFs will be saved.")
    
    args = parser.parse_args()

    # Basic validation
    if not os.path.isdir(args.source_dir):
        print(f"Error: Source directory not found at '{args.source_dir}'")
    else:
        split_pdf_pages(args.source_dir, args.output_dir)
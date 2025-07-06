import re
import os
from datetime import datetime
from dateutil.parser import parse as date_parser

class DateExtractor:
    """
    Extracts the most likely effective date from a document using a hierarchical approach.
    """
    # Confidence scores for each extraction source
    CONFIDENCE_SCORES = {
        "content": 1.0,
        "filename": 0.8,
        "path": 0.7,
        "filesystem_modified": 0.5,
        "none": 0.0
    }

    def __init__(self, file_path, document_text):
        self.file_path = file_path
        self.document_text = document_text
        self.filename = os.path.basename(file_path) if file_path else ''
        self.directory_path = os.path.dirname(file_path) if file_path else ''

    def extract_date(self):
        """
        Orchestrates the date extraction process according to the defined hierarchy.
        """
        # 1. Content-Level Extraction
        date, source = self._extract_from_content()
        if date:
            return self._format_output(date, source)

        # 2. File/Path-Level Parsing
        date, source = self._extract_from_path()
        if date:
            return self._format_output(date, source)
            
        date, source = self._extract_from_filename()
        if date:
            return self._format_output(date, source)

        # 3. Filesystem Metadata Fallback
        date, source = self._extract_from_filesystem()
        if date:
            return self._format_output(date, source)

        # Handle case where no date is found
        return self._format_output(None, "none")

    def _extract_from_content(self):
        # Regex to find dates preceded by specific keywords
        pattern = r'(?i)(?:Published on|Effective Date|Date|Revision):\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|[A-Za-z]+\s\d{1,2},\s\d{4})'
        match = re.search(pattern, self.document_text)
        if match:
            try:
                date_str = match.group(1)
                return date_parser(date_str, dayfirst=False), "content"
            except (ValueError, TypeError):
                return None, None
        return None, None

    def _extract_from_path(self):
        # Regex to find YYYY-MM-DD format in the directory path
        pattern = r'(\d{4}-\d{2}-\d{2})'
        match = re.search(pattern, self.directory_path)
        if match:
            try:
                return date_parser(match.group(1)), "path"
            except (ValueError, TypeError):
                return None, None
        return None, None

    def _extract_from_filename(self):
        # Regex to find YYYY-MM-DD format in the filename
        pattern = r'(\d{4}-\d{2}-\d{2})'
        match = re.search(pattern, self.filename)
        if match:
            try:
                return date_parser(match.group(1)), "filename"
            except (ValueError, TypeError):
                return None, None
        return None, None

    def _extract_from_filesystem(self):
        # Use the last modified timestamp of the file
        if self.file_path and os.path.exists(self.file_path):
            try:
                mod_time = os.path.getmtime(self.file_path)
                return datetime.fromtimestamp(mod_time), "filesystem_modified"
            except OSError:
                return None, None
        return None, None

    def _format_output(self, date_obj, source):
        return {
            "document_effective_date": date_obj.strftime("%Y-%m-%d") if date_obj else None,
            "date_source": source,
            "date_confidence": self.CONFIDENCE_SCORES.get(source, 0.0)
        }
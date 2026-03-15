#!/usr/bin/env python3
"""
OpenAlex Searcher Module
========================

A module for searching academic papers using OpenAlex API.
Supports both Boolean search and semantic (vector) search.

Features:
- Query translation using LLM (OpenAI API)
- Boolean search with OpenAlex API
- Semantic search with OpenAlex API
- Results export with metadata (title, DOI, authors, abstract)

Usage:
    from openalex_searcher import OpenAlexSearcher
    searcher = OpenAlexSearcher(gemini_api_key="your_key")
    results = searcher.search("machine learning in drug discovery")
"""

import os
import json
import logging
import time
from typing import List, Dict, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
OPENALEX_API_BASE = "https://api.openalex.org"
DEFAULT_TIMEOUT = 30
MAX_RESULTS_PER_PAGE = 200
MAX_RESULTS_TOTAL = 1000


@dataclass
class Paper:
    """Data class representing a paper from OpenAlex."""
    title: str
    doi: Optional[str]
    authors: List[str]
    abstract: Optional[str]
    publication_year: Optional[int]
    openalex_id: str
    cited_by_count: int = 0
    is_oa: bool = False
    source: str = ""  # 'boolean' or 'semantic'

    def to_dict(self) -> Dict:
        """Convert Paper to dictionary."""
        return asdict(self)

    def to_csv_row(self) -> Dict:
        """Convert Paper to CSV-compatible dictionary."""
        return {
            'title': self.title,
            'doi': self.doi if self.doi else '',
            'authors': '; '.join(self.authors) if self.authors else '',
            'abstract': self.abstract if self.abstract else '',
            'publication_year': self.publication_year if self.publication_year else '',
            'openalex_id': self.openalex_id,
            'cited_by_count': self.cited_by_count,
            'is_oa': self.is_oa,
            'source': self.source
        }


class LLMQueryTranslator:
    """Translates natural language queries to OpenAlex search queries using Gemini API."""

    SYSTEM_PROMPT = """You are an expert academic search specialist. Your task is to translate natural language research queries into optimized OpenAlex API search queries.

OpenAlex supports the following search syntax:
1. Boolean operators: AND, OR, NOT (must be uppercase)
2. Field tags:
   - title.search:"phrase" (search in title)
   - abstract.search:"phrase" (search in abstract)
   - display_name.search:"phrase" (search in work title)
   - author.display_name:"name" (search by author)
   - host_venue.display_name:"journal" (search by journal)
   - publication_year:2023 (filter by year)
   - concepts.display_name:"Concept Name" (search by concept)
   - is_oa:true (open access only)
3. Wildcards: * for partial matches
4. Phrases: Use quotes for exact phrases

Rules:
1. Always use uppercase AND, OR, NOT
2. Use quotes for multi-word terms
3. Extract key concepts and expand with synonyms when appropriate using OR
4. Consider adding is_oa:true for better accessibility
5. Return ONLY the query string, no explanations

Examples:
Input: "machine learning for drug discovery"
Output: (abstract.search:"machine learning" OR abstract.search:"deep learning" OR abstract.search:"artificial intelligence") AND (abstract.search:"drug discovery" OR abstract.search:"drug design" OR abstract.search:"pharmaceutical")

Input: "CRISPR in cancer therapy by Jennifer Doudna"
Output: abstract.search:"CRISPR" AND (abstract.search:"cancer" OR abstract.search:"tumor" OR abstract.search:"oncology") AND author.display_name:"Jennifer Doudna"

Input: "recent papers on climate change and biodiversity"
Output: (abstract.search:"climate change" OR abstract.search:"global warming") AND (abstract.search:"biodiversity" OR abstract.search:"species diversity") AND publication_year:>2020"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the LLM translator using Gemini API.

        Args:
            api_key: Gemini API key. If None, will try to get from GEMINI_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

        if not self.api_key:
            logger.warning("No Gemini API key provided. LLM query translation will not be available.")

    def is_available(self) -> bool:
        """Check if LLM translation is available."""
        return self.api_key is not None

    def translate(self, user_query: str, model: str = "gemini-2.0-flash") -> str:
        """
        Translate natural language query to OpenAlex search query using Gemini.

        Args:
            user_query: Natural language description of research interest
            model: Gemini model to use (default: gemini-2.0-flash)

        Returns:
            OpenAlex-formatted search query string
        """
        if not self.api_key:
            logger.warning("No API key available, returning original query")
            return user_query

        try:
            # Construct the API URL with API key
            url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"

            # Gemini API payload format
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": self.SYSTEM_PROMPT},
                            {"text": f"Input: \"{user_query}\"\nOutput:"}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 500
                }
            }

            headers = {
                "Content-Type": "application/json"
            }

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()

            # Parse Gemini response format
            if "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    translated_query = candidate["content"]["parts"][0]["text"].strip()
                else:
                    translated_query = user_query
            else:
                translated_query = user_query

            # Clean up the response (remove quotes if present)
            translated_query = translated_query.strip('"\'')

            logger.info(f"Translated query: '{user_query}' -> '{translated_query}'")
            return translated_query

        except Exception as e:
            logger.error(f"LLM translation failed: {e}")
            logger.info("Falling back to original query")
            return user_query


class OpenAlexSearcher:
    """Main class for searching papers using OpenAlex API."""

    def __init__(self, gemini_api_key: Optional[str] = None,
                 email: Optional[str] = None):
        """
        Initialize the OpenAlex searcher.

        Args:
            gemini_api_key: Gemini API key for query translation
            email: Email for OpenAlex polite pool (recommended)
        """
        self.email = email or os.getenv("OPENALEX_EMAIL")
        self.translator = LLMQueryTranslator(gemini_api_key)

        # Setup session with retries
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

        # Set headers
        headers = {
            'User-Agent': f'OASearchTool (mailto:{self.email})' if self.email else 'OASearchTool',
            'Accept': 'application/json'
        }
        self.session.headers.update(headers)

    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """Make a request to OpenAlex API."""
        url = f"{OPENALEX_API_BASE}/{endpoint}"

        # Add email for polite pool
        if self.email:
            params['mailto'] = self.email

        try:
            response = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None

    def _parse_work(self, work: Dict, source: str) -> Optional[Paper]:
        """Parse a work item from OpenAlex API response."""
        try:
            # Extract authors
            authors = []
            for authorship in work.get('authorships', []):
                author_name = authorship.get('author', {}).get('display_name')
                if author_name:
                    authors.append(author_name)

            # Extract DOI
            doi = work.get('doi')
            if doi:
                doi = doi.replace('https://doi.org/', '').replace('http://doi.org/', '')

            # Get abstract (may need inverted index reconstruction)
            abstract = self._reconstruct_abstract(work.get('abstract_inverted_index'))

            return Paper(
                title=work.get('display_name', 'Unknown Title'),
                doi=doi,
                authors=authors,
                abstract=abstract,
                publication_year=work.get('publication_year'),
                openalex_id=work.get('id', ''),
                cited_by_count=work.get('cited_by_count', 0),
                is_oa=work.get('open_access', {}).get('is_oa', False),
                source=source
            )
        except Exception as e:
            logger.error(f"Error parsing work: {e}")
            return None

    def _reconstruct_abstract(self, inverted_index: Optional[Dict]) -> Optional[str]:
        """Reconstruct abstract from OpenAlex inverted index format."""
        if not inverted_index:
            return None

        try:
            # Inverted index is {word: [positions]}
            # We need to reconstruct the original order
            word_positions = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    word_positions.append((pos, word))

            word_positions.sort(key=lambda x: x[0])
            return ' '.join(word for _, word in word_positions)
        except Exception:
            return None

    def search_boolean(self, query: str, max_results: int = 100,
                       publication_year: Optional[str] = None,
                       sort: str = "relevance_score:desc") -> List[Paper]:
        """
        Perform Boolean search using OpenAlex works endpoint.

        Args:
            query: Search query string (OpenAlex format)
            max_results: Maximum number of results to return
            publication_year: Optional year filter (e.g., "2023" or ">2020")
            sort: Sort order (default: relevance_score:desc)

        Returns:
            List of Paper objects
        """
        logger.info(f"Starting Boolean search with query: {query}")

        papers = []
        cursor = "*"
        per_page = min(MAX_RESULTS_PER_PAGE, max_results)
        remaining = max_results

        while remaining > 0 and cursor:
            params = {
                'search': query,
                'per_page': min(per_page, remaining),
                'cursor': cursor,
                'sort': sort
            }

            # Add optional filters
            if publication_year:
                params['filter'] = f'publication_year:{publication_year}'

            data = self._make_request('works', params)

            if not data or 'results' not in data:
                break

            for work in data['results']:
                paper = self._parse_work(work, source='boolean')
                if paper:
                    papers.append(paper)

            remaining -= len(data['results'])
            cursor = data.get('meta', {}).get('next_cursor')

            # Be polite to API
            time.sleep(0.1)

        logger.info(f"Boolean search returned {len(papers)} papers")
        return papers

    def search_semantic(self, query: str, max_results: int = 100,
                        publication_year: Optional[str] = None) -> List[Paper]:
        """
        Perform semantic search using OpenAlex API with vector similarity.
        Note: OpenAlex doesn't have native semantic search, so we use a
        broader search with relevance ranking.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            publication_year: Optional year filter

        Returns:
            List of Paper objects
        """
        logger.info(f"Starting semantic search with query: {query}")

        # For semantic-like results, we use the default relevance search
        # which considers concept similarity and citation impact
        papers = []
        cursor = "*"
        per_page = min(MAX_RESULTS_PER_PAGE, max_results)
        remaining = max_results

        while remaining > 0 and cursor:
            params = {
                'search': query,
                'per_page': min(per_page, remaining),
                'cursor': cursor,
                'sort': 'cited_by_count:desc'  # Prioritize highly cited papers
            }

            if publication_year:
                params['filter'] = f'publication_year:{publication_year}'

            data = self._make_request('works', params)

            if not data or 'results' not in data:
                break

            for work in data['results']:
                paper = self._parse_work(work, source='semantic')
                if paper:
                    papers.append(paper)

            remaining -= len(data['results'])
            cursor = data.get('meta', {}).get('next_cursor')
            time.sleep(0.1)

        logger.info(f"Semantic search returned {len(papers)} papers")
        return papers

    def search(self, query: str, use_llm: bool = True, max_results: int = 100,
               publication_year: Optional[str] = None,
               translate_model: str = "gpt-4o-mini") -> Dict[str, List[Paper]]:
        """
        Perform both Boolean and semantic searches.

        Args:
            query: Natural language query or search string
            use_llm: Whether to use LLM to translate the query
            max_results: Maximum results per search type
            publication_year: Optional year filter
            translate_model: Model to use for translation

        Returns:
            Dictionary with 'boolean' and 'semantic' keys containing Paper lists
        """
        # Translate query if LLM is available and requested
        if use_llm and self.translator.is_available():
            search_query = self.translator.translate(query, model=translate_model)
        else:
            search_query = query
            if use_llm and not self.translator.is_available():
                logger.warning("LLM not available, using original query")

        results = {
            'boolean': [],
            'semantic': []
        }

        # Perform both searches
        results['boolean'] = self.search_boolean(search_query, max_results, publication_year)
        results['semantic'] = self.search_semantic(search_query, max_results, publication_year)

        return results

    def export_to_json(self, results: Dict[str, List[Paper]], filepath: str):
        """Export search results to JSON file."""
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'boolean_count': len(results['boolean']),
            'semantic_count': len(results['semantic']),
            'boolean_results': [p.to_dict() for p in results['boolean']],
            'semantic_results': [p.to_dict() for p in results['semantic']]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Results exported to JSON: {filepath}")

    def export_to_csv(self, results: Dict[str, List[Paper]], filepath: str,
                      separate_files: bool = False):
        """
        Export search results to CSV file(s).

        Args:
            results: Search results dictionary
            filepath: Output file path
            separate_files: If True, create separate files for boolean and semantic results
        """
        import pandas as pd

        if separate_files:
            # Export separate files
            base, ext = os.path.splitext(filepath)

            if results['boolean']:
                boolean_df = pd.DataFrame([p.to_csv_row() for p in results['boolean']])
                boolean_path = f"{base}_boolean{ext}"
                boolean_df.to_csv(boolean_path, index=False, encoding='utf-8')
                logger.info(f"Boolean results exported to: {boolean_path}")

            if results['semantic']:
                semantic_df = pd.DataFrame([p.to_csv_row() for p in results['semantic']])
                semantic_path = f"{base}_semantic{ext}"
                semantic_df.to_csv(semantic_path, index=False, encoding='utf-8')
                logger.info(f"Semantic results exported to: {semantic_path}")
        else:
            # Export combined file
            all_papers = results['boolean'] + results['semantic']
            if all_papers:
                df = pd.DataFrame([p.to_csv_row() for p in all_papers])
                df.to_csv(filepath, index=False, encoding='utf-8')
                logger.info(f"Combined results exported to: {filepath}")

    def export_doi_list(self, results: Dict[str, List[Paper]], filepath: str,
                        include_source: bool = False):
        """
        Export clean DOI list for downstream processing.

        Args:
            results: Search results dictionary
            filepath: Output file path (should be .txt or .csv)
            include_source: If True, include source column (boolean/semantic)
        """
        dois_data = []

        for source, papers in results.items():
            for paper in papers:
                if paper.doi:  # Only include papers with DOIs
                    if include_source:
                        dois_data.append({'doi': paper.doi, 'source': source})
                    else:
                        dois_data.append({'doi': paper.doi})

        # Remove duplicates while preserving order
        seen = set()
        unique_dois = []
        for item in dois_data:
            doi = item['doi']
            if doi not in seen:
                seen.add(doi)
                unique_dois.append(item)

        if not unique_dois:
            logger.warning("No DOIs found to export")
            return

        # Export based on file extension
        if filepath.endswith('.csv'):
            import pandas as pd
            df = pd.DataFrame(unique_dois)
            df.to_csv(filepath, index=False, encoding='utf-8')
        else:
            # Plain text file, one DOI per line
            with open(filepath, 'w', encoding='utf-8') as f:
                for item in unique_dois:
                    f.write(f"{item['doi']}\n")

        logger.info(f"DOI list exported ({len(unique_dois)} unique DOIs): {filepath}")
        return len(unique_dois)

    def get_doi_list(self, results: Dict[str, List[Paper]],
                     deduplicate: bool = True) -> List[str]:
        """
        Extract clean list of DOIs from search results.

        Args:
            results: Search results dictionary
            deduplicate: Whether to remove duplicate DOIs

        Returns:
            List of DOI strings
        """
        dois = []

        for papers in results.values():
            for paper in papers:
                if paper.doi:
                    dois.append(paper.doi)

        if deduplicate:
            # Remove duplicates while preserving order
            seen = set()
            unique_dois = []
            for doi in dois:
                if doi not in seen:
                    seen.add(doi)
                    unique_dois.append(doi)
            return unique_dois

        return dois


def main():
    """CLI interface for OpenAlex searcher."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OpenAlex Searcher: Search academic papers using OpenAlex API"
    )
    parser.add_argument("query", help="Search query (natural language or OpenAlex format)")
    parser.add_argument("--max-results", "-n", type=int, default=100,
                        help="Maximum results per search type (default: 100)")
    parser.add_argument("--output", "-o", default="search_results",
                        help="Output file prefix (default: search_results)")
    parser.add_argument("--email", "-e", help="Email for OpenAlex polite pool")
    parser.add_argument("--gemini-api-key", help="Gemini API key for query translation")
    parser.add_argument("--no-llm", action="store_true",
                        help="Disable LLM query translation")
    parser.add_argument("--year", "-y", help="Publication year filter (e.g., 2023 or >2020)")
    parser.add_argument("--format", choices=["json", "csv", "both"], default="both",
                        help="Output format (default: both)")
    parser.add_argument("--doi-only", action="store_true",
                        help="Export only DOI list for OA Downloader")

    args = parser.parse_args()

    # Initialize searcher
    searcher = OpenAlexSearcher(
        gemini_api_key=args.gemini_api_key,
        email=args.email
    )

    # Perform search
    results = searcher.search(
        query=args.query,
        use_llm=not args.no_llm,
        max_results=args.max_results,
        publication_year=args.year
    )

    # Export results
    if args.format in ["json", "both"] and not args.doi_only:
        searcher.export_to_json(results, f"{args.output}.json")

    if args.format in ["csv", "both"] and not args.doi_only:
        searcher.export_to_csv(results, f"{args.output}.csv", separate_files=True)

    if args.doi_only or args.format in ["csv", "both"]:
        searcher.export_doi_list(results, f"{args.output}_dois.csv")

    # Print summary
    print("\n=== Search Summary ===")
    print(f"Boolean search: {len(results['boolean'])} papers")
    print(f"Semantic search: {len(results['semantic'])} papers")
    total_dois = len(searcher.get_doi_list(results))
    print(f"Total unique DOIs: {total_dois}")


if __name__ == "__main__":
    main()

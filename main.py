#!/usr/bin/env python3
"""
OpenAlex OA Pipeline
====================

A unified tool that combines OpenAlex academic search with OA Downloader
to provide a complete research paper discovery and download workflow.

Features:
1. Natural language query to search papers using OpenAlex API
2. Boolean and semantic search support
3. Automatic query translation using LLM (OpenAI API)
4. Integrated OA paper download using multiple sources
5. Clean modular interface between search and download components

Usage:
    # Full pipeline: search and download
    python main.py "machine learning in drug discovery" --download --email your@email.com

    # Search only
    python main.py "CRISPR cancer therapy" --max-results 50

    # Download from existing search results
    python main.py --from-results search_results.csv --download --email your@email.com

Environment Variables:
    GEMINI_API_KEY:    Gemini API key for query translation
    OPENALEX_EMAIL: Email for OpenAlex polite pool
"""

import os
import sys
import argparse
import logging
from typing import Optional, List
from pathlib import Path

# Import local modules
from openalex_searcher import OpenAlexSearcher, Paper
from oa_downloader import OADownloader

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class OpenAlexOAPipeline:
    """
    Pipeline class that coordinates OpenAlex search and OA download.

    This class provides a clean interface between the search and download
    modules, handling data flow and configuration.
    """

    def __init__(self,
                 gemini_api_key: Optional[str] = None,
                 openalex_email: Optional[str] = None,
                 output_dir: str = "./downloads"):
        """
        Initialize the pipeline.

        Args:
            gemini_api_key: Gemini API key for query translation
            openalex_email: Email for OpenAlex API (recommended)
            output_dir: Directory to save downloaded PDFs
        """
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.openalex_email = openalex_email or os.getenv("OPENALEX_EMAIL")
        self.output_dir = output_dir

        # Initialize components
        self.searcher = OpenAlexSearcher(
            gemini_api_key=self.gemini_api_key,
            email=self.openalex_email
        )

        self.downloader: Optional[OADownloader] = None

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

    def search(self,
               query: str,
               use_llm: bool = True,
               max_results: int = 100,
               publication_year: Optional[str] = None,
               save_results: bool = True,
               output_prefix: str = "search_results") -> dict:
        """
        Search for papers using OpenAlex API.

        Args:
            query: Natural language research query
            use_llm: Whether to use LLM for query translation
            max_results: Maximum results per search type
            publication_year: Optional year filter
            save_results: Whether to save results to files
            output_prefix: Prefix for output files

        Returns:
            Dictionary with search results
        """
        logger.info(f"Starting search for: '{query}'")

        # Perform search
        results = self.searcher.search(
            query=query,
            use_llm=use_llm,
            max_results=max_results,
            publication_year=publication_year
        )

        # Save results if requested
        if save_results:
            self._save_search_results(results, output_prefix)

        return results

    def _save_search_results(self, results: dict, prefix: str):
        """Save search results to multiple formats."""
        # JSON format (full metadata)
        json_path = f"{prefix}.json"
        self.searcher.export_to_json(results, json_path)

        # CSV format (separate files for boolean and semantic)
        csv_path = f"{prefix}.csv"
        self.searcher.export_to_csv(results, csv_path, separate_files=True)

        # DOI list for download
        doi_csv_path = f"{prefix}_dois.csv"
        self.searcher.export_doi_list(results, doi_csv_path, include_source=True)

        # Plain text DOI list
        doi_txt_path = f"{prefix}_dois.txt"
        self.searcher.export_doi_list(results, doi_txt_path)

        logger.info(f"Search results saved with prefix: {prefix}")

    def download_papers(self,
                        doi_list: List[str],
                        email: str,
                        download_dir: Optional[str] = None) -> dict:
        """
        Download papers from DOI list.

        Args:
            doi_list: List of DOI strings
            email: Email for Unpaywall API (required)
            download_dir: Directory to save PDFs (default: self.output_dir)

        Returns:
            Dictionary with download statistics
        """
        if not doi_list:
            logger.warning("No DOIs provided for download")
            return {'success': 0, 'failed': 0, 'total': 0}

        download_dir = download_dir or self.output_dir

        # Initialize downloader
        self.downloader = OADownloader(
            email=email,
            output_dir=download_dir
        )

        logger.info(f"Starting download of {len(doi_list)} papers to {download_dir}")

        success_count = 0
        failed_dois = []

        # Process each DOI
        import time
        from tqdm import tqdm

        for doi in tqdm(doi_list, desc="Downloading papers"):
            if self.downloader.process_doi(doi):
                success_count += 1
            else:
                failed_dois.append(doi)
            time.sleep(0.5)  # Be polite to APIs

        # Save failed DOIs
        if failed_dois:
            failed_path = os.path.join(download_dir, "failed_downloads.txt")
            with open(failed_path, 'w') as f:
                for doi in failed_dois:
                    f.write(f"{doi}\n")
            logger.info(f"Failed DOIs saved to: {failed_path}")

        stats = {
            'total': len(doi_list),
            'success': success_count,
            'failed': len(failed_dois),
            'success_rate': success_count / len(doi_list) * 100 if doi_list else 0
        }

        logger.info(f"Download complete: {stats['success']}/{stats['total']} successful "
                    f"({stats['success_rate']:.1f}%)")

        return stats

    def download_from_results(self,
                              results: dict,
                              email: str,
                              download_dir: Optional[str] = None) -> dict:
        """
        Download papers from search results.

        Args:
            results: Search results dictionary from search()
            email: Email for Unpaywall API
            download_dir: Directory to save PDFs

        Returns:
            Dictionary with download statistics
        """
        doi_list = self.searcher.get_doi_list(results, deduplicate=True)
        return self.download_papers(doi_list, email, download_dir)

    def download_from_file(self,
                           filepath: str,
                           email: str,
                           download_dir: Optional[str] = None,
                           doi_column: str = "doi") -> dict:
        """
        Download papers from a CSV or text file containing DOIs.

        Args:
            filepath: Path to file with DOIs
            email: Email for Unpaywall API
            download_dir: Directory to save PDFs
            doi_column: Column name for CSV files (default: 'doi')

        Returns:
            Dictionary with download statistics
        """
        doi_list = self._load_dois_from_file(filepath, doi_column)
        return self.download_papers(doi_list, email, download_dir)

    def _load_dois_from_file(self, filepath: str, doi_column: str = "doi") -> List[str]:
        """Load DOIs from CSV or text file."""
        path = Path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        dois = []

        if filepath.endswith('.csv'):
            import pandas as pd
            df = pd.read_csv(filepath)

            # Try to find DOI column
            possible_columns = [doi_column, 'DOI', 'doi', 'Doi', 'DOI_number']
            found_column = None

            for col in possible_columns:
                if col in df.columns:
                    found_column = col
                    break

            if not found_column:
                raise ValueError(f"DOI column not found in CSV. Available columns: {list(df.columns)}")

            dois = df[found_column].dropna().astype(str).tolist()

        else:
            # Plain text file, one DOI per line
            with open(filepath, 'r') as f:
                for line in f:
                    doi = line.strip()
                    if doi:
                        dois.append(doi)

        # Clean DOIs
        cleaned_dois = []
        for doi in dois:
            doi = doi.strip()
            # Remove common prefixes
            for prefix in ['https://doi.org/', 'http://doi.org/', 'doi.org/']:
                if doi.startswith(prefix):
                    doi = doi[len(prefix):]
                    break
            if doi:
                cleaned_dois.append(doi)

        logger.info(f"Loaded {len(cleaned_dois)} DOIs from {filepath}")
        return cleaned_dois

    def run_full_pipeline(self,
                          query: str,
                          download_email: str,
                          use_llm: bool = True,
                          max_results: int = 100,
                          publication_year: Optional[str] = None,
                          output_prefix: str = "search_results") -> dict:
        """
        Run the complete pipeline: search and download.

        Args:
            query: Research query
            download_email: Email for Unpaywall API
            use_llm: Whether to use LLM for query translation
            max_results: Maximum results per search type
            publication_year: Optional year filter
            output_prefix: Prefix for output files

        Returns:
            Dictionary with complete pipeline results
        """
        # Step 1: Search
        search_results = self.search(
            query=query,
            use_llm=use_llm,
            max_results=max_results,
            publication_year=publication_year,
            save_results=True,
            output_prefix=output_prefix
        )

        # Step 2: Download
        download_stats = self.download_from_results(
            results=search_results,
            email=download_email
        )

        return {
            'search': {
                'query': query,
                'boolean_count': len(search_results['boolean']),
                'semantic_count': len(search_results['semantic']),
                'total_dois': len(self.searcher.get_doi_list(search_results))
            },
            'download': download_stats,
            'output_prefix': output_prefix,
            'output_dir': self.output_dir
        }


def print_banner():
    """Print welcome banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║              OpenAlex OA Pipeline                             ║
║                                                               ║
║  Search academic papers with OpenAlex + Download OA PDFs      ║
╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="OpenAlex OA Pipeline: Search and download academic papers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search and download (full pipeline)
  python main.py "machine learning in drug discovery" --download --email your@email.com

  # Search only, save results
  python main.py "CRISPR cancer therapy" --max-results 50

  # Download from existing results
  python main.py --from-file search_results_dois.csv --download --email your@email.com

  # Search with year filter
  python main.py "COVID-19 vaccine" --year ">2020" --download --email your@email.com

Environment Variables:
  GEMINI_API_KEY    Gemini API key for query translation
  OPENALEX_EMAIL    Email for OpenAlex polite pool
        """
    )

    # Search arguments
    parser.add_argument("query", nargs="?",
                        help="Search query (natural language)")
    parser.add_argument("--max-results", "-n", type=int, default=100,
                        help="Maximum results per search type (default: 100)")
    parser.add_argument("--year", "-y",
                        help="Publication year filter (e.g., 2023 or >2020)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Disable LLM query translation")
    parser.add_argument("--output-prefix", "-o", default="search_results",
                        help="Output file prefix (default: search_results)")

    # Download arguments
    parser.add_argument("--download", "-d", action="store_true",
                        help="Download papers after search")
    parser.add_argument("--email", "-e",
                        help="Email for Unpaywall API (required for download)")
    parser.add_argument("--download-dir", default="./downloads",
                        help="Directory to save PDFs (default: ./downloads)")

    # Input from file
    parser.add_argument("--from-file", "-f",
                        help="Load DOIs from file instead of searching")
    parser.add_argument("--from-results",
                        help="Load search results JSON file")
    parser.add_argument("--doi-column", default="doi",
                        help="DOI column name for CSV files (default: doi)")

    # Other options
    parser.add_argument("--gemini-api-key",
                        help="Gemini API key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print_banner()

    # Validate arguments
    if not args.query and not args.from_file and not args.from_results:
        parser.error("Must provide either a query, --from-file, or --from-results")

    download_email = args.email or os.getenv("UNPAYWALL_EMAIL")
    if args.download and not download_email:
        parser.error("--email is required when using --download (or set UNPAYWALL_EMAIL)")

    # Initialize pipeline
    pipeline = OpenAlexOAPipeline(
        gemini_api_key=args.gemini_api_key,
        output_dir=args.download_dir
    )

    # Execute based on mode
    if args.from_file:
        # Download from file mode
        print(f"\n📁 Loading DOIs from: {args.from_file}")
        stats = pipeline.download_from_file(
            filepath=args.from_file,
            email=download_email,
            doi_column=args.doi_column
        )

        print("\n" + "="*50)
        print("📊 DOWNLOAD SUMMARY")
        print("="*50)
        print(f"Total:     {stats['total']}")
        print(f"Success:   {stats['success']} ({stats['success_rate']:.1f}%)")
        print(f"Failed:    {stats['failed']}")
        print(f"Output:    {args.download_dir}")

    elif args.from_results:
        # Download from previous search results
        print(f"\n📁 Loading results from: {args.from_results}")

        import json
        with open(args.from_results, 'r') as f:
            search_results = json.load(f)

        # Convert back to Paper objects format
        results = {
            'boolean': [],
            'semantic': []
        }

        for key in ['boolean_results', 'semantic_results']:
            source = key.replace('_results', '')
            for item in search_results.get(key, []):
                paper = Paper(
                    title=item.get('title', ''),
                    doi=item.get('doi'),
                    authors=item.get('authors', []),
                    abstract=item.get('abstract'),
                    publication_year=item.get('publication_year'),
                    openalex_id=item.get('openalex_id', ''),
                    cited_by_count=item.get('cited_by_count', 0),
                    is_oa=item.get('is_oa', False),
                    source=source
                )
                results[source].append(paper)

        print(f"   Boolean results: {len(results['boolean'])}")
        print(f"   Semantic results: {len(results['semantic'])}")

        stats = pipeline.download_from_results(results, download_email)

        print("\n" + "="*50)
        print("📊 DOWNLOAD SUMMARY")
        print("="*50)
        print(f"Total:     {stats['total']}")
        print(f"Success:   {stats['success']} ({stats['success_rate']:.1f}%)")
        print(f"Failed:    {stats['failed']}")

    else:
        # Search mode (with optional download)
        print(f"\n🔍 Search Query: {args.query}")
        print(f"   Max results: {args.max_results}")
        print(f"   LLM translation: {'Disabled' if args.no_llm else 'Enabled'}")
        if args.year:
            print(f"   Year filter: {args.year}")

        if args.download:
            # Full pipeline
            print("\n⏳ Running full pipeline (search + download)...")
            results = pipeline.run_full_pipeline(
                query=args.query,
                download_email=download_email,
                use_llm=not args.no_llm,
                max_results=args.max_results,
                publication_year=args.year,
                output_prefix=args.output_prefix
            )

            print("\n" + "="*50)
            print("📊 PIPELINE SUMMARY")
            print("="*50)
            print("\n🔍 SEARCH RESULTS")
            print(f"  Boolean:  {results['search']['boolean_count']} papers")
            print(f"  Semantic: {results['search']['semantic_count']} papers")
            print(f"  Unique DOIs: {results['search']['total_dois']}")
            print("\n📥 DOWNLOAD RESULTS")
            print(f"  Total:    {results['download']['total']}")
            print(f"  Success:  {results['download']['success']} ({results['download']['success_rate']:.1f}%)")
            print(f"  Failed:   {results['download']['failed']}")
            print("\n📁 OUTPUT FILES")
            print(f"  Results:  {results['output_prefix']}.json/csv")
            print(f"  DOIs:     {results['output_prefix']}_dois.csv/txt")
            print(f"  PDFs:     {results['output_dir']}/")
        else:
            # Search only
            print("\n⏳ Searching...")
            results = pipeline.search(
                query=args.query,
                use_llm=not args.no_llm,
                max_results=args.max_results,
                publication_year=args.year,
                save_results=True,
                output_prefix=args.output_prefix
            )

            doi_count = len(pipeline.searcher.get_doi_list(results))

            print("\n" + "="*50)
            print("📊 SEARCH SUMMARY")
            print("="*50)
            print(f"Boolean:  {len(results['boolean'])} papers")
            print(f"Semantic: {len(results['semantic'])} papers")
            print(f"Unique DOIs: {doi_count}")
            print("\n📁 OUTPUT FILES")
            print(f"  Full results: {args.output_prefix}.json")
            print(f"  CSV results:  {args.output_prefix}_boolean.csv, {args.output_prefix}_semantic.csv")
            print(f"  DOI list:     {args.output_prefix}_dois.csv")

            print("\n💡 To download papers, run:")
            print(f"   python main.py --from-file {args.output_prefix}_dois.csv --download --email your@email.com")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()

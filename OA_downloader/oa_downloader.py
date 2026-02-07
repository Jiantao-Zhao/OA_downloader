#!/usr/bin/env python3
"""
OA Downloader
============

A robust tool to batch download Open Access (OA) academic papers given a list of DOIs.
It aggregates multiple data sources to maximize success rates:
1. Unpaywall API (Primary source, checks multiple OA locations)
2. Semantic Scholar API (Fallback source)
3. BioRxiv/MedRxiv API (Preprint fallback)
4. Landing Page Heuristics (Scans HTML pages for hidden PDF links)

Usage:
    python oa_downloader.py --input dois.csv --output ./pdfs --email your@email.com
"""

import os
import argparse
import logging
import time
import re
import pandas as pd
import requests
from urllib.parse import urlparse
from tqdm import tqdm
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# =========================
# CONFIGURATION
# =========================
UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"
SEMANTIC_SCHOLAR_API_BASE = "https://api.semanticscholar.org/graph/v1/paper/DOI:"
BIORXIV_API_BASE = "https://api.biorxiv.org/details/biorxiv"

DEFAULT_TIMEOUT = 20
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("download.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class OADownloader:
    def __init__(self, email: str, output_dir: str):
        self.email = email
        self.output_dir = output_dir
        self.failed_dois = []
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Setup Session with Retries
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })

    def _is_valid_pdf(self, response):
        """Check if response is a valid PDF using headers and magic bytes."""
        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/pdf' in content_type:
            return True
        
        # Peek at magic bytes if content type is ambiguous (e.g., application/octet-stream)
        try:
            chunk = next(response.iter_content(chunk_size=4), b'')
            if chunk.startswith(b'%PDF'):
                return True
        except StopIteration:
            pass
            
        return False

    def _download_from_url(self, url: str, save_path: str, depth: int = 0) -> bool:
        """
        Attempt to download PDF from a URL. 
        Recursively scans for links if an HTML page is encountered.
        """
        if not url or depth > 1: return False
        
        try:
            logger.debug(f"Trying URL: {url}")
            # Use stream=True to avoid downloading large HTML files into memory
            response = self.session.get(url, stream=True, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
            
            if response.status_code != 200:
                return False

            # 1. Check if it is a direct PDF
            if self._is_valid_pdf(response):
                with open(save_path, 'wb') as f:
                    # Write the peeked chunk if _is_valid_pdf consumed it? 
                    # Simpler approach: Re-request or careful iteration.
                    # Since _is_valid_pdf is a helper, let's just write blindly here if the helper passed.
                    # Ideally, we should handle the iterator. For simplicity in this script,
                    # we assume standard content-type check first.
                    pass 
                
                # Re-download properly to save to file (cleanest way)
                with self.session.get(url, stream=True, timeout=DEFAULT_TIMEOUT) as r:
                    with open(save_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                return True

            # 2. Heuristic: If it's an HTML page, look for PDF links (Landing Page Scanning)
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                html_content = response.text
                
                # Regex for PDF links
                # Matches: href="..." containing .pdf
                potential_links = re.findall(r'href=["\\]\["\\](https?://[^"\\]+\.pdf["\\]*)"\\]', html_content, re.IGNORECASE)
                
                # Matches: Relative links
                if not potential_links:
                    rel_links = re.findall(r'href=["\\]\["\\](/[^"\\]+\.pdf["\\]*)"\\]', html_content, re.IGNORECASE)
                    parsed_url = urlparse(url)
                    base = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    potential_links = [base + rl for rl in rel_links]

                # Try the first few found links
                for link in potential_links[:2]:
                    if self._download_from_url(link, save_path, depth + 1):
                        return True
                        
        except Exception as e:
            logger.debug(f"Download failed for {url}: {e}")
            
        return False

    def _get_unpaywall_urls(self, doi: str) -> list:
        """Fetch potential PDF URLs from Unpaywall."""
        urls = []
        try:
            resp = self.session.get(f"{UNPAYWALL_API_BASE}/{doi}?email={self.email}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('is_oa'):
                    for loc in data.get('oa_locations', []):
                        if loc.get('url_for_pdf'):
                            urls.append(loc['url_for_pdf'])
                        if loc.get('url'): # Landing page
                            urls.append(loc['url'])
        except Exception as e:
            logger.error(f"Unpaywall API error for {doi}: {e}")
        return urls

    def _get_semantic_scholar_url(self, doi: str) -> str:
        """Fetch PDF URL from Semantic Scholar."""
        try:
            resp = self.session.get(
                f"{SEMANTIC_SCHOLAR_API_BASE}{doi}?fields=openAccessPdf", 
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('openAccessPdf'):
                    return data['openAccessPdf'].get('url')
        except Exception:
            pass
        return None

    def _get_biorxiv_url(self, doi: str) -> str:
        """Construct BioRxiv PDF URL if valid."""
        try:
            resp = self.session.get(f"{BIORXIV_API_BASE}/{doi}", timeout=10)
            if resp.status_code == 200 and resp.json().get('collection'):
                 return f"https://www.biorxiv.org/content/{doi}v1.full.pdf"
        except Exception:
            pass
        return None

    def process_doi(self, doi: str) -> bool:
        """Pipeline to process a single DOI through all strategies."""
        safe_doi = doi.replace('/', '_').replace(':', '_')
        save_path = os.path.join(self.output_dir, f"{safe_doi}.pdf")
        
        if os.path.exists(save_path):
            logger.info(f"Skipping {doi} (already exists)")
            return True

        # Strategy 1: Unpaywall
        urls = self._get_unpaywall_urls(doi)
        for url in urls:
            # Special PMC handling
            if "ncbi.nlm.nih.gov/pmc/articles/" in url and "/pdf/" not in url:
                 # Try to guess the PDF link for PMC
                 if url.endswith("/"): url += "pdf/"
                 else: url += "/pdf/"
            
            if self._download_from_url(url, save_path):
                logger.info(f"Success (Unpaywall): {doi}")
                return True

        # Strategy 2: Semantic Scholar
        s2_url = self._get_semantic_scholar_url(doi)
        if s2_url and self._download_from_url(s2_url, save_path):
            logger.info(f"Success (Semantic Scholar): {doi}")
            return True

        # Strategy 3: BioRxiv
        bio_url = self._get_biorxiv_url(doi)
        if bio_url and self._download_from_url(bio_url, save_path):
            logger.info(f"Success (BioRxiv): {doi}")
            return True

        logger.warning(f"Failed to find PDF for: {doi}")
        return False

    def run(self, csv_path: str, doi_col: str):
        """Run the batch download process."""
        df = pd.read_csv(csv_path)
        
        if doi_col not in df.columns:
            raise ValueError(f"Column '{doi_col}' not found in CSV.")
            
        total = len(df)
        success = 0
        
        print(f"Starting download for {total} papers...")
        for _, row in tqdm(df.iterrows(), total=total):
            doi = str(row[doi_col]).strip()
            if self.process_doi(doi):
                success += 1
            else:
                self.failed_dois.append(row)
            
            time.sleep(0.5) # Be polite to APIs

        # Summary
        print("\n=== Download Summary ===")
        print(f"Total: {total}")
        print(f"Success: {success}")
        print(f"Failed: {len(self.failed_dois)}")
        
        if self.failed_dois:
            failed_df = pd.DataFrame(self.failed_dois)
            failed_path = "failed_downloads.csv"
            failed_df.to_csv(failed_path, index=False)
            print(f"Failed DOIs saved to {failed_path}")

def main():
    parser = argparse.ArgumentParser(description="OA Downloader: Batch download academic papers.")
    parser.add_argument("--input", "-i", required=True, help="Path to input CSV file containing DOIs")
    parser.add_argument("--output", "-o", required=True, help="Directory to save downloaded PDFs")
    parser.add_argument("--email", "-e", required=True, help="Your email (required for Unpaywall API)")
    parser.add_argument("--column", "-c", default="DOI", help="Name of the DOI column in CSV (default: DOI)")
    
    args = parser.parse_args()
    
    downloader = OADownloader(args.email, args.output)
    downloader.run(args.input, args.column)

if __name__ == "__main__":
    main()

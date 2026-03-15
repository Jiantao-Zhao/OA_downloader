# OA Downloader + OpenAlex Search

**OA Downloader** is a robust, Python-based tool designed to batch download Open Access (OA) academic papers given a list of Digital Object Identifiers (DOIs).

**NEW: OpenAlex Search Module** - A powerful addition that allows you to search for papers using natural language queries, with automatic translation to optimized search terms using Gemini API. Supports both Boolean and semantic search modes.

## Features

### OA Downloader Features
- **Multi-Source Retrieval**:
  - **Unpaywall API**: The primary source for legal OA status.
  - **Semantic Scholar API**: A powerful fallback for papers missed by Unpaywall.
  - **BioRxiv/MedRxiv**: Direct checking for preprints in life sciences.
- **Smart Handling**:
  - **Landing Page Scanning**: Automatically scans HTML landing pages to find hidden PDF links.
  - **PMC Heuristics**: Intelligently constructs PDF URLs for PubMed Central articles.
  - **Validation**: Verifies downloaded files are valid PDFs (checks magic bytes).
- **Resilient**: Implements retries and timeouts for reliable network operations.

### OpenAlex Search Features
- **Natural Language Query**: Describe your research interest in plain English.
- **LLM-Powered Translation**: Automatically converts your query to optimized OpenAlex search syntax using Gemini API.
- **Dual Search Modes**:
  - **Boolean Search**: Precise keyword matching with field-specific queries.
  - **Semantic Search**: Relevance-ranked results prioritizing highly-cited papers.
- **Rich Metadata**: Returns title, DOI, authors, abstract, publication year, and citation count.
- **Flexible Export**: Save results as JSON, CSV, or clean DOI lists for download.

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/OA_downloader.git
   cd OA_downloader
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Configure environment variables:
   ```bash
   cp env.example .env
   # Edit .env with your API keys
   ```

## Usage

### Quick Start: Full Pipeline (Search + Download)

Search for papers and automatically download the open access ones:

```bash
python main.py "machine learning in drug discovery" \
    --download \
    --email your@email.com \
    --gemini-api-key your_gemini_key
```

### Step-by-Step Workflow

#### 1. Search Only

Search for papers and save results without downloading:

```bash
# Basic search
python main.py "CRISPR cancer therapy"

# Search with options
python main.py "COVID-19 vaccine" \
    --max-results 50 \
    --year ">2020" \
    --output-prefix my_search
```

This creates:
- `my_search.json` - Full metadata in JSON format
- `my_search_boolean.csv` - Boolean search results
- `my_search_semantic.csv` - Semantic search results
- `my_search_dois.csv` - Clean DOI list with metadata
- `my_search_dois.txt` - Plain text DOI list (one per line)

#### 2. Download Papers

Download papers from existing DOI list:

```bash
# From CSV file
python main.py --from-file my_search_dois.csv \
    --download \
    --email your@email.com \
    --download-dir ./my_pdfs

# From text file (one DOI per line)
python main.py --from-file dois.txt \
    --download \
    --email your@email.com
```

### Command Reference

#### Main Pipeline (`main.py`)

| Argument | Short | Description |
|----------|-------|-------------|
| `query` | - | Search query (natural language) |
| `--download` | `-d` | Enable download after search |
| `--email` | `-e` | Email for Unpaywall API (required for download) |
| `--max-results` | `-n` | Max results per search type (default: 100) |
| `--year` | `-y` | Year filter (e.g., `2023` or `>2020`) |
| `--no-llm` | - | Disable LLM query translation |
| `--from-file` | `-f` | Load DOIs from file instead of searching |
| `--output-prefix` | `-o` | Output file prefix (default: search_results) |
| `--download-dir` | - | Directory for PDFs (default: ./downloads) |
| `--gemini-api-key` | - | Gemini API key (or set env var) |

#### Standalone OpenAlex Searcher (`openalex_searcher.py`)

```bash
# Basic search
python openalex_searcher.py "your research query"

# Advanced usage
python openalex_searcher.py "deep learning protein structure" \
    --max-results 200 \
    --year ">2022" \
    --format both \
    --output results

# Export only DOIs for OA Downloader
python openalex_searcher.py "your query" --doi-only --output dois
```

#### Standalone OA Downloader (`oa_downloader.py`)

```bash
# From CSV file
python oa_downloader.py --input dois.csv --output ./pdfs --email your@email.com

# Custom column name
python oa_downloader.py -i data.csv -o ./pdfs -e your@email.com -c doi_column
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Gemini API key for query translation |
| `OPENALEX_EMAIL` | Email for OpenAlex polite pool (recommended) |
| `OPENALEX_API_KEY` | OpenAlex API key for API access |

## How It Works

### Search Pipeline

1. **Query Translation** (if LLM enabled):
   - Your natural language query is sent to Gemini API
   - LLM converts it to optimized OpenAlex search syntax
   - Example: `"AI in healthcare"` → `(abstract.search:"artificial intelligence" OR abstract.search:"machine learning") AND (abstract.search:"healthcare" OR abstract.search:"medicine")`

2. **Boolean Search**:
   - Uses OpenAlex `works` endpoint with structured query
   - Supports field-specific searches (title, abstract, author, etc.)
   - Returns papers matching exact criteria

3. **Semantic Search**:
   - Uses citation-weighted relevance ranking
   - Prioritizes highly-cited papers in the field
   - Good for discovering influential works

4. **Metadata Extraction**:
   - Parses OpenAlex response
   - Reconstructs abstracts from inverted index
   - Extracts DOI, authors, publication year, citation count

5. **Export**:
   - Saves full metadata to JSON
   - Exports CSV files for analysis
   - Generates clean DOI list for download

### Download Pipeline

1. **Read DOI List**: From CSV, text file, or direct from search results
2. **Multi-Source Retrieval**: For each DOI:
   - Query **Unpaywall** for OA locations
   - Query **Semantic Scholar** for OA PDF links
   - Check **BioRxiv** for preprints
   - Scan landing pages for hidden PDF links
3. **Download & Validate**: Verify PDF magic bytes before saving
4. **Report**: Generate summary and failed downloads list

## Python API

You can also use the modules programmatically:

```python
from openalex_searcher import OpenAlexSearcher
from oa_downloader import OADownloader

# Search for papers
searcher = OpenAlexSearcher(gemini_api_key="your_key", email="your@email.com")
results = searcher.search("machine learning drug discovery", max_results=50)

# Get DOI list
dois = searcher.get_doi_list(results)

# Download papers
downloader = OADownloader(email="your@email.com", output_dir="./pdfs")
downloader.download_doi_list(dois)
```

Or use the unified pipeline:

```python
from main import OpenAlexOAPipeline

pipeline = OpenAlexOAPipeline(
    gemini_api_key="your_key",
    output_dir="./downloads"
)

# Full pipeline
stats = pipeline.run_full_pipeline(
    query="CRISPR gene editing",
    download_email="your@email.com",
    max_results=100
)

print(f"Found: {stats['search']['total_dois']} papers")
print(f"Downloaded: {stats['download']['success']}/{stats['download']['total']}")
```

## Output Formats

### JSON Format
```json
{
  "timestamp": "2024-01-15T10:30:00",
  "boolean_count": 50,
  "semantic_count": 50,
  "boolean_results": [
    {
      "title": "Paper Title",
      "doi": "10.1234/example",
      "authors": ["Author A", "Author B"],
      "abstract": "Paper abstract...",
      "publication_year": 2023,
      "cited_by_count": 42,
      "is_oa": true
    }
  ],
  "semantic_results": [...]
}
```

### CSV Format
| title | doi | authors | abstract | publication_year | ... |
|-------|-----|---------|----------|------------------|-----|
| Paper Title | 10.1234/example | Author A; Author B | Abstract text... | 2023 | ... |

## License

MIT License

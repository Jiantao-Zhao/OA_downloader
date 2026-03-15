# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Related Projects

- **HYDRO_ZOO** (`../HYDRO_ZOO/`): Peptide-hydrazone chemistry research knowledge base
  - Contains knowledge extraction tools and extracted knowledge from PDF papers
  - V1 vs V2 extraction comparison data available (see HYDRO_ZOO documentation)

## Project Overview

OA Downloader is a Python-based academic paper discovery and download tool with two main components:

1. **OpenAlex Search Module** (`openalex_searcher.py`): Search academic papers using OpenAlex API with optional LLM-powered query translation
2. **OA Downloader Module** (`oa_downloader.py`): Download open access PDFs from multiple sources (Unpaywall, Semantic Scholar, BioRxiv)
3. **Unified Pipeline** (`main.py`): Combines search and download in a single workflow

## Architecture

### Core Components

```
main.py                    # CLI entry point and unified pipeline
├── OpenAlexSearcher       # Search papers via OpenAlex API
│   ├── LLMQueryTranslator # Gemini-powered query translation
│   ├── search_boolean()   # Boolean search with field-specific queries
│   └── search_semantic()  # Relevance-ranked semantic search
│
└── OADownloader           # Download PDFs from multiple sources
    ├── Unpaywall API      # Primary OA source
    ├── Semantic Scholar   # Fallback source
    └── BioRxiv            # Preprint source
```

### Data Flow

1. **Search Pipeline**: Natural Language Query → LLM Translation (optional) → OpenAlex API → Boolean + Semantic Search → JSON/CSV Export
2. **Download Pipeline**: DOI List → Multi-Source Retrieval → PDF Validation → Save to Disk

## Common Commands

### Environment Setup
```bash
# Set required environment variables
export GEMINI_API_KEY="your_gemini_key"
export OPENALEX_EMAIL="your@email.com"

# Or use .env file
cp env.example .env  # if it exists
```

### Full Pipeline (Search + Download)
```bash
python main.py "your research query" --download --email your@email.com
```

### Search Only
```bash
# Basic search
python main.py "machine learning in drug discovery"

# Search with options
python main.py "CRISPR cancer therapy" --max-results 50 --year ">2020"
```

### Download from DOI List
```bash
# From CSV file
python main.py --from-file search_results_dois.csv --download --email your@email.com

# From text file (one DOI per line)
python main.py --from-file dois.txt --download --email your@email.com
```

### Standalone Searcher
```bash
python openalex_searcher.py "your query" --max-results 100 --format both --output results
```

### Standalone Downloader
```bash
python oa_downloader.py --input dois.csv --output ./pdfs --email your@email.com --column doi
```

## Python API Usage

```python
from main import OpenAlexOAPipeline

# Full pipeline
pipeline = OpenAlexOAPipeline(
    gemini_api_key="your_key",
    output_dir="./downloads"
)

stats = pipeline.run_full_pipeline(
    query="hydrazone peptide catalysis",
    download_email="your@email.com",
    max_results=100
)

print(f"Found: {stats['search']['total_dois']} papers")
print(f"Downloaded: {stats['download']['success']}/{stats['download']['total']}")
```

## Key Design Patterns

### Search Strategy
- OpenAlex uses simplified keyword queries (not complex Boolean syntax)
- Multiple parallel searches with different keywords, then deduplicate and filter
- LLM translates natural language to optimized search syntax using Gemini API
- Abstracts are reconstructed from OpenAlex's inverted index format

### Download Strategy
- Cascading fallback: Unpaywall → Semantic Scholar → BioRxiv → Landing Page Scan
- PDF validation uses magic bytes (`%PDF`) not just file extension
- Polite rate limiting (0.5s delay between requests)
- Failed DOIs tracked in `failed_downloads.csv`

### Data Classes
- `Paper`: Core dataclass with title, DOI, authors, abstract, year, citations
- Export methods: `to_dict()`, `to_csv_row()` for serialization

## Output Files

Search generates:
- `{prefix}.json` - Full metadata
- `{prefix}_boolean.csv` / `{prefix}_semantic.csv` - Split results
- `{prefix}_dois.txt` - Plain text DOI list for download

Download generates:
- `{doi}.pdf` - Downloaded papers
- `failed_downloads.txt` - List of failed DOIs

## Dependencies

Core dependencies (see imports in files):
- `requests` - HTTP client with retry logic
- `pandas` - CSV/DataFrame handling
- `tqdm` - Progress bars
- Standard library: `os`, `json`, `logging`, `time`, `re`, `dataclasses`

Optional:
- Gemini API key for LLM query translation (falls back to raw query if not provided)

## Important Implementation Details

1. **Email Required**: Unpaywall API requires email for polite pool access
2. **No Rate Limit Issues**: Built-in delays and retries handle API limits
3. **PDF Validation**: Downloads are validated as actual PDFs before saving
4. **OpenAlex Syntax**: Use simplified queries like `"hydrazone peptide"` not complex Boolean
5. **Abstract Reconstruction**: OpenAlex returns inverted index; code reconstructs text by sorting word positions

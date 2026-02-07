
# OA Downloader

**OA Downloader** is a robust, Python-based tool designed to batch download Open Access (OA) academic papers given a list of Digital Object Identifiers (DOIs). 

It goes beyond simple API lookups by aggregating multiple sources and using smart heuristics to maximize the success rate of retrieving PDF files.

## Features

- **Multi-Source Retrieval**:
  - **Unpaywall API**: The primary source for legal OA status.
  - **Semantic Scholar API**: A powerful fallback for papers missed by Unpaywall.
  - **BioRxiv/MedRxiv**: Direct checking for preprints in life sciences.
- **Smart Handling**:
  - **Landing Page Scanning**: Automatically scans HTML landing pages to find hidden PDF links.
  - **PMC Heuristics**: Intelligently constructs PDF URLs for PubMed Central articles.
  - **Validation**: Verifies downloaded files are valid PDFs (checks magic bytes).
- **Resilient**: Implements retries and timeouts for reliable network operations.
- **Detailed Logging**: Keeps track of successes and failures.

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

## Usage

Prepare a CSV file (e.g., `dois.csv`) with a column containing DOIs (default column name is `DOI`).

Run the script:

```bash
python oa_downloader.py --input dois.csv --output ./pdfs --email your@email.com
```

### Arguments

- `--input`, `-i`: Path to the input CSV file. (Required)
- `--output`, `-o`: Directory where PDFs will be saved. (Required)
- `--email`, `-e`: Your email address. This is required by the Unpaywall API for polite usage. (Required)
- `--column`, `-c`: The name of the column in your CSV that contains the DOIs. (Default: `DOI`)

## Example

```bash
python oa_downloader.py -i data/my_papers.csv -o ./downloads -e research@example.com
```

## How It Works

1. **Read CSV**: Loads the list of DOIs.
2. **Strategy Loop**: For each DOI, it tries the following strategies in order:
   - Queries **Unpaywall**. If a PDF link is found, it downloads it. If a landing page is found, it scans the page for PDF links.
   - Queries **Semantic Scholar**. If an OA PDF is indexed, it downloads it.
   - Checks **BioRxiv**. If it's a preprint, it constructs the PDF URL.
3. **Verify & Save**: Downloads are checked to ensure they are valid PDFs before saving.
4. **Report**: Generates a summary and a `failed_downloads.csv` for any papers that could not be retrieved.

## License

MIT License

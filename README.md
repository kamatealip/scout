# Scout

Scout is a local documentation search application built with Flask. It allows users to search through HTML documentation files stored locally, providing a fast and efficient way to navigate technical documentation without relying on external search engines.

The application indexes HTML documents into a SQLite database, uses BM25-style ranking for relevance, and offers a clean, search-engine-like interface with features such as section filtering, click tracking, and snippet highlighting.

## Features

- Recursive indexing for `.html`, `.xhtml`, and `.xhtml` files
- SQLite-backed search index in `scout.db`
- BM25-style ranking with phrase-aware boosts
- Optional stemming for broader matches
- Section filtering based on indexed document paths
- Click tracking that helps frequently opened documents rise in results
- Search-engine-style flow: `/` for home, `/search?q=...` for results
- Safe local document serving through `/docs/<path>`

## Requirements

- Python `3.13+`

## Setup

Clone the repo and enter the project:

```bash
git clone <your-repo-url> scout
cd scout
```

Create an environment and install dependencies.

Using `uv`:

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

Using `venv` + `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Build the Index

Index a folder containing HTML files:

```bash
python main.py INDEX docs
```

This creates or updates:

- `scout.db` for indexed word counts and click counts

## Run the App

```bash
python main.py SERVE
```

Open:

- `http://127.0.0.1:5000`

## How It Works

### Home page

- `/` shows a minimal Scout landing page
- the home page contains only the Scout branding and a search box
- submitting the form navigates to `/search?q=...`

### Results page

- `/search` renders the results layout
- the top bar keeps the search box visible, like a traditional search engine
- users can refine results with:
  - `section`
  - `stemming`
- each result shows:
  - a document link
  - its doc path
  - a section label
  - click metadata
  - a highlighted text snippet

### Ranking

- queries are tokenized with the same tokenizer used during indexing
- stopwords are removed before scoring
- a BM25-style calculation balances term frequency and document length

## Project Structure

- `app.py`: Contains the Flask application setup, routes, and search logic.
- `indexer.py`: Handles the indexing of HTML files into the SQLite database.
- `main.py`: Command-line interface for indexing and serving the app.
- `search.py`: Implements the search functionality and ranking algorithms.
- `templates/`: HTML templates for the web interface.
- `static/`: Static assets like CSS stylesheets.
- `docs/`: Pre-indexed documentation for popular Python libraries (NumPy, Pandas, Python standard library).
- `tests/`: Unit tests for the application.
- `pyproject.toml`: Project configuration and dependencies.

## Included Documentation

The project comes pre-loaded with documentation for:

- **NumPy**: Comprehensive documentation for the NumPy library, including API reference, tutorials, and examples.
- **Pandas**: Full documentation for Pandas, covering data manipulation, analysis, and visualization.
- **Python**: Official Python documentation, including language reference, library reference, and tutorials.

You can index additional documentation by running `python main.py INDEX <path-to-docs>`.

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests on the project's repository.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

- exact phrase hits can add a ranking boost
- click history can boost documents users open often
- cached normalization and corpus stats speed up repeated searches

### Document opening

- clicking a result first hits `/result/<path:doc_path>`
- Scout increments the click count for that document
- the user is then redirected to `/docs/<path:doc_path>`
- document paths are validated before serving

## Common Commands

Rebuild the index:

```bash
python main.py INDEX docs
```

Start the server:

```bash
python main.py SERVE
```

Run tests:

```bash
python -m unittest discover -s tests -q
```

With `uv`:

```bash
uv run python -m unittest discover -s tests -q
```

Enable Flask debug mode:

```bash
FLASK_DEBUG=1 python main.py SERVE
```

## Project Layout

- `app.py` contains Flask routes and page context builders
- `indexer.py` handles HTML parsing, indexing, SQLite persistence, and document text extraction
- `search.py` contains query preparation, ranking, filtering, and snippet generation
- `templates/index.html` is the home page
- `templates/search.html` is the results page
- `templates/_search_results.html` renders the result list and search states
- `static/styles.css` contains the shared home/results styling
- `tests/test_app.py` covers indexing, search ranking, routes, and UI behavior

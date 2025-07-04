# FastSymApi

The FastSymApi server is a Fast API server designed for debugging and development environments. It allows users to download and cache symbols from Microsoft, Google, and Mozilla symbol servers. Additionally, users can easily add support for other symbol servers.

When clients connect to FastSymApi and attempt to download a symbol, the server first checks if the symbol exists within its `./fastsymapi/symbols` cache. If found, the server returns the symbol; otherwise, it responds with a status `404` and proceeds to download the symbol. On subsequent requests, if the symbol is already downloaded and cached, the server returns it, either compressed using GZIP or decompressed based on the presence of the Accept-Encoding: gzip header. GZIP compression reduces bandwidth usage and improves download speed for clients.

FastSymApi has been tested and works with the following tools:

- x64dbg
- WinDbg
- Symchk

Supports the following symbol servers:

- <http://msdl.microsoft.com/download/symbols>
- <http://chromium-browser-symsrv.commondatastorage.googleapis.com>
- <http://symbols.mozilla.org>

## Setup FastSymApi

### Prerequisites

- Python 3.11 or higher
- [UV package manager](https://docs.astral.sh/uv/) (recommended) or pip

### Quick Start with UV (Recommended)

Clone the repository

```bash
git clone https://github.com/P1tt1cus/FastSymApi
cd FastSymApi
```

Install UV if you haven't already:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install dependencies and sync the project:

```bash
uv sync
```

Start the server:

```bash
# Production mode
uv run uvicorn fastsymapi:app --host 0.0.0.0 --port 80

# Or use the built-in command
uv run fastsymapi
```

Debug Mode:

```bash
uv run uvicorn fastsymapi:app --reload
```

### Alternative Setup with pip

Install the requirements:

```bash
pip install -r requirements.txt 
```

Start the server:

```bash
uvicorn fastsymapi:app --host 0.0.0.0 --port 80 
```

Debug Mode:

```bash
uvicorn fastsymapi:app --reload 
```

## Development

### Run Tests 

With UV:
```bash
uv run pytest fastsymapi_tests.py
```

With pip:
```bash
pytest fastsymapi_tests.py
```

### Build Package

With UV:
```bash
uv build
```

With pip:
```bash
python -m build
```

## GitHub Actions

This project includes automated testing and building through GitHub Actions. The workflow:

- **Tests**: Runs on Python 3.11 and 3.12 with pytest
- **Health Check**: Verifies the API server starts correctly
- **Build**: Creates distributable packages
- **Artifacts**: Uploads build artifacts for distribution

The workflow is triggered on pushes to `main` and `develop` branches, and on pull requests to `main`.

## Configure x64dbg

**options** >> **preferences** >> **misc**

Symbol store

```
http://FastSymApiServerIp/
```

## Configure WinDbg

```
.sympath srv*C:\symbols*http://FastSymApiServerIp/
```

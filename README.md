# FastSymApi

A high-performance [FastAPI](https://fastapi.tiangolo.com/) server for downloading, caching, and serving symbol files (PDBs) from multiple symbol servers. Designed for debugging and development environments, it works with tools like x64dbg, WinDbg, and Symchk.

When a client requests a symbol, the server checks its local cache (`./fastsymapi/symbols`). If the symbol is found, it is returned immediately — optionally GZIP-compressed based on the `Accept-Encoding` header. If the symbol is not cached, the server responds with `404` and begins downloading it in the background. On the next request the cached symbol is served.

## Features

- Automatic symbol caching from multiple symbol servers
- GZIP compression support for reduced bandwidth
- Concurrent download support with file locking
- Retry logic with exponential backoff
- Configurable performance via environment variables
- SQLite database for tracking symbol entries
- Path sanitization and input validation

See [CONFIGURATION.md](CONFIGURATION.md) for detailed configuration options.

## Supported Symbol Servers

- <http://msdl.microsoft.com/download/symbols> (Microsoft)
- <http://chromium-browser-symsrv.commondatastorage.googleapis.com> (Google)
- <http://symbols.mozilla.org> (Mozilla)
- <http://symbols.mozilla.org/try> (Mozilla Try)

## Requirements

- Python 3.12 or higher

## Setup

Clone the repository:

```bash
git clone https://github.com/P1tt1cus/FastSymApi
cd FastSymApi
```

Install dependencies using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv sync
```

Or using pip:

```bash
pip install .
```

For development (includes pytest, httpx, and ruff):

```bash
uv sync --extra dev
```

## Running the Server

Start the server:

```bash
uvicorn fastsymapi:app --host 0.0.0.0 --port 80
```

Development mode with auto-reload:

```bash
uvicorn fastsymapi:app --reload
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{pdbname}/{guid}/{pdbfile}` | Retrieve a symbol file |
| `GET` | `/download/symbols/{pdbname}/{guid}/{pdbfile}` | Alternate symbol retrieval path |
| `GET` | `/symbols` | List all tracked symbol entries |
| `GET` | `/health` | Health check (`{"status": "ok"}`) |

## Running Tests

```bash
pytest
```

Verbose output:

```bash
pytest -v
```

## Client Configuration

### x64dbg

**Options** > **Preferences** > **Misc**

Set the symbol store to:

```
http://FastSymApiServerIp/
```

### WinDbg

```
.sympath srv*C:\symbols*http://FastSymApiServerIp/
```

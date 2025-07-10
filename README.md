# FastSymApi

The FastSymApi server is a Fast API server designed for debugging and development environments. It allows users to download and cache symbols from Microsoft, Google, and Mozilla symbol servers. Additionally, users can easily add support for other symbol servers.

When clients connect to FastSymApi and attempt to download a symbol, the server first checks if the symbol exists within its `./fastsymapi/symbols` cache. If found, the server returns the symbol; otherwise, it responds with a status `404` and proceeds to download the symbol. On subsequent requests, if the symbol is already downloaded and cached, the server returns it, either compressed using GZIP or decompressed based on the presence of the Accept-Encoding: gzip header. GZIP compression reduces bandwidth usage and improves download speed for clients.

## Security and Robustness Improvements

FastSymApi includes comprehensive security and robustness features:

- **Path Sanitization**: Prevents directory traversal attacks by validating all path components
- **Input Validation**: Validates all PDB entry fields to prevent injection attacks
- **File Locking**: Thread-safe file operations prevent race conditions during concurrent downloads
- **Retry Logic**: Automatic retry with exponential backoff for network requests
- **Memory Management**: Configurable memory limits for streaming operations
- **Error Handling**: Comprehensive error logging and graceful failure handling
- **Configurable Performance**: Environment variables for tuning chunk sizes and retry behavior

See [CONFIGURATION.md](CONFIGURATION.md) for detailed configuration options.

FastSymApi has been tested and works with the following tools:

- x64dbg
- WinDbg
- Symchk

Supports the following symbol servers:

- <http://msdl.microsoft.com/download/symbols>
- <http://chromium-browser-symsrv.commondatastorage.googleapis.com>
- <http://symbols.mozilla.org>

## Setup FastSymApi

Clone the repository

```
git clone https://github.com/P1tt1cus/FastSymApi
```

Install the requirements

```
pip install requirements.txt 
```

Start the server

```
uvicorn fastsymapi:app --host 0.0.0.0 --port 80 
```

Debug Mode

```
uvicorn fastsymapi:app --reload 
```

## Run Tests 

Run the original tests:
```
pytest fastsymapi_tests.py
```

Run comprehensive robustness tests:
```
pytest test_symbols_improved.py
```

Run all tests:
```
pytest
```

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

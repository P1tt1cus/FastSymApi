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

Clone the repository

```
git clone https://github.com/P1tt1cus/FastSymApi
```

## Setup with UV (Recommended)

Install UV package manager if not already installed:

```
pip install uv
```

Install dependencies using UV:

```
uv sync
```

**Note about purest dependency**: The project includes a `purest` dependency as part of the UV format conversion. However, `purest` v0.0.2 has build issues. To attempt installation of purest:

```
uv sync --extra purest
```

This may fail due to package build issues, but the core application will work without it.

Start the server:

```
uv run uvicorn fastsymapi:app --host 0.0.0.0 --port 80 
```

Debug Mode:

```
uv run uvicorn fastsymapi:app --reload 
```

## Setup with pip (Legacy)

Install the requirements

```
pip install -r requirements.txt 
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

With UV:
```
uv run pytest fastsymapi_tests.py
```

With pip:
```
pytest fastsymapi_tests.py
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

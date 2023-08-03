# FastSymApi v1.0

The FastSymApi server is a Fast API server designed for debugging and development environments. It allows users to download and cache symbols from Microsoft, Google, and Mozilla symbol servers. Additionally, users can easily add support for other symbol servers.

When clients connect to FastSymApi and attempt to download a symbol, the server first checks if the symbol exists within its `./fastsymapi/symbols` cache. If found, the server returns the symbol; otherwise, it responds with a status `404` and proceeds to download the symbol. On subsequent requests, if the symbol is already downloaded and cached, the server returns it, either compressed using GZIP or decompressed based on the presence of the Accept-Encoding: gzip header. GZIP compression reduces bandwidth usage and improves download speed for clients.

FastSymApi has been tested and works with the following tools:

- x64dbg
- WinDbg 
- Symchk

Supports the following symbol servers:

- http://msdl.microsoft.com/download/symbols
- http://chromium-browser-symsrv.commondatastorage.googleapis.com
- http://symbols.mozilla.org

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
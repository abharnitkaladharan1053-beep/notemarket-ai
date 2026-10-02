#!/usr/bin/env python3
"""
NoteMarket AI Server Starter
Run: python start_server.py
"""
import sys
import os

try:
    import uvicorn
    from backend.server import app
    port = int(os.environ.get("PORT", 5500))
    host = os.environ.get("HOST", "0.0.0.0")
    print("=" * 60)
    print("  📚 NoteMarket AI — Full-Stack Server")
    print(f"  🌐 Local URL:   http://localhost:{port}")
    print(f"  📡 Network URL: http://{host}:{port}")
    print(f"  📡 API Health:  http://localhost:{port}/api/health")
    print(f"  🤖 AI Study:    http://localhost:{port}/api/ai/chat")
    print("=" * 60)
    uvicorn.run("backend.server:app", host=host, port=port, reload=False if os.environ.get("PORT") else True)
except ImportError:
    print("FastAPI / Uvicorn not found, running standard Python HTTP server on port 5500...")
    import http.server
    import socketserver
    port = int(os.environ.get("PORT", 5500))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Serving NoteMarket AI at http://localhost:{port}")
        httpd.serve_forever()

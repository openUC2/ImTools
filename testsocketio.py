from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from socketio import ASGIApp, AsyncServer
import uvicorn
# Create a Socket.IO server instance
sio = AsyncServer(async_mode="asgi", cors_allowed_origins="*")

# Wrap it as an ASGI app
sio_app = ASGIApp(sio)

# Create the FastAPI app and add middleware
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the Socket.IO app
app.mount("/socket.io", sio_app)

# Define an HTTP endpoint
@app.get("/")
async def read_root():
    return {"message": "Hello, Socket.IO!"}

# Handle a new client connection
@sio.on("connect")
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit("welcome", {"message": "Welcome to the server!"}, room=sid)

# Handle client disconnections
@sio.on("disconnect")
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

# Handle custom events
@sio.on("client_message")
async def handle_client_message(sid, data):
    print(f"Message from {sid}: {data}")
    await sio.emit("server_message", {"text": f"Echo: {data['text']}"})  # Broadcast to all clients

# Broadcast a message to all clients
async def broadcast_message(message):
    await sio.emit("broadcast", {"message": message})

import asyncio
asyncio.run(broadcast_message("This is a broadcast!"))

uvicorn.run(app, host="0.0.0.0", port=8002)
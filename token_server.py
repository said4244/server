"""
Token server for Tavus Avatar Flutter clients
Generates JWT tokens for connecting to LiveKit rooms
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from datetime import timedelta
import os
from dotenv import load_dotenv
import logging
import json
import subprocess
import psutil

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Tavus Avatar Token Server")

# Configure CORS for Flutter web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domains
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# LiveKit credentials
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "wss://cloud.livekit.io")

# Validate credentials on startup
if not all([LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
    logger.error("Missing LiveKit credentials in .env file")
    logger.error(f"LIVEKIT_API_KEY: {'✓' if LIVEKIT_API_KEY else '✗'}")
    logger.error(f"LIVEKIT_API_SECRET: {'✓' if LIVEKIT_API_SECRET else '✗'}")
else:
    logger.info("LiveKit credentials loaded successfully")
    logger.info(f"LiveKit URL: {LIVEKIT_URL}")


@app.get("/token")
async def create_token(
    identity: str = None,
    room: str = None
):
    """
    Generate a token for connecting to LiveKit room with Tavus avatar
    
    Args:
        identity: User identifier (optional)
        room: Room name to join (optional)
    
    Returns:
        JSON with accessToken and connection details
    """
    
    # Get and increment counter from file
    counter = increment_counter()
    
    # Generate default values if none provided
    if not identity:
        identity = f"avatar-user-{counter}"
    if not room:
        room = f"avatar-room-{counter}"
    
    if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise HTTPException(
            status_code=500, 
            detail="LiveKit credentials not configured. Check .env file."
        )
    
    try:
        # Create access token
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        # Set user identity
        token.with_identity(identity).with_name(f"User-{identity}")
        
        # Grant permissions for avatar interaction
        token.with_grants(api.VideoGrants(
            room_join=True,
            room=room,
            can_subscribe=True,      # Subscribe to avatar video/audio
            can_publish=True,        # Publish user audio
            can_publish_data=True,   # For future data channel features
        ))
        
        # Set expiration (24 hours)
        token.with_ttl(timedelta(hours=24))
        
        # Add metadata if needed
        token.with_metadata(
            json.dumps({
                "client": "flutter",
                "avatar_enabled": True
            })
        )
        
        # Generate JWT
        jwt_token = token.to_jwt()
        
        logger.info(f"Token generated for {identity} in room {room}")
        
        # Start new agent for this room
        #await start_new_agent(room)
        
        return {
            "accessToken": jwt_token,
            "url": LIVEKIT_URL,
            "room": room,
            "identity": identity,
            "expiresIn": 86400  # 24 hours in seconds
        }
        
    except Exception as e:
        logger.error(f"Error generating token: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Token generation failed: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "livekit_configured": bool(LIVEKIT_API_KEY and LIVEKIT_API_SECRET),
        "livekit_url": LIVEKIT_URL,
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Tavus Avatar Token Server",
        "description": "Generates tokens for Flutter clients to connect to Tavus avatar sessions",
        "endpoints": {
            "/token": "Get access token for LiveKit room",
            "/health": "Health check",
            "/rooms": "List active rooms (if enabled)",
        },
        "usage": "GET /token?identity=your-name&room=your-room"
    }


@app.get("/rooms")
async def list_rooms():
    """List active rooms (optional endpoint)"""
    if not all([LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        raise HTTPException(
            status_code=500,
            detail="LiveKit credentials not configured"
        )
    
    try:
        # Create LiveKit API client
        lk_api = api.LiveKitAPI(
            LIVEKIT_URL,
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET
        )
        
        # List rooms
        rooms = await lk_api.room.list_rooms()
        
        return {
            "rooms": [
                {
                    "name": room.name,
                    "sid": room.sid,
                    "num_participants": room.num_participants,
                    "creation_time": room.creation_time,
                }
                for room in rooms
            ],
            "total": len(rooms)
        }
    except Exception as e:
        logger.error(f"Error listing rooms: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list rooms: {str(e)}"
        )


# Add these globals after the existing globals
current_agent_process = None
current_room_name = None

# Add these new functions after the globals
def get_counter():
    try:
        with open('counter.txt', 'r') as f:
            return int(f.read().strip())
    except FileNotFoundError:
        with open('counter.txt', 'w') as f:
            f.write('1')
        return 1

def increment_counter():
    counter = get_counter()
    counter += 1
    with open('counter.txt', 'w') as f:
        f.write(str(counter))
    return counter



if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8080))
    logger.info(f"Starting Tavus Avatar token server on port {port}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )

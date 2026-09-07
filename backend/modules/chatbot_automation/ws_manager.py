import asyncio
from typing import Dict, List
from fastapi import WebSocket


class ConnectionManager:
    """
    Dashboard WebSocket connections, keyed by user_id.
    Har business owner apne dashboard se connect hota hai — new conversation
    aur escalation events yahan se broadcast hote hain.
    """

    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(user_id, []).append(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket):
        async with self._lock:
            conns = self._connections.get(user_id, [])
            if websocket in conns:
                conns.remove(websocket)
            if not conns and user_id in self._connections:
                del self._connections[user_id]

    async def send_to_user(self, user_id: str, message: dict):
        conns = list(self._connections.get(user_id, []))
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(user_id, ws)


ws_manager = ConnectionManager()

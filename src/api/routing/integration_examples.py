"""
Integration Examples for Unified Router with ASRHub APIs

This module demonstrates practical integration patterns for using the unified router
with existing HTTP SSE, WebSocket, and Socket.IO server implementations.
"""

import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

from src.api.routing.unified_router import (
    create_unified_router, create_protocol_adapters, 
    Route, RouteCategory, ProtocolType
)


class UnifiedRouterMixin:
    """
    Mixin class providing unified router functionality to existing API servers
    
    Add this mixin to existing server classes to enable unified routing:
    
    class SSEServer(APIBase, UnifiedRouterMixin):
        def __init__(self):
            super().__init__()
            self._init_unified_router()
    """
    
    def _init_unified_router(self):
        """Initialize unified router and adapters"""
        self.unified_router = create_unified_router()
        self.protocol_adapters = create_protocol_adapters(self.unified_router)
        
    def get_adapter(self, protocol: ProtocolType):
        """Get protocol adapter"""
        return self.protocol_adapters[protocol]
    
    def validate_route_params(self, route: Route, params: Dict[str, Any]) -> bool:
        """Validate route parameters"""
        return self.unified_router.validate_route_parameters(route, params)
    
    def get_routes_by_category(self, category: RouteCategory) -> list:
        """Get routes by category"""
        return self.unified_router.get_routes_by_category(category)


# HTTP SSE Integration Examples

class EnhancedSSEServer(UnifiedRouterMixin):
    """Enhanced SSE Server with unified router integration"""
    
    def __init__(self):
        self._init_unified_router()
        self.http_adapter = self.get_adapter(ProtocolType.HTTP_SSE)
        
    def setup_unified_routes(self, app):
        """Setup FastAPI routes using unified router definitions"""
        
        # Get all routes and setup programmatically
        for route in Route:
            definition = self.unified_router.get_route_definition(route)
            
            # Skip routes that don't apply to HTTP SSE
            if not definition.http_sse_path or definition.http_sse_path.startswith("/"):
                continue
                
            if route.name.startswith("SESSION"):
                self._setup_session_routes(app, route, definition)
            elif route.name.startswith("CONTROL"):
                self._setup_control_routes(app, route, definition)
            elif route.name.startswith("AUDIO"):
                self._setup_audio_routes(app, route, definition)
            elif route.name.startswith("EVENTS"):
                self._setup_event_routes(app, route, definition)
    
    def _setup_session_routes(self, app, route: Route, definition):
        """Setup session-related routes"""
        path = definition.http_sse_path
        
        if route == Route.SESSION_CREATE:
            @app.post(path)
            async def create_session_unified(request):
                return await self.handle_unified_session_create(route, request)
                
        elif route == Route.SESSION_GET:
            @app.get(path)
            async def get_session_unified(session_id: str):
                return await self.handle_unified_session_get(route, session_id)
                
        elif route == Route.SESSION_DELETE:
            @app.delete(path)
            async def delete_session_unified(session_id: str):
                return await self.handle_unified_session_delete(route, session_id)
    
    async def handle_unified_session_create(self, route: Route, request):
        """Handle session creation with unified router"""
        try:
            data = await request.json() if request.headers.get("content-type") == "application/json" else {}
            
            # Validate parameters using unified router
            if not self.validate_route_params(route, data):
                return {"error": "Invalid parameters", "required": self.unified_router.get_route_definition(route).parameters}
            
            # Check if this route has associated PyStoreX action
            action_type = self.unified_router.to_pystore_action(route)
            if action_type:
                # Dispatch PyStoreX action
                import uuid
                session_id = data.get("session_id", str(uuid.uuid4()))
                # store.dispatch(sessions_actions.create_session(session_id, data.get("strategy", "batch")))
                
            return {
                "status": "success",
                "route": route.name,
                "action": action_type,
                "session_id": session_id if 'session_id' in locals() else None
            }
            
        except Exception as e:
            return {"error": str(e), "route": route.name}
    
    def build_sse_event_unified(self, route: Route, data: Any, event_id: Optional[str] = None) -> str:
        """Build SSE event using unified router"""
        return self.http_adapter.build_sse_event(route, data, event_id)
    
    async def send_unified_transcript(self, session_id: str, text: str, is_final: bool = True):
        """Send transcript using unified router format"""
        # Build SSE event for transcript
        transcript_data = {
            "text": text,
            "is_final": is_final,
            "confidence": 0.95,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }
        
        sse_event = self.build_sse_event_unified(Route.TRANSCRIPT, transcript_data)
        
        # Send to SSE connection (implementation would depend on your SSE setup)
        # await self._send_sse_event(session_id, sse_event)
        return sse_event


# WebSocket Integration Examples

class EnhancedWebSocketServer(UnifiedRouterMixin):
    """Enhanced WebSocket Server with unified router integration"""
    
    def __init__(self):
        self._init_unified_router()
        self.ws_adapter = self.get_adapter(ProtocolType.WEBSOCKET)
        
    async def handle_unified_message(self, websocket, message):
        """Handle WebSocket message using unified router"""
        try:
            # Parse JSON message
            if isinstance(message, str):
                data = json.loads(message)
            else:
                # Handle binary messages (for audio)
                await self.handle_binary_audio(websocket, message)
                return
            
            # Use unified router to parse message
            route, message_data = self.ws_adapter.parse_message(data)
            
            # Route to appropriate handler based on route category
            definition = self.unified_router.get_route_definition(route)
            
            if definition.category == RouteCategory.CONTROL:
                await self.handle_unified_control(websocket, route, message_data)
            elif definition.category == RouteCategory.AUDIO:
                await self.handle_unified_audio(websocket, route, message_data)
            elif definition.category == RouteCategory.EVENTS:
                await self.handle_unified_events(websocket, route, message_data)
            elif definition.category == RouteCategory.SESSION:
                await self.handle_unified_session(websocket, route, message_data)
            else:
                await self.send_unified_error(websocket, f"Unsupported route category: {definition.category}")
                
        except json.JSONDecodeError:
            await self.send_unified_error(websocket, "Invalid JSON format")
        except ValueError as e:
            await self.send_unified_error(websocket, str(e))
        except Exception as e:
            await self.send_unified_error(websocket, f"Internal error: {str(e)}")
    
    async def handle_unified_control(self, websocket, route: Route, data: Dict[str, Any]):
        """Handle control commands with unified routing"""
        command = data.get("command")
        session_id = data.get("session_id")
        
        # Validate parameters
        params = {"command": command, "session_id": session_id}
        if not self.validate_route_params(route, params):
            await self.send_unified_error(websocket, "Missing required parameters for control command")
            return
        
        # Check for PyStoreX action mapping
        action_type = self.unified_router.to_pystore_action(route)
        
        if command == "start":
            # Handle start command
            if action_type:
                # Dispatch PyStoreX action
                # store.dispatch(sessions_actions.start_listening(session_id))
                pass
            
            # Send success response
            response = self.ws_adapter.build_message(
                Route.CONTROL_COMMAND,
                {"status": "started", "command": command, "session_id": session_id}
            )
            await websocket.send(json.dumps(response))
            
        elif command == "stop":
            # Handle stop command
            response = self.ws_adapter.build_message(
                Route.CONTROL_COMMAND,
                {"status": "stopped", "command": command, "session_id": session_id}
            )
            await websocket.send(json.dumps(response))
            
        else:
            await self.send_unified_error(websocket, f"Unknown control command: {command}")
    
    async def handle_unified_audio(self, websocket, route: Route, data: Dict[str, Any]):
        """Handle audio messages with unified routing"""
        if route == Route.AUDIO_CHUNK:
            session_id = data.get("session_id")
            audio_data = data.get("audio")
            chunk_id = data.get("chunk_id")
            
            # Validate parameters
            if not all([session_id, audio_data is not None]):
                await self.send_unified_error(websocket, "Missing audio data or session_id")
                return
            
            # Process audio chunk
            # Your audio processing logic here
            
            # Send confirmation
            confirmation = self.ws_adapter.build_message(
                Route.AUDIO_RECEIVED,
                {
                    "session_id": session_id,
                    "chunk_id": chunk_id,
                    "size": len(audio_data) if isinstance(audio_data, str) else 0,
                    "timestamp": datetime.now().isoformat()
                }
            )
            await websocket.send(json.dumps(confirmation))
            
        elif route == Route.AUDIO_CONFIG:
            # Handle audio configuration
            session_id = data.get("session_id")
            config = data.get("config", {})
            
            # Process configuration
            # Your config processing logic here
            
            # Send acknowledgment
            ack = self.ws_adapter.build_message(
                Route.AUDIO_CONFIG,
                {"status": "configured", "session_id": session_id}
            )
            await websocket.send(json.dumps(ack))
    
    async def send_unified_transcript(self, websocket, session_id: str, text: str, is_final: bool = True):
        """Send transcript using unified router"""
        transcript_msg = self.ws_adapter.build_message(
            Route.TRANSCRIPT,
            {
                "session_id": session_id,
                "text": text,
                "is_final": is_final,
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat()
            }
        )
        await websocket.send(json.dumps(transcript_msg))
    
    async def send_unified_error(self, websocket, error_message: str):
        """Send error message using unified router"""
        error_msg = self.ws_adapter.build_message(
            Route.ERROR,
            {
                "error": error_message,
                "timestamp": datetime.now().isoformat()
            }
        )
        await websocket.send(json.dumps(error_msg))


# Socket.IO Integration Examples

class EnhancedSocketIOServer(UnifiedRouterMixin):
    """Enhanced Socket.IO Server with unified router integration"""
    
    def __init__(self):
        self._init_unified_router()
        self.sio_adapter = self.get_adapter(ProtocolType.SOCKETIO)
        
        # Setup Socket.IO server
        import socketio
        self.sio = socketio.AsyncServer(
            async_mode='aiohttp',
            cors_allowed_origins='*'
        )
        
        self.setup_unified_handlers()
    
    def setup_unified_handlers(self):
        """Setup Socket.IO event handlers using unified router"""
        
        # Get all event names from unified router
        control_events = self.get_routes_by_category(RouteCategory.CONTROL)
        audio_events = self.get_routes_by_category(RouteCategory.AUDIO)
        event_routes = self.get_routes_by_category(RouteCategory.EVENTS)
        
        # Setup control handlers
        for route in control_events:
            event_name = self.sio_adapter.get_event_name(route)
            self._register_control_handler(event_name, route)
        
        # Setup audio handlers
        for route in audio_events:
            event_name = self.sio_adapter.get_event_name(route)
            self._register_audio_handler(event_name, route)
        
        # Setup event handlers
        for route in event_routes:
            event_name = self.sio_adapter.get_event_name(route)
            if event_name in ["subscribe", "unsubscribe"]:
                self._register_subscription_handler(event_name, route)
    
    def _register_control_handler(self, event_name: str, route: Route):
        """Register control event handler"""
        @self.sio.event(event_name)
        async def control_handler(sid, data):
            await self.handle_unified_control_event(sid, route, data)
    
    def _register_audio_handler(self, event_name: str, route: Route):
        """Register audio event handler"""
        @self.sio.event(event_name)
        async def audio_handler(sid, data):
            await self.handle_unified_audio_event(sid, route, data)
    
    def _register_subscription_handler(self, event_name: str, route: Route):
        """Register subscription event handler"""
        @self.sio.event(event_name)
        async def subscription_handler(sid, data):
            await self.handle_unified_subscription_event(sid, route, data)
    
    async def handle_unified_control_event(self, sid: str, route: Route, data: Dict[str, Any]):
        """Handle control events with unified routing"""
        try:
            # Parse event data using unified router
            parsed_route, parsed_data = self.sio_adapter.parse_event(
                self.sio_adapter.get_event_name(route), 
                data
            )
            
            # Validate parameters
            if not self.validate_route_params(route, data):
                await self.emit_unified_error(sid, "Invalid parameters for control event")
                return
            
            command = data.get("command")
            session_id = data.get("session_id")
            
            # Check for PyStoreX action
            action_type = self.unified_router.to_pystore_action(route)
            if action_type:
                # Dispatch action to store
                # store.dispatch(create_action(action_type, data))
                pass
            
            # Send response
            response_event = self.sio_adapter.get_event_name(Route.CONTROL_COMMAND)
            await self.sio.emit(
                response_event,
                {
                    "status": "success",
                    "command": command,
                    "session_id": session_id,
                    "action": action_type
                },
                to=sid
            )
            
        except Exception as e:
            await self.emit_unified_error(sid, str(e))
    
    async def handle_unified_audio_event(self, sid: str, route: Route, data: Dict[str, Any]):
        """Handle audio events with unified routing"""
        try:
            session_id = data.get("session_id")
            
            if route == Route.AUDIO_CHUNK:
                # Handle audio chunk
                audio_data = data.get("audio")
                chunk_id = data.get("chunk_id")
                
                # Process audio chunk
                # Your audio processing logic here
                
                # Send confirmation
                confirmation_event = self.sio_adapter.get_event_name(Route.AUDIO_RECEIVED)
                await self.sio.emit(
                    confirmation_event,
                    {
                        "session_id": session_id,
                        "chunk_id": chunk_id,
                        "size": len(audio_data) if audio_data else 0,
                        "timestamp": datetime.now().isoformat()
                    },
                    to=sid
                )
                
        except Exception as e:
            await self.emit_unified_error(sid, str(e))
    
    async def broadcast_unified_transcript(self, session_id: str, text: str, is_final: bool = True):
        """Broadcast transcript to session room using unified router"""
        room_name = self.sio_adapter.build_room_name(session_id)
        transcript_event = self.sio_adapter.get_event_name(Route.TRANSCRIPT)
        
        await self.sio.emit(
            transcript_event,
            {
                "session_id": session_id,
                "text": text,
                "is_final": is_final,
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat()
            },
            room=room_name
        )
    
    async def emit_unified_error(self, sid: str, error_message: str):
        """Emit error using unified router"""
        error_event = self.sio_adapter.get_event_name(Route.ERROR)
        await self.sio.emit(
            error_event,
            {
                "error": error_message,
                "timestamp": datetime.now().isoformat()
            },
            to=sid
        )


# PyStoreX Action Integration

class UnifiedActionDispatcher:
    """
    Unified action dispatcher that maps PyStoreX actions to routes
    """
    
    def __init__(self):
        self.router = create_unified_router()
        self.action_handlers = {}
        self.setup_action_handlers()
    
    def setup_action_handlers(self):
        """Setup action handlers based on unified router definitions"""
        
        # Get all routes that have PyStoreX actions
        for route in Route:
            action_type = self.router.to_pystore_action(route)
            if action_type:
                self.action_handlers[action_type] = self.create_handler(route)
    
    def create_handler(self, route: Route):
        """Create action handler for route"""
        async def handler(action_data):
            await self.handle_unified_action(route, action_data)
        return handler
    
    async def handle_unified_action(self, route: Route, action_data: Dict[str, Any]):
        """Handle PyStoreX action using unified route information"""
        definition = self.router.get_route_definition(route)
        payload = action_data.get("payload", {})
        
        print(f"Handling action for route: {route.name}")
        print(f"Category: {definition.category}")
        print(f"Description: {definition.description}")
        print(f"Payload: {payload}")
        
        # Route to appropriate handler based on category
        if definition.category == RouteCategory.SESSION:
            await self.handle_session_action(route, payload)
        elif definition.category == RouteCategory.AUDIO:
            await self.handle_audio_action(route, payload)
        elif definition.category == RouteCategory.TRANSCRIPTION:
            await self.handle_transcription_action(route, payload)
    
    async def handle_session_action(self, route: Route, payload: Dict[str, Any]):
        """Handle session-related actions"""
        session_id = payload.get("session_id")
        
        if route == Route.ACTION_SESSION_CREATE:
            print(f"Creating session: {session_id}")
            # Implement session creation logic
            
        elif route == Route.SESSION_DELETE:
            print(f"Deleting session: {session_id}")
            # Implement session deletion logic
    
    async def handle_audio_action(self, route: Route, payload: Dict[str, Any]):
        """Handle audio-related actions"""
        session_id = payload.get("session_id")
        
        if route == Route.ACTION_SESSION_CHUNK_UPLOAD_START:
            print(f"Starting chunk upload for session: {session_id}")
            # Implement chunk upload start logic
            
        elif route == Route.ACTION_SESSION_CHUNK_UPLOAD_DONE:
            print(f"Chunk upload done for session: {session_id}")
            # Trigger transcription processing
    
    async def handle_transcription_action(self, route: Route, payload: Dict[str, Any]):
        """Handle transcription-related actions"""
        session_id = payload.get("session_id")
        result = payload.get("result")
        
        if route == Route.ACTION_SESSION_TRANSCRIPTION_DONE:
            print(f"Transcription completed for session: {session_id}")
            print(f"Result: {result}")
            # Broadcast result to all connected clients
    
    async def dispatch_action(self, action_type: str, payload: Dict[str, Any]):
        """Dispatch action using unified router"""
        if action_type in self.action_handlers:
            await self.action_handlers[action_type]({"type": action_type, "payload": payload})
        else:
            print(f"No handler found for action: {action_type}")


# Usage Examples

async def demonstrate_integration():
    """Demonstrate unified router integration"""
    
    print("=== Unified Router Integration Examples ===\n")
    
    # 1. HTTP SSE Integration
    print("1. HTTP SSE Integration:")
    sse_server = EnhancedSSEServer()
    
    # Build SSE event
    sse_event = sse_server.build_sse_event_unified(
        Route.TRANSCRIPT,
        {"text": "Hello from unified router", "is_final": True},
        event_id="unified-123"
    )
    print(f"   SSE Event:\n{sse_event}")
    
    # 2. WebSocket Integration
    print("2. WebSocket Integration:")
    ws_server = EnhancedWebSocketServer()
    
    # Simulate message handling
    test_message = {
        "type": "control",
        "data": {"command": "start", "session_id": "test-session"}
    }
    print(f"   Processing message: {test_message}")
    # await ws_server.handle_unified_message(None, json.dumps(test_message))
    
    # 3. Socket.IO Integration
    print("3. Socket.IO Integration:")
    sio_server = EnhancedSocketIOServer()
    
    # Get event names using unified router
    control_event = sio_server.sio_adapter.get_event_name(Route.CONTROL_COMMAND)
    audio_event = sio_server.sio_adapter.get_event_name(Route.AUDIO_CHUNK)
    print(f"   Control event: '{control_event}'")
    print(f"   Audio event: '{audio_event}'")
    
    # 4. PyStoreX Action Integration
    print("4. PyStoreX Action Integration:")
    dispatcher = UnifiedActionDispatcher()
    
    await dispatcher.dispatch_action(
        "[Session] Create",
        {"session_id": "unified-session", "strategy": "batch"}
    )
    
    await dispatcher.dispatch_action(
        "[Session] Transcription Done",
        {
            "session_id": "unified-session",
            "result": {"text": "Unified routing works!", "confidence": 0.95}
        }
    )
    
    print("\n=== Integration Examples Complete ===")


if __name__ == "__main__":
    asyncio.run(demonstrate_integration())
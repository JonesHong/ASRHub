# Unified Routing System for ASRHub

The ASRHub Unified Routing System provides a comprehensive abstraction layer that unifies route handling across HTTP SSE, WebSocket, and Socket.IO protocols. This documentation explains how to use and integrate the unified router with existing API implementations.

## Overview

The unified routing system addresses the challenge of maintaining consistent route handling across multiple protocols while accommodating their unique characteristics. It provides:

- **Centralized Route Definitions**: All routes defined in a single enum with complete metadata
- **Protocol-Specific Adapters**: Convert routes to appropriate formats for each protocol
- **Bidirectional Conversion**: Map from protocol-specific patterns back to unified routes
- **Type Safety**: Comprehensive parameter validation and type checking
- **PyStoreX Integration**: Direct mapping to event-driven architecture actions

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Unified Router Core                      │
├─────────────────────────────────────────────────────────────┤
│  Route Enum + RouteDefinition                              │
│  ┌─────────────┬─────────────┬─────────────┬──────────────┐ │
│  │ HTTP SSE    │ WebSocket   │ Socket.IO   │ PyStoreX     │ │
│  │ Paths       │ Msg Types   │ Events      │ Actions      │ │
│  └─────────────┴─────────────┴─────────────┴──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼──────┐    ┌─────────▼──────┐    ┌─────────▼──────┐
│ HTTP Adapter │    │ WebSocket      │    │ Socket.IO      │
│              │    │ Adapter        │    │ Adapter        │
│ • Path build │    │ • Msg building │    │ • Event names  │
│ • SSE format │    │ • Type lookup  │    │ • Room mgmt    │
│ • Path parse │    │ • Msg parsing  │    │ • Event parse  │
└──────────────┘    └────────────────┘    └────────────────┘
```

## Route Categories

Routes are organized into logical categories:

- **CONTROL**: Session control commands (start, stop, status)
- **SESSION**: Session lifecycle management
- **AUDIO**: Audio processing and upload
- **TRANSCRIPTION**: Speech-to-text operations
- **EVENTS**: Real-time event streaming
- **SYSTEM**: Health checks, ping/pong, errors
- **METADATA**: Configuration and parameters

## Key Components

### 1. Route Enum

The `Route` enum defines all available routes with semantic naming:

```python
from src.api.routing.unified_router import Route

# Session management
Route.SESSION_CREATE
Route.SESSION_GET
Route.SESSION_DELETE

# Control commands
Route.CONTROL_START
Route.CONTROL_STOP
Route.CONTROL_STATUS

# Audio processing
Route.AUDIO_UPLOAD
Route.AUDIO_CHUNK
Route.AUDIO_CONFIG

# PyStoreX actions
Route.ACTION_SESSION_CREATE
Route.ACTION_SESSION_TRANSCRIPTION_DONE
```

### 2. UnifiedRouter Class

Core router providing conversion methods:

```python
from src.api.routing.unified_router import create_unified_router

router = create_unified_router()

# Convert route to protocol-specific format
http_path = router.to_http_sse_path(Route.AUDIO_UPLOAD, {"session_id": "abc123"})
# Result: "/audio/abc123"

ws_type = router.to_websocket_message_type(Route.CONTROL_COMMAND)
# Result: "control"

sio_event = router.to_socketio_event_name(Route.AUDIO_CHUNK)
# Result: "audio_chunk"

action = router.to_pystore_action(Route.ACTION_SESSION_CREATE)
# Result: "[Session] Create"
```

### 3. Protocol Adapters

Specialized adapters for each protocol:

```python
from src.api.routing.unified_router import create_protocol_adapters, ProtocolType

adapters = create_protocol_adapters(router)
http_adapter = adapters[ProtocolType.HTTP_SSE]
ws_adapter = adapters[ProtocolType.WEBSOCKET]
sio_adapter = adapters[ProtocolType.SOCKETIO]
```

## Integration Examples

### HTTP SSE Server Integration

```python
from src.api.routing.unified_router import create_unified_router, create_protocol_adapters, ProtocolType, Route

class SSEServer:
    def __init__(self):
        self.router = create_unified_router()
        self.adapters = create_protocol_adapters(self.router)
        self.http_adapter = self.adapters[ProtocolType.HTTP_SSE]
        
    def setup_routes(self):
        """Setup FastAPI routes using unified router"""
        
        # Session creation endpoint
        session_path = self.http_adapter.build_path(Route.SESSION_CREATE)
        @self.app.post(session_path)
        async def create_session(request: Request):
            # Handle session creation
            pass
            
        # Audio upload endpoint
        audio_path = self.http_adapter.build_path(Route.AUDIO_UPLOAD)
        @self.app.post(audio_path)
        async def upload_audio(session_id: str, request: Request):
            # Handle audio upload
            pass
            
        # Events streaming endpoint
        events_path = self.http_adapter.build_path(Route.EVENTS_STREAM)
        @self.app.get(events_path)
        async def events_stream(session_id: str, request: Request):
            # Handle SSE streaming
            return StreamingResponse(
                self.generate_events(session_id),
                media_type="text/event-stream"
            )
    
    async def generate_events(self, session_id: str):
        """Generate SSE events using unified router"""
        # Send status update
        status_event = self.http_adapter.build_sse_event(
            Route.STATUS_UPDATE,
            {"session_id": session_id, "state": "LISTENING"},
            event_id="123"
        )
        yield status_event
        
        # Send transcript result
        transcript_event = self.http_adapter.build_sse_event(
            Route.TRANSCRIPT,
            {"text": "Hello world", "is_final": True, "confidence": 0.95}
        )
        yield transcript_event
    
    async def dispatch_action(self, request: Request):
        """Handle PyStoreX action dispatch"""
        action_data = await request.json()
        action_type = action_data.get("type")
        
        # Find route from action
        route = self.router.from_pystore_action(action_type)
        if route:
            # Process the action using the unified route
            await self.handle_action(route, action_data)
```

### WebSocket Server Integration

```python
class WebSocketServer:
    def __init__(self):
        self.router = create_unified_router()
        self.adapters = create_protocol_adapters(self.router)
        self.ws_adapter = self.adapters[ProtocolType.WEBSOCKET]
    
    async def handle_message(self, websocket, message):
        """Handle WebSocket message using unified router"""
        try:
            data = json.loads(message)
            
            # Parse message to route
            route, message_data = self.ws_adapter.parse_message(data)
            
            # Handle based on route
            if route == Route.CONTROL_COMMAND:
                await self.handle_control(websocket, message_data)
            elif route == Route.AUDIO_CHUNK:
                await self.handle_audio_chunk(websocket, message_data)
            elif route == Route.ACTION_DISPATCH:
                await self.handle_action(websocket, message_data)
                
        except ValueError as e:
            # Send error using unified router
            error_msg = self.ws_adapter.build_message(
                Route.ERROR,
                {"error": str(e)}
            )
            await websocket.send(json.dumps(error_msg))
    
    async def send_transcript(self, websocket, text, is_final=True):
        """Send transcript using unified router"""
        transcript_msg = self.ws_adapter.build_message(
            Route.TRANSCRIPT,
            {"text": text, "is_final": is_final, "confidence": 0.95}
        )
        await websocket.send(json.dumps(transcript_msg))
    
    async def handle_control(self, websocket, data):
        """Handle control commands"""
        command = data.get("command")
        session_id = data.get("session_id")
        
        # Process command and send response
        response_msg = self.ws_adapter.build_message(
            Route.CONTROL_COMMAND,
            {"status": "success", "command": command}
        )
        await websocket.send(json.dumps(response_msg))
```

### Socket.IO Server Integration

```python
class SocketIOServer:
    def __init__(self):
        self.router = create_unified_router()
        self.adapters = create_protocol_adapters(self.router)
        self.sio_adapter = self.adapters[ProtocolType.SOCKETIO]
        
        # Setup Socket.IO server
        self.sio = socketio.AsyncServer()
        self.register_handlers()
    
    def register_handlers(self):
        """Register Socket.IO event handlers using unified router"""
        
        # Control handler
        control_event = self.sio_adapter.get_event_name(Route.CONTROL_COMMAND)
        @self.sio.event(control_event)
        async def handle_control(sid, data):
            route, parsed_data = self.sio_adapter.parse_event(control_event, data)
            await self.process_control(sid, parsed_data)
        
        # Audio chunk handler
        audio_event = self.sio_adapter.get_event_name(Route.AUDIO_CHUNK)
        @self.sio.event(audio_event)
        async def handle_audio(sid, data):
            route, parsed_data = self.sio_adapter.parse_event(audio_event, data)
            await self.process_audio_chunk(sid, parsed_data)
        
        # Action handler for PyStoreX integration
        action_event = self.sio_adapter.get_event_name(Route.ACTION_DISPATCH)
        @self.sio.event(action_event)
        async def handle_action(sid, data):
            route, parsed_data = self.sio_adapter.parse_event(action_event, data)
            await self.process_action(sid, parsed_data)
    
    async def broadcast_transcript(self, session_id: str, text: str):
        """Broadcast transcript to room"""
        room_name = self.sio_adapter.build_room_name(session_id)
        
        # Use unified router to get event name
        transcript_event = self.sio_adapter.get_event_name(Route.TRANSCRIPT)
        
        await self.sio.emit(
            transcript_event,
            {"text": text, "is_final": True, "confidence": 0.95},
            room=room_name
        )
    
    async def process_action(self, sid, data):
        """Process PyStoreX action"""
        action_type = data.get("type")
        
        # Find route from action type
        route = self.router.from_pystore_action(action_type)
        if route:
            # Dispatch to store and handle response
            store.dispatch(create_action(action_type, data.get("payload", {})))
```

## PyStoreX Integration

The unified router provides direct integration with PyStoreX actions:

```python
# Map route to PyStoreX action
action_type = router.to_pystore_action(Route.ACTION_SESSION_CREATE)
# Result: "[Session] Create"

# Find route from PyStoreX action
route = router.from_pystore_action("[Session] Transcription Done")
# Result: Route.ACTION_SESSION_TRANSCRIPTION_DONE

# Use in event-driven workflows
async def handle_session_events(action_data):
    action_type = action_data.get("type")
    route = router.from_pystore_action(action_type)
    
    if route == Route.ACTION_SESSION_CREATE:
        # Handle session creation
        pass
    elif route == Route.ACTION_SESSION_TRANSCRIPTION_DONE:
        # Handle transcription completion
        result = action_data.get("payload", {}).get("result")
        await broadcast_result(result)
```

## Route Parameter Validation

```python
# Validate parameters before processing
params = {"session_id": "abc123", "chunk_id": 5}
is_valid = router.validate_route_parameters(Route.AUDIO_CHUNK, params)

if is_valid:
    # Process the request
    pass
else:
    # Return parameter validation error
    pass

# Get required parameters for a route
definition = router.get_route_definition(Route.AUDIO_CHUNK)
required_params = definition.parameters
# Result: ["session_id", "chunk_id"]
```

## Error Handling

```python
# Consistent error handling across protocols
async def handle_error(protocol_adapter, error_message, connection_info):
    try:
        if isinstance(protocol_adapter, HTTPSSEAdapter):
            error_event = protocol_adapter.build_sse_event(
                Route.ERROR,
                {"error": error_message}
            )
            # Send SSE error event
            
        elif isinstance(protocol_adapter, WebSocketAdapter):
            error_msg = protocol_adapter.build_message(
                Route.ERROR,
                {"error": error_message}
            )
            # Send WebSocket error message
            
        elif isinstance(protocol_adapter, SocketIOAdapter):
            error_event = protocol_adapter.get_event_name(Route.ERROR)
            # Emit Socket.IO error event
            
    except Exception as e:
        logger.error(f"Error handling failed: {e}")
```

## Best Practices

### 1. Route Selection

- Use specific routes when possible (e.g., `Route.CONTROL_START` vs `Route.CONTROL_COMMAND`)
- Reserve general routes for protocol adapters that need to handle multiple sub-commands
- Use PyStoreX action routes for event-driven architecture integration

### 2. Parameter Handling

- Always validate parameters using `validate_route_parameters()`
- Use the `parameters` field from route definitions to know what's required
- Handle parameter extraction consistently across protocols

### 3. Error Management

- Use unified error handling through the `Route.ERROR` route
- Provide meaningful error messages that help with debugging
- Log errors with sufficient context for troubleshooting

### 4. Performance Considerations

- Cache protocol adapters to avoid recreation overhead
- Use route categories to group related functionality
- Validate routes at startup to catch configuration issues early

### 5. Protocol-Specific Optimizations

- **HTTP SSE**: Use SSE event formatting for proper client handling
- **WebSocket**: Leverage message type consistency for client libraries
- **Socket.IO**: Utilize room management for session-based broadcasting

## Migration Guide

To migrate existing API implementations to use the unified router:

### 1. Replace Hard-coded Paths/Events

**Before:**
```python
@app.post("/audio/{session_id}")
async def upload_audio(session_id: str):
    pass

await websocket.send(json.dumps({"type": "audio_received"}))

await sio.emit("final_result", data, room=f"session_{session_id}")
```

**After:**
```python
audio_path = router.to_http_sse_path(Route.AUDIO_UPLOAD)
@app.post(audio_path)
async def upload_audio(session_id: str):
    pass

msg = ws_adapter.build_message(Route.AUDIO_RECEIVED, data)
await websocket.send(json.dumps(msg))

event_name = sio_adapter.get_event_name(Route.TRANSCRIPT)
room_name = sio_adapter.build_room_name(session_id)
await sio.emit(event_name, data, room=room_name)
```

### 2. Unify Message Parsing

**Before:**
```python
# Different parsing logic for each protocol
if message.get("type") == "control":
    # Handle control
elif message.get("type") == "audio_chunk":
    # Handle audio
```

**After:**
```python
# Unified parsing
route, data = ws_adapter.parse_message(message)
if route == Route.CONTROL_COMMAND:
    # Handle control
elif route == Route.AUDIO_CHUNK:
    # Handle audio
```

### 3. Integrate PyStoreX Actions

**Before:**
```python
# Manual action type handling
if action_type == "[Session] Create":
    # Handle creation
elif action_type == "[Session] Transcription Done":
    # Handle completion
```

**After:**
```python
# Route-based action handling
route = router.from_pystore_action(action_type)
if route == Route.ACTION_SESSION_CREATE:
    # Handle creation
elif route == Route.ACTION_SESSION_TRANSCRIPTION_DONE:
    # Handle completion
```

## Testing

The unified router includes comprehensive test coverage. Run tests with:

```bash
python test_unified_routing.py
```

The test suite validates:
- Route conversions across all protocols
- Reverse lookup functionality
- Parameter validation
- Protocol adapter behavior
- PyStoreX action integration
- Error handling scenarios

## Extension Points

To add new routes or protocols:

### 1. Adding New Routes

Add to the `Route` enum and update `_build_route_definitions()`:

```python
class Route(Enum):
    # ... existing routes ...
    NEW_FEATURE = auto()

# In _build_route_definitions():
Route.NEW_FEATURE: RouteDefinition(
    name="new_feature",
    category=RouteCategory.CUSTOM,
    description="Description of new feature",
    parameters=["param1", "param2"],
    http_sse_path="/new/feature/{param1}",
    websocket_message_type="new_feature",
    socketio_event_name="new_feature",
    pystore_action="[Custom] New Feature",  # Optional
    requires_session=True
)
```

### 2. Adding New Protocols

Create a new adapter class:

```python
class NewProtocolAdapter:
    def __init__(self, router: UnifiedRouter):
        self.router = router
    
    def build_message(self, route: Route, data: Any) -> Any:
        # Convert route to protocol-specific format
        pass
    
    def parse_message(self, message: Any) -> Tuple[Route, Any]:
        # Parse protocol message to route
        pass
```

Add to `create_protocol_adapters()`:

```python
def create_protocol_adapters(router: UnifiedRouter) -> Dict[ProtocolType, Any]:
    return {
        # ... existing adapters ...
        ProtocolType.NEW_PROTOCOL: NewProtocolAdapter(router)
    }
```

## Conclusion

The Unified Routing System provides a robust foundation for handling multiple protocols in the ASRHub project. It offers:

- **Consistency**: Unified route handling across all protocols
- **Maintainability**: Centralized route definitions reduce duplication
- **Extensibility**: Easy to add new routes or protocols
- **Type Safety**: Comprehensive validation and error handling
- **Integration**: Direct PyStoreX action mapping for event-driven architecture

By using the unified router, you can ensure consistent behavior across all API protocols while maintaining the flexibility to leverage protocol-specific features when needed.
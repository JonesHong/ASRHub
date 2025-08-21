"""
Unified Router System for ASRHub API Protocols

This module provides a comprehensive routing abstraction that unifies route handling
across HTTP SSE, WebSocket, and Socket.IO protocols. It defines all routes in a single
enum and provides conversion methods for each protocol format.

Architecture:
- Route definitions centralized in Route enum
- Protocol-specific adapters for path/event name conversion
- Type-safe route parameter handling
- Comprehensive test examples included

Protocol Patterns Analyzed:
- HTTP SSE: REST-style paths ("/session", "/audio/{session_id}")
- WebSocket: Message types ("action", "audio_chunk", "control")
- Socket.IO: Event names ("control", "audio_chunk", "action")
"""

import re
from enum import Enum, auto
from typing import Dict, Any, Optional, Union, List, Tuple
from dataclasses import dataclass


class RouteCategory(Enum):
    """Route categories for logical grouping"""
    CONTROL = "control"
    SESSION = "session"
    AUDIO = "audio"
    TRANSCRIPTION = "transcription"
    METADATA = "metadata"
    SYSTEM = "system"
    EVENTS = "events"


class ProtocolType(Enum):
    """Supported protocol types"""
    HTTP_SSE = "http_sse"
    WEBSOCKET = "websocket"
    SOCKETIO = "socketio"


@dataclass
class RouteDefinition:
    """Complete route definition with metadata"""
    name: str
    category: RouteCategory
    description: str
    parameters: List[str]
    http_sse_path: str
    websocket_message_type: str
    socketio_event_name: str
    pystore_action: Optional[str] = None
    requires_session: bool = True
    is_bidirectional: bool = False


class Route(Enum):
    """
    Comprehensive route definitions for all ASRHub API protocols
    
    Each route includes:
    - Unique identifier
    - Protocol-specific patterns
    - Parameter requirements
    - Associated PyStoreX actions (where applicable)
    """
    
    # System & Health Routes
    ROOT = auto()
    HEALTH_CHECK = auto()
    
    # Session Management Routes
    SESSION_CREATE = auto()
    SESSION_GET = auto()
    SESSION_DELETE = auto()
    SESSION_LIST = auto()
    
    # Control Commands
    CONTROL_COMMAND = auto()
    CONTROL_START = auto()
    CONTROL_STOP = auto()
    CONTROL_STATUS = auto()
    CONTROL_BUSY_START = auto()
    CONTROL_BUSY_END = auto()
    
    # Wake Word Management
    WAKE_COMMAND = auto()
    WAKE_SET_TIMEOUT = auto()
    WAKE_GET_STATUS = auto()
    WAKE_SLEEP = auto()
    
    # Audio Processing
    AUDIO_UPLOAD = auto()
    AUDIO_CONFIG = auto()
    AUDIO_CHUNK = auto()
    AUDIO_STREAM_START = auto()
    AUDIO_STREAM_STOP = auto()
    
    # Transcription
    TRANSCRIBE_SYNC = auto()
    TRANSCRIBE_ASYNC = auto()
    TRANSCRIBE_STREAM = auto()
    TRANSCRIBE_V1 = auto()
    
    # PyStoreX Actions (Event-Driven Architecture)
    ACTION_DISPATCH = auto()
    ACTION_SESSION_CREATE = auto()
    ACTION_SESSION_DESTROY = auto()
    ACTION_SESSION_START_LISTENING = auto()
    ACTION_SESSION_UPLOAD_FILE = auto()
    ACTION_SESSION_UPLOAD_FILE_DONE = auto()
    ACTION_SESSION_CHUNK_UPLOAD_START = auto()
    ACTION_SESSION_CHUNK_UPLOAD_DONE = auto()
    ACTION_SESSION_START_RECORDING = auto()
    ACTION_SESSION_END_RECORDING = auto()
    ACTION_SESSION_BEGIN_TRANSCRIPTION = auto()
    ACTION_SESSION_AUDIO_CHUNK_RECEIVED = auto()
    ACTION_SESSION_TRANSCRIPTION_DONE = auto()
    
    # Event Streaming
    EVENTS_STREAM = auto()
    EVENTS_SUBSCRIBE = auto()
    EVENTS_UNSUBSCRIBE = auto()
    
    # Real-time Communication
    PING = auto()
    PONG = auto()
    HEARTBEAT = auto()
    WELCOME = auto()
    CONNECTED = auto()
    DISCONNECTED = auto()
    
    # Error Handling & Status
    ERROR = auto()
    STATUS_UPDATE = auto()
    PROGRESS_UPDATE = auto()
    BACKPRESSURE = auto()
    
    # Protocol-Specific Events
    AUDIO_RECEIVED = auto()
    PARTIAL_RESULT = auto()
    FINAL_RESULT = auto()
    TRANSCRIPT = auto()


class UnifiedRouter:
    """
    Unified routing system that provides consistent route mapping across all protocols
    
    Features:
    - Protocol-agnostic route definitions
    - Type-safe parameter extraction
    - Bidirectional route conversion
    - Comprehensive validation
    """
    
    def __init__(self):
        """Initialize the unified router with complete route definitions"""
        self._route_definitions = self._build_route_definitions()
        self._http_path_cache = {}
        self._websocket_type_cache = {}
        self._socketio_event_cache = {}
        
    def _build_route_definitions(self) -> Dict[Route, RouteDefinition]:
        """Build comprehensive route definitions for all protocols"""
        return {
            # System & Health Routes
            Route.ROOT: RouteDefinition(
                name="root",
                category=RouteCategory.SYSTEM,
                description="API root endpoint with service information",
                parameters=[],
                http_sse_path="/",
                websocket_message_type="system_info",
                socketio_event_name="system_info",
                requires_session=False
            ),
            
            Route.HEALTH_CHECK: RouteDefinition(
                name="health_check",
                category=RouteCategory.SYSTEM,
                description="Health check endpoint",
                parameters=[],
                http_sse_path="/health",
                websocket_message_type="health_check",
                socketio_event_name="health",
                requires_session=False
            ),
            
            # Session Management Routes
            Route.SESSION_CREATE: RouteDefinition(
                name="session_create",
                category=RouteCategory.SESSION,
                description="Create a new session",
                parameters=[],
                http_sse_path="/session",
                websocket_message_type="session_create",
                socketio_event_name="session_create",
                pystore_action="[Session] Create",
                requires_session=False
            ),
            
            Route.SESSION_GET: RouteDefinition(
                name="session_get",
                category=RouteCategory.SESSION,
                description="Get session information",
                parameters=["session_id"],
                http_sse_path="/session/{session_id}",
                websocket_message_type="session_get",
                socketio_event_name="session_get",
                requires_session=True
            ),
            
            Route.SESSION_DELETE: RouteDefinition(
                name="session_delete",
                category=RouteCategory.SESSION,
                description="Delete a session",
                parameters=["session_id"],
                http_sse_path="/session/{session_id}",  # DELETE method
                websocket_message_type="session_delete",
                socketio_event_name="session_delete",
                pystore_action="[Session] Destroy",
                requires_session=True
            ),
            
            # Control Commands
            Route.CONTROL_COMMAND: RouteDefinition(
                name="control_command",
                category=RouteCategory.CONTROL,
                description="General control command endpoint",
                parameters=["command", "session_id"],
                http_sse_path="/control",
                websocket_message_type="control",
                socketio_event_name="control",
                requires_session=True,
                is_bidirectional=True
            ),
            
            Route.CONTROL_START: RouteDefinition(
                name="control_start",
                category=RouteCategory.CONTROL,
                description="Start listening/recording",
                parameters=["session_id"],
                http_sse_path="/control",  # POST with command=start
                websocket_message_type="control",
                socketio_event_name="control",
                pystore_action="[Session] Start Listening",
                requires_session=True
            ),
            
            Route.CONTROL_STOP: RouteDefinition(
                name="control_stop",
                category=RouteCategory.CONTROL,
                description="Stop listening/recording",
                parameters=["session_id"],
                http_sse_path="/control",  # POST with command=stop
                websocket_message_type="control",
                socketio_event_name="control",
                requires_session=True
            ),
            
            Route.CONTROL_STATUS: RouteDefinition(
                name="control_status",
                category=RouteCategory.CONTROL,
                description="Get session status",
                parameters=["session_id"],
                http_sse_path="/control",  # POST with command=status
                websocket_message_type="control",
                socketio_event_name="control",
                requires_session=True
            ),
            
            # Wake Word Management
            Route.WAKE_COMMAND: RouteDefinition(
                name="wake_command",
                category=RouteCategory.CONTROL,
                description="Wake word activation",
                parameters=["session_id", "source"],
                http_sse_path="/control",  # POST with command=wake
                websocket_message_type="control",
                socketio_event_name="control",
                requires_session=True
            ),
            
            # Audio Processing
            Route.AUDIO_UPLOAD: RouteDefinition(
                name="audio_upload",
                category=RouteCategory.AUDIO,
                description="Upload audio file or chunk",
                parameters=["session_id"],
                http_sse_path="/audio/{session_id}",
                websocket_message_type="audio",
                socketio_event_name="audio_upload",
                requires_session=True
            ),
            
            Route.AUDIO_CONFIG: RouteDefinition(
                name="audio_config",
                category=RouteCategory.AUDIO,
                description="Configure audio parameters",
                parameters=["session_id"],
                http_sse_path="/audio/{session_id}/config",
                websocket_message_type="audio_config",
                socketio_event_name="audio_config",
                requires_session=True
            ),
            
            Route.AUDIO_CHUNK: RouteDefinition(
                name="audio_chunk",
                category=RouteCategory.AUDIO,
                description="Process audio chunk",
                parameters=["session_id", "chunk_id"],
                http_sse_path="/audio/{session_id}/chunk",
                websocket_message_type="audio_chunk",
                socketio_event_name="audio_chunk",
                pystore_action="[Session] Audio Chunk Received",
                requires_session=True
            ),
            
            # Transcription
            Route.TRANSCRIBE_SYNC: RouteDefinition(
                name="transcribe_sync",
                category=RouteCategory.TRANSCRIPTION,
                description="Synchronous transcription",
                parameters=["session_id"],
                http_sse_path="/transcribe/{session_id}",
                websocket_message_type="transcribe",
                socketio_event_name="transcribe",
                requires_session=True
            ),
            
            Route.TRANSCRIBE_V1: RouteDefinition(
                name="transcribe_v1",
                category=RouteCategory.TRANSCRIPTION,
                description="V1 transcription API endpoint",
                parameters=[],
                http_sse_path="/v1/transcribe",
                websocket_message_type="transcribe_v1",
                socketio_event_name="transcribe_v1",
                requires_session=False
            ),
            
            # PyStoreX Actions
            Route.ACTION_DISPATCH: RouteDefinition(
                name="action_dispatch",
                category=RouteCategory.EVENTS,
                description="Dispatch PyStoreX action",
                parameters=["action_type"],
                http_sse_path="/action",
                websocket_message_type="action",
                socketio_event_name="action",
                requires_session=False,
                is_bidirectional=True
            ),
            
            Route.ACTION_SESSION_CREATE: RouteDefinition(
                name="action_session_create",
                category=RouteCategory.EVENTS,
                description="Session creation action",
                parameters=["session_id", "strategy"],
                http_sse_path="/action",  # POST with action type
                websocket_message_type="action",
                socketio_event_name="action",
                pystore_action="[Session] Create",
                requires_session=False
            ),
            
            Route.ACTION_SESSION_CHUNK_UPLOAD_START: RouteDefinition(
                name="action_session_chunk_upload_start",
                category=RouteCategory.EVENTS,
                description="Start chunk upload action",
                parameters=["session_id"],
                http_sse_path="/action",
                websocket_message_type="action",
                socketio_event_name="action",
                pystore_action="[Session] Chunk Upload Start",
                requires_session=True
            ),
            
            Route.ACTION_SESSION_CHUNK_UPLOAD_DONE: RouteDefinition(
                name="action_session_chunk_upload_done",
                category=RouteCategory.EVENTS,
                description="Complete chunk upload action",
                parameters=["session_id"],
                http_sse_path="/action",
                websocket_message_type="action",
                socketio_event_name="action",
                pystore_action="[Session] Chunk Upload Done",
                requires_session=True
            ),
            
            Route.ACTION_SESSION_TRANSCRIPTION_DONE: RouteDefinition(
                name="action_session_transcription_done",
                category=RouteCategory.EVENTS,
                description="Transcription completion action",
                parameters=["session_id", "result"],
                http_sse_path="/action",
                websocket_message_type="action",
                socketio_event_name="action",
                pystore_action="[Session] Transcription Done",
                requires_session=True
            ),
            
            # Event Streaming
            Route.EVENTS_STREAM: RouteDefinition(
                name="events_stream",
                category=RouteCategory.EVENTS,
                description="SSE event stream",
                parameters=["session_id"],
                http_sse_path="/events/{session_id}",
                websocket_message_type="events",
                socketio_event_name="subscribe",
                requires_session=True,
                is_bidirectional=True
            ),
            
            Route.EVENTS_SUBSCRIBE: RouteDefinition(
                name="events_subscribe",
                category=RouteCategory.EVENTS,
                description="Subscribe to session events",
                parameters=["session_id"],
                http_sse_path="/events/{session_id}/subscribe",
                websocket_message_type="subscribe",
                socketio_event_name="subscribe",
                requires_session=True
            ),
            
            Route.EVENTS_UNSUBSCRIBE: RouteDefinition(
                name="events_unsubscribe",
                category=RouteCategory.EVENTS,
                description="Unsubscribe from session events",
                parameters=["session_id"],
                http_sse_path="/events/{session_id}/unsubscribe",
                websocket_message_type="unsubscribe",
                socketio_event_name="unsubscribe",
                requires_session=True
            ),
            
            # Real-time Communication
            Route.PING: RouteDefinition(
                name="ping",
                category=RouteCategory.SYSTEM,
                description="Ping for connection health",
                parameters=[],
                http_sse_path="/ping",
                websocket_message_type="ping",
                socketio_event_name="ping",
                requires_session=False
            ),
            
            Route.PONG: RouteDefinition(
                name="pong",
                category=RouteCategory.SYSTEM,
                description="Pong response",
                parameters=[],
                http_sse_path="/pong",
                websocket_message_type="pong",
                socketio_event_name="pong",
                requires_session=False
            ),
            
            Route.WELCOME: RouteDefinition(
                name="welcome",
                category=RouteCategory.SYSTEM,
                description="Welcome message on connection",
                parameters=["connection_id"],
                http_sse_path="/welcome",
                websocket_message_type="welcome",
                socketio_event_name="welcome",
                requires_session=False
            ),
            
            # Status & Error Handling
            Route.ERROR: RouteDefinition(
                name="error",
                category=RouteCategory.SYSTEM,
                description="Error message",
                parameters=["error_message"],
                http_sse_path="/error",
                websocket_message_type="error",
                socketio_event_name="error",
                requires_session=False,
                is_bidirectional=True
            ),
            
            Route.STATUS_UPDATE: RouteDefinition(
                name="status_update",
                category=RouteCategory.EVENTS,
                description="Session status update",
                parameters=["session_id", "state"],
                http_sse_path="/status/{session_id}",
                websocket_message_type="status_update",
                socketio_event_name="status_update",
                requires_session=True,
                is_bidirectional=True
            ),
            
            Route.AUDIO_RECEIVED: RouteDefinition(
                name="audio_received",
                category=RouteCategory.AUDIO,
                description="Audio chunk received confirmation",
                parameters=["size", "chunk_id"],
                http_sse_path="/audio/received",
                websocket_message_type="audio_received",
                socketio_event_name="audio_received",
                requires_session=True,
                is_bidirectional=True
            ),
            
            Route.TRANSCRIPT: RouteDefinition(
                name="transcript",
                category=RouteCategory.TRANSCRIPTION,
                description="Transcription result",
                parameters=["text", "is_final", "confidence"],
                http_sse_path="/transcript",
                websocket_message_type="transcript",
                socketio_event_name="final_result",
                requires_session=True,
                is_bidirectional=True
            ),
        }
    
    # Protocol-Specific Conversion Methods
    
    def to_http_sse_path(self, route: Route, params: Optional[Dict[str, Any]] = None) -> str:
        """
        Convert route to HTTP SSE path
        
        Args:
            route: Route enum value
            params: URL parameters for path substitution
            
        Returns:
            HTTP path string
            
        Example:
            >>> router.to_http_sse_path(Route.AUDIO_UPLOAD, {"session_id": "abc123"})
            "/audio/abc123"
        """
        if route not in self._route_definitions:
            raise ValueError(f"Unknown route: {route}")
            
        definition = self._route_definitions[route]
        path = definition.http_sse_path
        
        if params:
            for key, value in params.items():
                path = path.replace(f"{{{key}}}", str(value))
                
        return path
    
    def to_websocket_message_type(self, route: Route) -> str:
        """
        Convert route to WebSocket message type
        
        Args:
            route: Route enum value
            
        Returns:
            WebSocket message type string
            
        Example:
            >>> router.to_websocket_message_type(Route.AUDIO_CHUNK)
            "audio_chunk"
        """
        if route not in self._route_definitions:
            raise ValueError(f"Unknown route: {route}")
            
        return self._route_definitions[route].websocket_message_type
    
    def to_socketio_event_name(self, route: Route) -> str:
        """
        Convert route to Socket.IO event name
        
        Args:
            route: Route enum value
            
        Returns:
            Socket.IO event name string
            
        Example:
            >>> router.to_socketio_event_name(Route.CONTROL_COMMAND)
            "control"
        """
        if route not in self._route_definitions:
            raise ValueError(f"Unknown route: {route}")
            
        return self._route_definitions[route].socketio_event_name
    
    def to_pystore_action(self, route: Route) -> Optional[str]:
        """
        Get PyStoreX action name for route
        
        Args:
            route: Route enum value
            
        Returns:
            PyStoreX action name or None if not applicable
            
        Example:
            >>> router.to_pystore_action(Route.ACTION_SESSION_CREATE)
            "[Session] Create"
        """
        if route not in self._route_definitions:
            raise ValueError(f"Unknown route: {route}")
            
        return self._route_definitions[route].pystore_action
    
    # Reverse Lookup Methods
    
    def from_http_sse_path(self, path: str, method: str = "GET") -> Tuple[Route, Dict[str, str]]:
        """
        Find route and extract parameters from HTTP SSE path
        
        Args:
            path: HTTP path
            method: HTTP method
            
        Returns:
            Tuple of (Route, extracted_parameters)
            
        Example:
            >>> router.from_http_sse_path("/audio/abc123", "POST")
            (Route.AUDIO_UPLOAD, {"session_id": "abc123"})
        """
        for route, definition in self._route_definitions.items():
            params = self._match_path_pattern(path, definition.http_sse_path)
            if params is not None:
                return route, params
                
        raise ValueError(f"No route found for path: {path}")
    
    def from_websocket_message_type(self, message_type: str) -> Route:
        """
        Find route from WebSocket message type
        
        Note: Returns the most general route when multiple routes share the same message type.
        This is expected behavior since protocols like WebSocket use the same message type 
        for different sub-commands (e.g., "control" for start/stop/status).
        
        Args:
            message_type: WebSocket message type
            
        Returns:
            Matching Route enum value (most general)
            
        Example:
            >>> router.from_websocket_message_type("audio_chunk")
            Route.AUDIO_CHUNK
            >>> router.from_websocket_message_type("control")
            Route.CONTROL_COMMAND
        """
        # Return the most general route for common message types
        for route, definition in self._route_definitions.items():
            if definition.websocket_message_type == message_type:
                return route
                
        raise ValueError(f"No route found for WebSocket message type: {message_type}")
    
    def from_socketio_event_name(self, event_name: str) -> Route:
        """
        Find route from Socket.IO event name
        
        Note: Returns the most general route when multiple routes share the same event name.
        This is expected behavior since protocols like Socket.IO use the same event name 
        for different sub-commands (e.g., "control" for start/stop/status).
        
        Args:
            event_name: Socket.IO event name
            
        Returns:
            Matching Route enum value (most general)
            
        Example:
            >>> router.from_socketio_event_name("control")
            Route.CONTROL_COMMAND
            >>> router.from_socketio_event_name("audio_chunk")
            Route.AUDIO_CHUNK
        """
        # Return the most general route for common event names
        for route, definition in self._route_definitions.items():
            if definition.socketio_event_name == event_name:
                return route
                
        raise ValueError(f"No route found for Socket.IO event: {event_name}")
    
    def from_pystore_action(self, action_type: str) -> Optional[Route]:
        """
        Find route from PyStoreX action type
        
        Args:
            action_type: PyStoreX action type
            
        Returns:
            Matching Route enum value or None
            
        Example:
            >>> router.from_pystore_action("[Session] Create")
            Route.ACTION_SESSION_CREATE
        """
        for route, definition in self._route_definitions.items():
            if definition.pystore_action == action_type:
                return route
                
        return None
    
    # Utility Methods
    
    def get_route_definition(self, route: Route) -> RouteDefinition:
        """Get complete route definition"""
        if route not in self._route_definitions:
            raise ValueError(f"Unknown route: {route}")
        return self._route_definitions[route]
    
    def get_routes_by_category(self, category: RouteCategory) -> List[Route]:
        """Get all routes in a specific category"""
        return [
            route for route, definition in self._route_definitions.items()
            if definition.category == category
        ]
    
    def get_bidirectional_routes(self) -> List[Route]:
        """Get all bidirectional routes (can send and receive)"""
        return [
            route for route, definition in self._route_definitions.items()
            if definition.is_bidirectional
        ]
    
    def validate_route_parameters(self, route: Route, params: Dict[str, Any]) -> bool:
        """
        Validate that all required parameters are provided for a route
        
        Args:
            route: Route enum value
            params: Parameters to validate
            
        Returns:
            True if all required parameters are present
        """
        if route not in self._route_definitions:
            return False
            
        definition = self._route_definitions[route]
        required_params = set(definition.parameters)
        provided_params = set(params.keys())
        
        return required_params.issubset(provided_params)
    
    def _match_path_pattern(self, path: str, pattern: str) -> Optional[Dict[str, str]]:
        """
        Match a path against a pattern and extract parameters
        
        Args:
            path: Actual path
            pattern: Pattern with {param} placeholders
            
        Returns:
            Dictionary of extracted parameters or None if no match
        """
        # Convert pattern to regex
        regex_pattern = pattern
        param_names = []
        
        # Find all parameter placeholders
        import re
        for match in re.finditer(r'\{(\w+)\}', pattern):
            param_name = match.group(1)
            param_names.append(param_name)
            # Replace with named capture group
            regex_pattern = regex_pattern.replace(
                f"{{{param_name}}}", 
                f"(?P<{param_name}>[^/]+)"
            )
        
        # Escape other regex characters
        regex_pattern = regex_pattern.replace("/", r"\/")
        regex_pattern = f"^{regex_pattern}$"
        
        match = re.match(regex_pattern, path)
        if match:
            return match.groupdict()
        
        return None


# Protocol-Specific Adapters

class HTTPSSEAdapter:
    """HTTP SSE protocol adapter"""
    
    def __init__(self, router: UnifiedRouter):
        self.router = router
    
    def build_path(self, route: Route, **params) -> str:
        """Build HTTP path with parameters"""
        return self.router.to_http_sse_path(route, params)
    
    def parse_path(self, path: str, method: str = "GET") -> Tuple[Route, Dict[str, str]]:
        """Parse HTTP path to route and parameters"""
        return self.router.from_http_sse_path(path, method)
    
    def build_sse_event(self, route: Route, data: Any, event_id: Optional[str] = None) -> str:
        """
        Build SSE event format
        
        Args:
            route: Route for event type
            data: Event data
            event_id: Optional event ID
            
        Returns:
            SSE formatted string
        """
        lines = []
        
        # Event type
        event_type = self.router.get_route_definition(route).name
        lines.append(f"event: {event_type}")
        
        # Event ID
        if event_id:
            lines.append(f"id: {event_id}")
        
        # Data
        import json
        data_str = json.dumps(data, ensure_ascii=False)
        for line in data_str.split('\n'):
            lines.append(f"data: {line}")
        
        return '\n'.join(lines) + '\n\n'


class WebSocketAdapter:
    """WebSocket protocol adapter"""
    
    def __init__(self, router: UnifiedRouter):
        self.router = router
    
    def build_message(self, route: Route, data: Any = None, **params) -> Dict[str, Any]:
        """
        Build WebSocket message
        
        Args:
            route: Route for message type
            data: Message data
            **params: Additional parameters
            
        Returns:
            WebSocket message dictionary
        """
        message = {
            "type": self.router.to_websocket_message_type(route)
        }
        
        if data is not None:
            message["data"] = data
            
        if params:
            message.update(params)
            
        return message
    
    def parse_message(self, message: Dict[str, Any]) -> Tuple[Route, Any]:
        """
        Parse WebSocket message to route and data
        
        Args:
            message: WebSocket message dictionary
            
        Returns:
            Tuple of (Route, data)
        """
        message_type = message.get("type")
        if not message_type:
            raise ValueError("Message missing 'type' field")
            
        route = self.router.from_websocket_message_type(message_type)
        data = message.get("data")
        
        return route, data


class SocketIOAdapter:
    """Socket.IO protocol adapter"""
    
    def __init__(self, router: UnifiedRouter):
        self.router = router
    
    def get_event_name(self, route: Route) -> str:
        """Get Socket.IO event name for route"""
        return self.router.to_socketio_event_name(route)
    
    def parse_event(self, event_name: str, data: Any) -> Tuple[Route, Any]:
        """
        Parse Socket.IO event to route and data
        
        Args:
            event_name: Socket.IO event name
            data: Event data
            
        Returns:
            Tuple of (Route, data)
        """
        route = self.router.from_socketio_event_name(event_name)
        return route, data
    
    def build_room_name(self, session_id: str) -> str:
        """Build Socket.IO room name for session"""
        return f"session_{session_id}"


# Factory Functions

def create_unified_router() -> UnifiedRouter:
    """Factory function to create a configured unified router"""
    return UnifiedRouter()


def create_protocol_adapters(router: UnifiedRouter) -> Dict[ProtocolType, Any]:
    """
    Factory function to create all protocol adapters
    
    Args:
        router: Unified router instance
        
    Returns:
        Dictionary mapping protocol types to their adapters
    """
    return {
        ProtocolType.HTTP_SSE: HTTPSSEAdapter(router),
        ProtocolType.WEBSOCKET: WebSocketAdapter(router),
        ProtocolType.SOCKETIO: SocketIOAdapter(router)
    }


# Example Usage and Tests

def demonstrate_usage():
    """
    Comprehensive examples showing how to use the unified routing system
    """
    print("=== ASRHub Unified Router Usage Examples ===\n")
    
    # Initialize router and adapters
    router = create_unified_router()
    adapters = create_protocol_adapters(router)
    
    http_adapter = adapters[ProtocolType.HTTP_SSE]
    ws_adapter = adapters[ProtocolType.WEBSOCKET]
    sio_adapter = adapters[ProtocolType.SOCKETIO]
    
    print("1. HTTP SSE Examples:")
    print("   Session creation:")
    session_path = http_adapter.build_path(Route.SESSION_CREATE)
    print(f"   Path: POST {session_path}")
    
    print("   Audio upload:")
    audio_path = http_adapter.build_path(Route.AUDIO_UPLOAD, session_id="abc123")
    print(f"   Path: POST {audio_path}")
    
    print("   Events stream:")
    events_path = http_adapter.build_path(Route.EVENTS_STREAM, session_id="abc123")
    print(f"   Path: GET {events_path}")
    
    # SSE event example
    sse_event = http_adapter.build_sse_event(
        Route.TRANSCRIPT,
        {"text": "Hello world", "is_final": True, "confidence": 0.95},
        event_id="12345"
    )
    print(f"   SSE Event:\n{sse_event}")
    
    print("\n2. WebSocket Examples:")
    
    # Control message
    control_msg = ws_adapter.build_message(
        Route.CONTROL_COMMAND,
        {"command": "start", "session_id": "abc123"}
    )
    print(f"   Control message: {control_msg}")
    
    # Audio chunk message
    audio_msg = ws_adapter.build_message(
        Route.AUDIO_CHUNK,
        {"audio": "base64data", "chunk_id": 1},
        session_id="abc123"
    )
    print(f"   Audio chunk: {audio_msg}")
    
    # Action message (PyStoreX)
    action_msg = ws_adapter.build_message(
        Route.ACTION_DISPATCH,
        {"type": "[Session] Create", "payload": {"session_id": "abc123"}}
    )
    print(f"   Action message: {action_msg}")
    
    print("\n3. Socket.IO Examples:")
    
    # Get event names
    control_event = sio_adapter.get_event_name(Route.CONTROL_COMMAND)
    audio_event = sio_adapter.get_event_name(Route.AUDIO_CHUNK)
    action_event = sio_adapter.get_event_name(Route.ACTION_DISPATCH)
    
    print(f"   Control event: '{control_event}'")
    print(f"   Audio event: '{audio_event}'")
    print(f"   Action event: '{action_event}'")
    
    # Room management
    room_name = sio_adapter.build_room_name("abc123")
    print(f"   Room name: '{room_name}'")
    
    print("\n4. Reverse Lookup Examples:")
    
    # Parse HTTP path
    try:
        route, params = http_adapter.parse_path("/audio/session123", "POST")
        print(f"   Path '/audio/session123' -> Route: {route}, Params: {params}")
    except ValueError as e:
        print(f"   Error: {e}")
    
    # Parse WebSocket message
    try:
        route, data = ws_adapter.parse_message({
            "type": "control",
            "data": {"command": "start"}
        })
        print(f"   WebSocket 'control' -> Route: {route}")
    except ValueError as e:
        print(f"   Error: {e}")
    
    # Parse Socket.IO event
    try:
        route, data = sio_adapter.parse_event("audio_chunk", {"audio": "data"})
        print(f"   Socket.IO 'audio_chunk' -> Route: {route}")
    except ValueError as e:
        print(f"   Error: {e}")
    
    print("\n5. PyStoreX Action Integration:")
    
    # Find route by action
    create_route = router.from_pystore_action("[Session] Create")
    transcription_route = router.from_pystore_action("[Session] Transcription Done")
    
    print(f"   '[Session] Create' -> {create_route}")
    print(f"   '[Session] Transcription Done' -> {transcription_route}")
    
    # Get action from route
    create_action = router.to_pystore_action(Route.ACTION_SESSION_CREATE)
    chunk_action = router.to_pystore_action(Route.ACTION_SESSION_CHUNK_UPLOAD_DONE)
    
    print(f"   {Route.ACTION_SESSION_CREATE} -> '{create_action}'")
    print(f"   {Route.ACTION_SESSION_CHUNK_UPLOAD_DONE} -> '{chunk_action}'")
    
    print("\n6. Route Categories:")
    
    control_routes = router.get_routes_by_category(RouteCategory.CONTROL)
    audio_routes = router.get_routes_by_category(RouteCategory.AUDIO)
    event_routes = router.get_routes_by_category(RouteCategory.EVENTS)
    
    print(f"   Control routes: {len(control_routes)} routes")
    print(f"   Audio routes: {len(audio_routes)} routes")
    print(f"   Event routes: {len(event_routes)} routes")
    
    bidirectional = router.get_bidirectional_routes()
    print(f"   Bidirectional routes: {len(bidirectional)} routes")
    
    print("\n7. Parameter Validation:")
    
    # Valid parameters
    valid_params = {"session_id": "abc123", "chunk_id": 1}
    is_valid = router.validate_route_parameters(Route.AUDIO_CHUNK, valid_params)
    print(f"   Audio chunk with {valid_params}: Valid = {is_valid}")
    
    # Invalid parameters (missing chunk_id)
    invalid_params = {"session_id": "abc123"}
    is_valid = router.validate_route_parameters(Route.AUDIO_CHUNK, invalid_params)
    print(f"   Audio chunk with {invalid_params}: Valid = {is_valid}")
    
    print("\n=== End of Examples ===")


if __name__ == "__main__":
    demonstrate_usage()
#!/usr/bin/env python3
"""
Test script for the Unified Router System
Demonstrates all major functionality and validates route conversions
"""

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.api.routing.unified_router import (
    UnifiedRouter, Route, RouteCategory, ProtocolType,
    create_unified_router, create_protocol_adapters,
    HTTPSSEAdapter, WebSocketAdapter, SocketIOAdapter
)


def test_basic_functionality():
    """Test basic router functionality"""
    print("=== Testing Basic Functionality ===")
    
    router = create_unified_router()
    
    # Test route definitions exist
    assert Route.SESSION_CREATE in router._route_definitions
    assert Route.AUDIO_UPLOAD in router._route_definitions
    assert Route.ACTION_SESSION_CREATE in router._route_definitions
    
    print("✅ Route definitions loaded successfully")
    
    # Test HTTP SSE conversion
    session_path = router.to_http_sse_path(Route.SESSION_CREATE)
    assert session_path == "/session"
    
    audio_path = router.to_http_sse_path(Route.AUDIO_UPLOAD, {"session_id": "test123"})
    assert audio_path == "/audio/test123"
    
    print("✅ HTTP SSE path conversion working")
    
    # Test WebSocket conversion
    ws_type = router.to_websocket_message_type(Route.CONTROL_COMMAND)
    assert ws_type == "control"
    
    audio_type = router.to_websocket_message_type(Route.AUDIO_CHUNK)
    assert audio_type == "audio_chunk"
    
    print("✅ WebSocket message type conversion working")
    
    # Test Socket.IO conversion
    sio_event = router.to_socketio_event_name(Route.CONTROL_COMMAND)
    assert sio_event == "control"
    
    audio_event = router.to_socketio_event_name(Route.AUDIO_CHUNK)
    assert audio_event == "audio_chunk"
    
    print("✅ Socket.IO event name conversion working")
    
    # Test PyStoreX action conversion
    action = router.to_pystore_action(Route.ACTION_SESSION_CREATE)
    assert action == "[Session] Create"
    
    chunk_action = router.to_pystore_action(Route.ACTION_SESSION_CHUNK_UPLOAD_DONE)
    assert chunk_action == "[Session] Chunk Upload Done"
    
    print("✅ PyStoreX action conversion working")


def test_reverse_lookup():
    """Test reverse lookup functionality"""
    print("\n=== Testing Reverse Lookup ===")
    
    router = create_unified_router()
    
    # Test HTTP path parsing
    route, params = router.from_http_sse_path("/audio/session123", "POST")
    assert route == Route.AUDIO_UPLOAD
    assert params["session_id"] == "session123"
    
    route, params = router.from_http_sse_path("/events/test456", "GET")
    assert route == Route.EVENTS_STREAM
    assert params["session_id"] == "test456"
    
    print("✅ HTTP path parsing working")
    
    # Test WebSocket message type lookup
    route = router.from_websocket_message_type("control")
    assert route == Route.CONTROL_COMMAND
    
    route = router.from_websocket_message_type("audio_chunk")
    assert route == Route.AUDIO_CHUNK
    
    print("✅ WebSocket message type lookup working")
    
    # Test Socket.IO event lookup (returns most general route for shared event names)
    route = router.from_socketio_event_name("control")
    assert route == Route.CONTROL_COMMAND  # Most general control route
    
    route = router.from_socketio_event_name("audio_chunk")
    assert route == Route.AUDIO_CHUNK  # Most general audio chunk route
    
    print("✅ Socket.IO event lookup working")
    
    # Test PyStoreX action lookup (returns first matching route)
    route = router.from_pystore_action("[Session] Create")
    # Note: Both SESSION_CREATE and ACTION_SESSION_CREATE use this action
    assert route in [Route.SESSION_CREATE, Route.ACTION_SESSION_CREATE]
    
    route = router.from_pystore_action("[Session] Transcription Done")
    assert route == Route.ACTION_SESSION_TRANSCRIPTION_DONE
    
    print("✅ PyStoreX action lookup working")


def test_protocol_adapters():
    """Test protocol adapter functionality"""
    print("\n=== Testing Protocol Adapters ===")
    
    router = create_unified_router()
    adapters = create_protocol_adapters(router)
    
    http_adapter = adapters[ProtocolType.HTTP_SSE]
    ws_adapter = adapters[ProtocolType.WEBSOCKET]
    sio_adapter = adapters[ProtocolType.SOCKETIO]
    
    # Test HTTP adapter
    path = http_adapter.build_path(Route.AUDIO_UPLOAD, session_id="test123")
    assert path == "/audio/test123"
    
    route, params = http_adapter.parse_path("/audio/test123", "POST")
    assert route == Route.AUDIO_UPLOAD
    assert params["session_id"] == "test123"
    
    print("✅ HTTP adapter working")
    
    # Test WebSocket adapter
    message = ws_adapter.build_message(
        Route.CONTROL_COMMAND,
        {"command": "start"},
        session_id="test123"
    )
    assert message["type"] == "control"
    assert message["data"]["command"] == "start"
    assert message["session_id"] == "test123"
    
    route, data = ws_adapter.parse_message({
        "type": "audio_chunk",
        "data": {"audio": "base64data"}
    })
    assert route == Route.AUDIO_CHUNK
    assert data["audio"] == "base64data"
    
    print("✅ WebSocket adapter working")
    
    # Test Socket.IO adapter
    event_name = sio_adapter.get_event_name(Route.CONTROL_COMMAND)
    assert event_name == "control"
    
    route, data = sio_adapter.parse_event("control", {"command": "start"})
    assert route == Route.CONTROL_COMMAND
    assert data["command"] == "start"
    
    room_name = sio_adapter.build_room_name("session123")
    assert room_name == "session_session123"
    
    print("✅ Socket.IO adapter working")


def test_route_categories():
    """Test route category functionality"""
    print("\n=== Testing Route Categories ===")
    
    router = create_unified_router()
    
    # Test category grouping
    control_routes = router.get_routes_by_category(RouteCategory.CONTROL)
    audio_routes = router.get_routes_by_category(RouteCategory.AUDIO)
    event_routes = router.get_routes_by_category(RouteCategory.EVENTS)
    
    assert Route.CONTROL_COMMAND in control_routes
    assert Route.CONTROL_START in control_routes
    assert Route.AUDIO_UPLOAD in audio_routes
    assert Route.AUDIO_CHUNK in audio_routes
    assert Route.EVENTS_STREAM in event_routes
    assert Route.ACTION_DISPATCH in event_routes
    
    print(f"✅ Found {len(control_routes)} control routes")
    print(f"✅ Found {len(audio_routes)} audio routes") 
    print(f"✅ Found {len(event_routes)} event routes")
    
    # Test bidirectional routes
    bidirectional = router.get_bidirectional_routes()
    assert Route.CONTROL_COMMAND in bidirectional
    assert Route.ACTION_DISPATCH in bidirectional
    assert Route.ERROR in bidirectional
    
    print(f"✅ Found {len(bidirectional)} bidirectional routes")


def test_parameter_validation():
    """Test parameter validation"""
    print("\n=== Testing Parameter Validation ===")
    
    router = create_unified_router()
    
    # Test valid parameters
    valid_params = {"session_id": "test123", "chunk_id": 1}
    is_valid = router.validate_route_parameters(Route.AUDIO_CHUNK, valid_params)
    assert is_valid == True
    
    # Test missing required parameter
    invalid_params = {"session_id": "test123"}  # missing chunk_id
    is_valid = router.validate_route_parameters(Route.AUDIO_CHUNK, invalid_params)
    assert is_valid == False
    
    # Test route with no required parameters
    no_params = {}
    is_valid = router.validate_route_parameters(Route.HEALTH_CHECK, no_params)
    assert is_valid == True
    
    print("✅ Parameter validation working")


def test_sse_event_formatting():
    """Test SSE event formatting"""
    print("\n=== Testing SSE Event Formatting ===")
    
    router = create_unified_router()
    adapters = create_protocol_adapters(router)
    http_adapter = adapters[ProtocolType.HTTP_SSE]
    
    # Test SSE event format
    sse_event = http_adapter.build_sse_event(
        Route.TRANSCRIPT,
        {"text": "Hello world", "is_final": True, "confidence": 0.95},
        event_id="12345"
    )
    
    lines = sse_event.strip().split('\n')
    assert lines[0] == "event: transcript"
    assert lines[1] == "id: 12345"
    assert lines[2].startswith("data: ")
    assert "Hello world" in sse_event
    
    print("✅ SSE event formatting working")


def test_comprehensive_mapping():
    """Test that all major routes work across protocols"""
    print("\n=== Testing Comprehensive Protocol Mapping ===")
    
    router = create_unified_router()
    
    # Key routes that should work across all protocols
    key_routes = [
        Route.SESSION_CREATE,
        Route.CONTROL_COMMAND,
        Route.AUDIO_UPLOAD,
        Route.AUDIO_CHUNK,
        Route.ACTION_DISPATCH,
        Route.EVENTS_STREAM,
        Route.TRANSCRIPT,
        Route.ERROR
    ]
    
    for route in key_routes:
        # Should have HTTP SSE path
        http_path = router.to_http_sse_path(route)
        assert http_path is not None
        
        # Should have WebSocket message type
        ws_type = router.to_websocket_message_type(route)
        assert ws_type is not None
        
        # Should have Socket.IO event name
        sio_event = router.to_socketio_event_name(route)
        assert sio_event is not None
        
        print(f"✅ {route.name}: HTTP='{http_path}', WS='{ws_type}', SIO='{sio_event}'")
    
    print(f"✅ All {len(key_routes)} key routes mapped across protocols")


def run_all_tests():
    """Run all test functions"""
    print("🧪 Starting Unified Router Tests\n")
    
    try:
        test_basic_functionality()
        test_reverse_lookup()
        test_protocol_adapters()
        test_route_categories()
        test_parameter_validation()
        test_sse_event_formatting()
        test_comprehensive_mapping()
        
        print("\n🎉 All tests passed! The Unified Router is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    
    if success:
        print("\n" + "="*60)
        print("Running usage demonstration...")
        print("="*60)
        
        # Import and run the demonstration
        from src.api.routing.unified_router import demonstrate_usage
        demonstrate_usage()
    
    sys.exit(0 if success else 1)
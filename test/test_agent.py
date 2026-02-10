import asyncio
import os
import json
import pytest
from libqtile.agent import AGENT_SOCK_NAME
from libqtile.utils import get_cache_dir

@pytest.mark.asyncio
async def test_agent_bridge_connection(manager_nospawn):
    # manager_nospawn fixture starts qtile which starts AgentBridge
    
    socket_path = os.path.join(get_cache_dir(), AGENT_SOCK_NAME)
    
    # Wait for socket to be created
    for _ in range(10):
        if os.path.exists(socket_path):
            break
        await asyncio.sleep(0.1)
    
    assert os.path.exists(socket_path)

    # Connect to the socket
    reader, writer = await asyncio.open_unix_connection(socket_path)

    # Send echo request
    request = {
        "jsonrpc": "2.0", 
        "method": "echo", 
        "params": "hello agent", 
        "id": 1
    }
    writer.write(json.dumps(request).encode())
    writer.write_eof()

    response_data = await reader.read()
    writer.close()
    await writer.wait_closed()

    response = json.loads(response_data.decode())
    assert response["jsonrpc"] == "2.0"
    assert response["result"] == "hello agent"
    assert response["id"] == 1

@pytest.mark.asyncio
async def test_agent_bridge_method_not_found(manager_nospawn):
    socket_path = os.path.join(get_cache_dir(), AGENT_SOCK_NAME)
    
    reader, writer = await asyncio.open_unix_connection(socket_path)

    request = {
        "jsonrpc": "2.0", 
        "method": "non_existent_method", 
        "id": 2
    }
    writer.write(json.dumps(request).encode())
    writer.write_eof()

    response_data = await reader.read()
    writer.close()
    await writer.wait_closed()

    response = json.loads(response_data.decode())
    assert response["error"]["code"] == -32601
    assert response["id"] == 2

import asyncio
import websockets
import json
import sys
import os

# Force UTF-8 output for Windows console
sys.stdout.reconfigure(encoding='utf-8')

async def verify_s3():
    uri = "ws://127.0.0.1:8765/ws"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            
            # 1. Send a request that requires a tool
            msg = {
                "type": "chat",
                "message": "Run this exact Windows command and tell me the output: echo S3_OK"
            }
            print(f"Sending: {msg['message']}")
            await websocket.send(json.dumps(msg))
            
            # 2. Listen for events
            events_received = {
                "thinking": False,
                "tool_call": False,
                "tool_result": False,
                "response": False
            }
            
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=30)
                    data = json.loads(response)
                    event_type = data.get("type")
                    content = data.get("data")
                    
                    print(f"\n[Event: {event_type}]")
                    if event_type == "thinking":
                        print(f"Thinking: {content[:50]}...")
                        events_received["thinking"] = True
                    elif event_type == "tool_call":
                        print(f"Tool Call: {content}")
                        events_received["tool_call"] = True
                    elif event_type == "tool_result":
                        print(f"Tool Result: {content}")
                        events_received["tool_result"] = True
                    elif event_type == "response":
                        print(f"Response: {content}")
                        events_received["response"] = True
                    elif event_type == "complete":
                        print("Stream complete.")
                        break
                    elif event_type == "error":
                        print(f"[ERROR]: {content}")
                        break
                        
                except asyncio.TimeoutError:
                    print("[TIMEOUT] waiting for response")
                    break
            
            # 3. Summary
            print("\n=== Verification Summary ===")
            print(f"Thinking: {'[OK]' if events_received['thinking'] else '[WARN] (Might be skipped if model is fast)'}")
            print(f"Tool Call: {'[OK]' if events_received['tool_call'] else '[FAIL]'}")
            print(f"Tool Result: {'[OK]' if events_received['tool_result'] else '[FAIL]'}")
            print(f"Final Response: {'[OK]' if events_received['response'] else '[FAIL]'}")
            
            if events_received["tool_call"] and events_received["tool_result"]:
                print("\n[SUCCESS] S3 Tool Support Verified!")
                sys.exit(0)
            else:
                print("\n[FAIL] S3 Verification Failed")
                sys.exit(1)

    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(verify_s3())

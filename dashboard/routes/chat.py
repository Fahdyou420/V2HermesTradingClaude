import os
import json
import requests
import redis
from flask import Blueprint, request, Response, jsonify

chat_bp = Blueprint('chat', __name__)

HERMES_RPC_URL = os.getenv("HERMES_RPC_URL", "http://host.docker.internal:7778")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

@chat_bp.route('/send', methods=['POST'])
def send_message():
    data = request.get_json() or {}
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "No message provided"}), 400

    # Store user message in redis history
    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        user_log = json.dumps({"role": "user", "content": message})
        r.rpush("chat_history", user_log)
        r.ltrim("chat_history", -50, -1)  # keep last 50 entries
    except Exception as e:
        # Graceful logging fallbacks
        print(f"Redis chat logging failed: {e}")

    def event_stream():
        try:
            url = f"{HERMES_RPC_URL}/chat"
            payload = {
                "message": message,
                "task_type": "analysis"
            }
            # Stream the request to the RPC server
            response = requests.post(url, json=payload, stream=True, timeout=120)
            
            accumulated_response = ""
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8').strip()
                    
                    if decoded_line.startswith("data:"):
                        try:
                            data_part = decoded_line[5:].strip()
                            event_data = json.loads(data_part)
                            if isinstance(event_data, dict) and "type" in event_data:
                                if "content" in event_data and event_data["type"] == "token":
                                    accumulated_response += event_data["content"]
                                yield f"data: {json.dumps(event_data)}\n\n"
                            else:
                                yield f"data: {json.dumps({'type': 'token', 'content': data_part})}\n\n"
                        except Exception:
                            yield f"data: {json.dumps({'type': 'token', 'content': decoded_line})}\n\n"
                    else:
                        try:
                            val = json.loads(decoded_line)
                            if isinstance(val, dict) and "type" in val:
                                if "content" in val and val["type"] == "token":
                                    accumulated_response += val["content"]
                                yield f"data: {decoded_line}\n\n"
                            else:
                                yield f"data: {json.dumps({'type': 'token', 'content': decoded_line})}\n\n"
                        except json.JSONDecodeError:
                            accumulated_response += decoded_line + "\n"
                            yield f"data: {json.dumps({'type': 'token', 'content': decoded_line + '\n'})}\n\n"

            # Store the assistant response in history
            if accumulated_response.strip():
                try:
                    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
                    agent_log = json.dumps({"role": "assistant", "content": accumulated_response})
                    r.rpush("chat_history", agent_log)
                    r.ltrim("chat_history", -50, -1)
                except Exception as ex:
                    print(f"Redis assistant logging failed: {ex}")

        except Exception as e:
            yield f"data: {json.dumps({'type': 'token', 'content': f'RPC connection failed: {str(e)}'})}\n\n"
        
        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

    return Response(event_stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    })

@chat_bp.route('/history', methods=['GET'])
def get_chat_history():
    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        history_raw = r.lrange("chat_history", 0, -1)
        history = []
        for h in history_raw:
            try:
                history.append(json.loads(h))
            except Exception:
                history.append({"role": "unknown", "content": h})
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve chat history: {str(e)}"}), 500

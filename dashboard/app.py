import os
import sys
import requests
from flask import Flask, Response, redirect, jsonify, render_template, request
from flask_cors import CORS

# Add current folder to path to make sure blueprints load seamlessly as modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import Blueprints
from routes.chat import chat_bp
from routes.vault import vault_bp
from routes.strategy import strategy_bp
from routes.trades import trades_bp
from routes.rnd import rnd_bp

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app, resources={r"/*": {"origins": "*"}})

# Register Blueprints with unified API routing prefixes
app.register_blueprint(chat_bp, url_prefix='/api/chat')
app.register_blueprint(vault_bp, url_prefix='/api/vault')
app.register_blueprint(strategy_bp, url_prefix='/api/strategy')
app.register_blueprint(trades_bp, url_prefix='/api/trades')
app.register_blueprint(rnd_bp, url_prefix='/api/rnd')

# Global health check endpoint
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "hermes-dashboard-backend"}), 200

# Template Views
@app.route('/terminal', methods=['GET'])
def view_terminal():
    return render_template('terminal.html', active_page='terminal')

@app.route('/knowledge', methods=['GET'])
def view_knowledge():
    return render_template('knowledge.html', active_page='knowledge')

@app.route('/strategy', methods=['GET'])
def view_strategy():
    return render_template('strategy.html', active_page='strategy')

@app.route('/trades', methods=['GET'])
def view_trades():
    return render_template('trades.html', active_page='trades')

@app.route('/rnd', methods=['GET'])
def view_rnd():
    return render_template('rnd.html', active_page='rnd')

@app.route('/api/market/price', methods=['GET'])
def get_market_price():
    try:
        mt5_url = os.getenv("MT5_BRIDGE_URL", "http://mt5_bridge:5558")
        resp = requests.get(f"{mt5_url}/latest_bars?n=1", timeout=5)
        if resp.status_code == 200:
            bars = resp.json()
            if bars and len(bars) > 0:
                price = bars[-1].get("close", 0.0)
                return jsonify({"price": price})
    except Exception as e:
        print(f"Failed to fetch market price: {e}")
    return jsonify({"price": 0.0})

@app.route('/api/errors', methods=['GET'])
def get_errors():
    from services.shared.error_bus import get_recent_errors
    n = int(request.args.get('n', 100))
    return jsonify(get_recent_errors(n))

# HTMX System status endpoint returns HTML status component directly
@app.route('/api/status', methods=['GET'])
def system_status():
    return """
    <div class="flex items-center space-x-2">
        <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
        <span>Hermes RPC: <span class="text-gray-200">Online</span></span>
    </div>
    <div class="flex items-center space-x-2">
        <div class="w-2 h-2 rounded-full bg-emerald-500"></div>
        <span>MT5 Terminal: <span class="text-gray-200">Connected</span></span>
    </div>
    <div class="flex items-center space-x-2">
        <div class="w-2 h-2 rounded-full bg-emerald-500"></div>
        <span>Paper Trader: <span class="text-gray-200">Active</span></span>
    </div>
    """

# Redirect GET / to /terminal
@app.route('/')
def home_redirect():
    return redirect('/terminal')

# SSE streaming helper
def sse_stream(generator):
    """Wraps are python generator yielding textual event messages into a high-performance SSE stream"""
    return Response(generator, mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    })

# Error handler for 404
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found"}), 404

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)

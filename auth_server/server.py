import os
import json
import time
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify

app = Flask(__name__)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
GAS_URL = "https://script.google.com/macros/s/AKfycbwd75y2vsmgA7g0AtNxqiCSLkqT4Ied1n-nV5JpOy__gM3bB8pWqNw6PZiyWpbrNeSjqg/exec"

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def verify_with_gas(email, node_name):
    # 發送 POST 到 Google Apps Script 進行試算表授權查詢
    payload = {
        'email': email,
        'node_name': node_name
    }
    req_data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        GAS_URL,
        data=req_data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as res:
            # GAS 重導向處理由 urllib 自動完成
            return json.loads(res.read().decode('utf-8'))
    except Exception as e:
        return {'status': 'error', 'message': f'GAS Connection failed: {e}'}

@app.route('/api/auth/google-config', methods=['GET'])
def get_google_config():
    config = load_config()
    client_id = os.environ.get('GOOGLE_CLIENT_ID') or config.get('google_client_id', '')
    return jsonify({
        'google_client_id': client_id
    })

@app.route('/api/auth/google-login', methods=['POST'])
def google_login():
    data = request.json or {}
    code = data.get('code')
    redirect_uri = data.get('redirect_uri')
    node_name = data.get('node_name')

    if not code or not redirect_uri or not node_name:
        return jsonify({'status': 'error', 'message': 'Missing code, redirect_uri or node_name'}), 400

    config = load_config()
    client_id = os.environ.get('GOOGLE_CLIENT_ID') or config.get('google_client_id')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET') or config.get('google_client_secret')

    if not client_id or not client_secret or "PLACEHOLDER" in client_id or "PLACEHOLDER" in client_secret:
        return jsonify({'status': 'error', 'message': 'Google client not configured on server (Missing client_id or client_secret)'}), 500

    # 1. 向 Google OAuth 伺服器交換 Token
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    
    req_data = urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(token_url, data=req_data, method='POST')
    
    try:
        with urllib.request.urlopen(req) as res:
            tokens = json.loads(res.read().decode('utf-8'))
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to exchange token with Google: {e}'}), 400

    # 2. 取得 Google 使用者資訊 (Email)
    access_token = tokens.get('access_token')
    userinfo_url = f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={access_token}"
    
    try:
        with urllib.request.urlopen(userinfo_url) as res:
            user_info = json.loads(res.read().decode('utf-8'))
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to fetch userinfo from Google: {e}'}), 400

    email = user_info.get('email')
    if not email:
        return jsonify({'status': 'error', 'message': 'Email not found in Google profile'}), 400

    # 3. 呼叫 GAS (Google 試算表) 進行身分與模式授權檢查
    gas_res = verify_with_gas(email, node_name)
    if gas_res.get('status') != 'success':
        return jsonify({
            'status': 'error',
            'message': gas_res.get('message', '試算表中無此帳號授權紀錄。')
        }), 403

    mode = gas_res.get('mode', 'mock') # 預設非您本人就是 mock 模式

    # 4. 綁定本機與記錄啟動狀態
    devices = config.setdefault('devices', {})
    devices[node_name] = {
        'email': email,
        'last_active': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'mode': mode
    }
    save_config(config)

    device_token = f"session-token-for-{node_name}-{int(time.time())}"
    
    return jsonify({
        'status': 'success',
        'node_name': node_name,
        'mode': mode,
        'expires_at': gas_res.get('expires_at', ''),
        'token': device_token,
        'email': email
    })

@app.route('/api/device/license', methods=['POST'])
def check_license():
    data = request.json or {}
    node_name = data.get('node_name')
    token = data.get('token')

    if not node_name or not token:
        return jsonify({'status': 'error', 'message': 'Missing node_name or token'}), 400

    config = load_config()
    devices = config.get('devices', {})

    if node_name not in devices:
        return jsonify({'status': 'error', 'message': 'Device not registered'}), 401

    device_info = devices[node_name]
    email = device_info.get('email')

    # 每一次啟動與定時檢查，都再次向 GAS 確認該 Email 的最新模式
    gas_res = verify_with_gas(email, node_name)
    if gas_res.get('status') != 'success':
        return jsonify({'status': 'error', 'message': 'Access revoked in Google Sheet'}), 403

    mode = gas_res.get('mode', 'mock')
    device_info['last_active'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    device_info['mode'] = mode
    save_config(config)

    return jsonify({
        'status': 'success',
        'node_name': node_name,
        'mode': mode,
        'expires_at': gas_res.get('expires_at', '')
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5085, debug=True)

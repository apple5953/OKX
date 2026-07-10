import os
import sys
import json
import urllib.request
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8085
REDIRECT_URI = f"http://localhost:{PORT}"
BACKEND_URL = "http://localhost:5085"

received_auth_code = None

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global received_auth_code
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        # 接收 Google 回傳的 authorization code
        code = params.get('code', [None])[0]
        
        if code:
            received_auth_code = code
            html = """
            <html>
            <head><title>驗證成功</title></head>
            <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                <h2 style="color: #2e7d32;">✓ Google 登入驗證成功！</h2>
                <p>授權金鑰已接收，您可以安全地關閉此網頁，並回到終端機程式。</p>
            </body>
            </html>
            """
        else:
            # 測試/本地開發備用：若是直接存取帶 email 參數則進入模擬模式
            email = params.get('email', [None])[0]
            if email:
                received_auth_code = f"mock-code-for-{email}"
                html = f"""
                <html>
                <head><title>驗證成功 (模擬模式)</title></head>
                <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                    <h2 style="color: #1565c0;">✓ 模擬登入驗證成功！</h2>
                    <p>已使用模擬身份 <b>{email}</b> 登入。您可以關閉此網頁。</p>
                </body>
                </html>
                """
            else:
                html = """
                <html>
                <head><title>驗證失敗</title></head>
                <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                    <h2 style="color: #c62828;">✗ 驗證失敗</h2>
                    <p>沒有接收到 Google OAuth 授權碼，請重試。</p>
                </body>
                </html>
                """
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        pass

def run_local_server():
    server = HTTPServer(('localhost', PORT), OAuthCallbackHandler)
    server.timeout = 120  # 給使用者 2 分鐘時間登入
    return server

def request_backend(endpoint, data):
    url = f"{BACKEND_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception as e:
        # 當為 HTTPError 時讀取錯誤訊息
        if hasattr(e, 'read'):
            try:
                err_data = json.loads(e.read().decode('utf-8'))
                return err_data
            except Exception:
                pass
        return {'status': 'error', 'message': str(e)}

def main():
    if len(sys.argv) < 2:
        print("Usage: python auth_wizard.py <NODE_NAME>")
        sys.exit(1)
        
    node_name = sys.argv[1]
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    token_path = os.path.join(root_dir, "auth_token.json")
    
    # 1. 檢查本機是否已有 Token 且可用
    if os.path.exists(token_path):
        try:
            with open(token_path, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            
            res = request_backend('/api/device/license', {
                'node_name': node_name,
                'token': token_data.get('token')
            })
            if res and res.get('status') == 'success':
                # 靜默通過，直接輸出 JSON 給 PowerShell
                print(json.dumps(res))
                sys.exit(0)
        except Exception:
            pass

    # 2. 向後端詢問 Google Client ID
    print("[*] 正在向後端取得授權設定...", file=sys.stderr)
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/auth/google-config") as res:
            g_config = json.loads(res.read().decode('utf-8'))
    except Exception as e:
        print(f"[Error] 無法連接至授權後端 API: {e}", file=sys.stderr)
        sys.exit(1)

    client_id = g_config.get('google_client_id')
    
    # 3. 啟動本機 Port 8085 接收 Callback
    server = run_local_server()

    # 如果沒設定 Client ID，開啟測試/模擬網址，方便使用者本地無 credentials 測試
    if not client_id or client_id.startswith("YOUR_GOOGLE_CLIENT_ID"):
        print("[!] 警告: 後端尚未設定真實 Google Client ID。已進入【模擬開發測試】模式！", file=sys.stderr)
        auth_url = f"http://localhost:{PORT}/?email=demo_user@gmail.com"
    else:
        # 正式的 Google OAuth 伺服器登入網址
        params = {
            'client_id': client_id,
            'redirect_uri': REDIRECT_URI,
            'response_type': 'code',
            'scope': 'openid email profile',
            'access_type': 'online',
            'prompt': 'select_account'
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    print(f"[*] 正在打開瀏覽器進行 Google 帳號授權...", file=sys.stderr)
    print(f"[*] 若瀏覽器未自動開啟，請手動複製此網址：\n{auth_url}", file=sys.stderr)
    webbrowser.open(auth_url)
    
    # 監聽 Callback
    server.handle_request()
    server.server_close()
    
    if not received_auth_code:
        print("[Error] 登入超時或被取消。", file=sys.stderr)
        sys.exit(1)
        
    # 4. 如果是模擬模式
    if received_auth_code.startswith("mock-code-for-"):
        mock_email = received_auth_code.replace("mock-code-for-", "")
        # 直接打一個模擬驗證 (如果後端不支援交換 code，這時 server 仍只支援 client_id 模式則需要傳假 token 過去)
        # 為了開發測試流暢：後端在未配置 credentials 時也可以對 mock 進行認證，此處我們改為傳送對應資訊
        print(f"[*] 正在使用模擬身份 [{mock_email}] 註冊綁定...", file=sys.stderr)
        
        # 發起請求給後端（若後端是 Mock 狀態直接將該帳號寫入）
        # 本地測試時直接向 /api/auth/google-login 的本地邏輯打
        # 我們在本機測試為了相容，打 /api/auth/google-login 發送模擬資訊
        res = request_backend('/api/auth/google-login', {
            'code': received_auth_code,
            'redirect_uri': REDIRECT_URI,
            'node_name': node_name
        })
    else:
        # 5. 正式向後端發送 Google Code 以換取 Session Token
        print(f"[*] 正在向後端 API 交換驗證憑證...", file=sys.stderr)
        res = request_backend('/api/auth/google-login', {
            'code': received_auth_code,
            'redirect_uri': REDIRECT_URI,
            'node_name': node_name
        })

    if not res or res.get('status') != 'success':
        msg = res.get('message', '未知錯誤') if res else '無法連接後端'
        print(f"[Error] 授權失敗: {msg}", file=sys.stderr)
        sys.exit(1)
        
    # 6. 成功登入，寫入本地 auth_token.json 與初始化空白 Journal
    with open(token_path, 'w', encoding='utf-8') as f:
        json.dump({'token': res['token'], 'email': res.get('email', 'unknown')}, f, indent=2)
        
    journal_path = os.path.join(root_dir, f"journal_{node_name}.json")
    trades_path = os.path.join(root_dir, f"active_trades_{node_name}.json")
    
    if not os.path.exists(journal_path):
        with open(journal_path, 'w', encoding='utf-8') as f:
            f.write("[]")
    if not os.path.exists(trades_path):
        with open(trades_path, 'w', encoding='utf-8') as f:
            f.write("[]")
            
    print(f"[OK] 授權成功！", file=sys.stderr)
    # 輸出 json 供 powershell 讀取
    print(json.dumps(res))

if __name__ == '__main__':
    main()

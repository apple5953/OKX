"""
auto_restart.py — 監控 server.py，崩潰後自動清理 port 5017 並重啟
用法: python auto_restart.py
"""
import subprocess
import sys
import time
import socket

def kill_port(port):
    """嘗試釋放佔用指定 port 的 process"""
    try:
        import subprocess as sp
        result = sp.run(
            ['netstat', '-ano'],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'
        )
        for line in result.stdout.splitlines():
            if f':{port} ' in line and 'LISTENING' in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid.isdigit():
                    sp.run(['taskkill', '/PID', pid, '/F'],
                           capture_output=True, errors='ignore')
                    print(f"[AutoRestart] Killed PID {pid} holding port {port}")
                    time.sleep(0.5)
    except Exception as e:
        print(f"[AutoRestart] kill_port error: {e}")

def main():
    restart_count = 0
    while True:
        # Clear guard ports before starting
        kill_port(5017)
        kill_port(5000)
        time.sleep(1)

        print(f"[AutoRestart] Starting server.py (attempt #{restart_count + 1})")
        proc = subprocess.Popen(
            [sys.executable, '-X', 'utf8', 'server.py'],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        try:
            proc.wait()
        except KeyboardInterrupt:
            print("[AutoRestart] Interrupted by user. Stopping.")
            proc.terminate()
            break

        exit_code = proc.returncode
        restart_count += 1
        print(f"[AutoRestart] server.py exited with code {exit_code}. Restarting in 5s...")
        time.sleep(5)

if __name__ == '__main__':
    main()

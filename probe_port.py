import socket
import time

def probe_port(host='127.0.0.1', port=49853):
    try:
        # 创建socket连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        
        print(f"尝试连接 {host}:{port}...")
        sock.connect((host, port))
        print("连接成功！")
        
        # 尝试发送一些探测数据
        probes = [
            b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n",  # HTTP
            b"HELLO",  # 简单文本
            b"\x81\x00",  # WebSocket ping帧
        ]
        
        for probe in probes:
            print(f"\n发送探测数据: {probe}")
            sock.send(probe)
            
            # 尝试接收响应
            try:
                response = sock.recv(1024)
                if response:
                    print(f"收到响应: {response[:100]}...")
                    print(f"响应长度: {len(response)} 字节")
                    print(f"响应十六进制: {response.hex()[:50]}...")
                else:
                    print("无响应")
            except socket.timeout:
                print("接收超时")
            
            time.sleep(0.5)
        
        sock.close()
        
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    probe_port()
import socket
import sys
import json
import threading

HOST = ''    # '' = listen on all interfaces
PORT = 5789

clients = {}    # client_id -> {"username": ..., "conn": ...}
clients_lock = threading.Lock()     # Threads share `clients`, so protect it

def send_msg(conn, msg):
    conn.sendall((json.dumps(msg) + "\n").encode())

def build_client_list(my_id):
    with clients_lock:
        return [{"username": c["username"], "id": cid}
                for cid, c in clients.items() if cid != my_id]

def handle_client(conn, address):
    client_id = address[1]      # The client's port is the id
    reader = conn.makefile("r") # Lets us read one line at a time
    try:
        send_msg(conn, {"type": "connect", "status": "successful"})

        line = reader.readline()
        if not line:
            return              # Client left
        msg = json.loads(line)
        if msg.get("type") != "register":
            return

        with clients_lock:
            clients[client_id] = {"username": msg["username"], "conn": conn}
        print(f'Registered {msg["username"]} as {client_id}' )

        send_msg(conn, {"type": "welcome", "client_id": client_id})
        send_msg(conn, {"type": "client_list", "clients": build_client_list(client_id)})

        for line in reader:     # Loops until the client disconnects
            msg = json.loads(line)
            if msg.get("type") == "client_request" and msg.get("command") == "refresh":
                send_msg(conn, {"type": "client_list", "clients": build_client_list(client_id)})
    except (ConnectionError, json.JSONDecodeError):
        pass
    finally:
        with clients_lock:
            clients.pop(client_id, None)
        conn.close()
        print(f'Disconnected {address[0]}: {client_id}')


try:
    # Dual-stack socket: accepts both IPv4 (127.0.0.1) and IPv6 (::1) clients
    soc = socket.create_server((HOST, PORT), family=socket.AF_INET6,
                               dualstack_ipv6=True, backlog=9)
except OSError as e:
    print(f'Bind failed. Error Code: {e.errno} Message: {e.strerror}')
    sys.exit(1)

print(f'Server listening on port {PORT} (IPv4 + IPv6). Press Ctrl+C to stop.')

# Wakeup once a second to allow KeyboardInterrupt
soc.settimeout(1.0)

# Keep server running until KeyboardInterrupt
try:
    while True:
        try:
            conn, address = soc.accept()
        except TimeoutError:
            continue
        print(f'Connected with {address[0]}:{address[1]}')
        conn.close() # Instead store the connection here, close only when client disconnects
except KeyboardInterrupt:
    print('\nShutting down server')
finally:
    soc.close()

# Server allocates a range of ports

# Client connects to server -> server assigns a port to client automatically

# Client receives a list of connected clients to the server and has an option to "call" another client

# Server transmits packets/data between connected clients only

# function that listens to 
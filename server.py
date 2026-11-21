import socket
import sys

HOST = ''    # '' = listen on all interfaces
PORT = 5789

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
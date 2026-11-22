import json
import os
import socket
import subprocess
import sys
import threading
from time import sleep
from typing import NoReturn

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5789

HELP_TEXT = """List of client commands:

- /help: displays this list of client commands

- /refresh: refreshes the list of online clients on the main menu

- /quit: disconnects the client from the server and exits the program

Entering anything not on this list into the client command prompt will result in an unknown command error."""

class Client:
    sock: socket.socket
    buffer: bytearray
    id: int
    username: str
    clients: list
    screen_lock: threading.Lock
    quitting: threading.Event
    server_gone: threading.Event

    def __init__(self, sock: socket.socket) -> None:
        """Initializes a new Client instance
        with a socket connection and an empty buffer."""

        self.sock = sock
        self.buffer = bytearray()
        self.id = -1
        self.username = ''
        self.clients = []
        self.screen_lock = threading.Lock()
        self.quitting = threading.Event()
        self.server_gone = threading.Event()


    def send_msg(self, msg: dict) -> None:
        """
        Sends a message from the client to the server.
        """
        text = json.dumps(msg) + "\n"
        self.sock.sendall(text.encode("utf-8"))

    def recv_msg(self):
        """
        Receives messages from the server and handles the buffer.
        """
        while (b"\n" not in self.buffer):
            try:
                chunk = self.sock.recv(4096)
            except OSError:
                return None

            if (chunk == b''):
                return None
            self.buffer += chunk

        line, buffer = self.buffer.split(b"\n", 1)
        self.buffer = buffer

        try:
            return json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            return self.recv_msg()

def askUsername() -> str:
    while (True):
        username = input("Please enter a username: \n").strip()[:10].strip()
        if (username != ''):
            break

    return username

def clearTerminal() -> None:
    try:
        if (os.name == "nt"):
            subprocess.run(["cmd", "/c", "cls"], check=True)
        else:
            subprocess.run(["clear"], check=True)
    except subprocess.CalledProcessError as e:
        fail(f"Command failed with exit code {e.returncode}\nError details: {e.stderr}")

def fail(reason: str | None) -> NoReturn:
    print(reason)
    sleep(5)
    sys.exit(1)

def drawMenu(client: Client):
    print(f"Welcome, {client.username}\nClient ID: {client.id}")
    print("======================")
    print("|    Online Users    |")
    print("======================")
    if (not client.clients):
        print("| No one else online |")
    for user in client.clients:
        print(f"| {user.get("username", "?"):<10} | {user.get("id", "?"):<5} |")
    print("======================")

def redrawMenu(client: Client, notice: str):
    with client.screen_lock:
        clearTerminal()
        drawMenu(client)
        if (notice != ""):
            print(notice)
        print("> ", end="", flush=True)

def recvLoop(client: Client):
    while (True):
        msg = client.recv_msg()

        # if server or client disconnects
        if (msg is None):
            if (client.quitting.is_set()):
                return
            client.server_gone.set()
            redrawMenu(client=client, notice="Server disconnected. Press Enter to exit.")
            return

        msg_type = msg.get("type")

        # broadcasts
        if (msg_type == "client_list"):
            new_list = msg.get("clients", [])
            if not isinstance(new_list, list):
                redrawMenu(client=client, notice="Server sent a bad client list.")
                continue

            client.clients = new_list
            redrawMenu(client=client, notice="")

        # server reported error
        elif (msg_type == "error"):
            redrawMenu(client=client, notice=f"Server error: {msg.get("exception", "unknown")}")

        else: continue

if __name__ == "__main__":

    clearTerminal()
    username = askUsername()

    try:
        sock = socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=5)
    except (ConnectionError, TimeoutError) as e:
        fail(f"Could not connect to {SERVER_HOST}:{SERVER_PORT}: {e}")

    sock.settimeout(None)
    client = Client(sock=sock)

    client.username = username

    msg = client.recv_msg()

    if (msg is None or (msg.get("type") != "connect")):
        fail(reason="Faulty connection")

    client.send_msg({"type": "register", "username": client.username})

    msg = client.recv_msg()

    if (msg is None):
        fail(reason="Server closed.")

    elif (msg.get("type") == "error"):
        fail(reason=msg.get("exception"))

    elif (msg.get("type") == "welcome"):
        client_id = msg.get("client_id")
        if not isinstance(client_id, int):
            fail(reason=f"Bad client_id from server: {client_id!r}")
        client.id = client_id

    else:
        fail(reason="Unexpected result, exiting.")

    thread = threading.Thread(target=recvLoop, args=(client,), daemon=True)
    thread.start()

    while (True):
        try:
            line = input().strip()
        except (KeyboardInterrupt, EOFError):
            line = "/quit"

        if (client.server_gone.is_set()):
            break

        parts = line.split()
        if not parts:
            redrawMenu(client, notice="")
            continue

        command = parts[0]
        if (command == "/help"):
            redrawMenu(client=client, notice=HELP_TEXT)
        elif (command == "/refresh"):
            try:
                client.send_msg({"type": "client_request", "command": "refresh"})
            except OSError:
                pass
        elif (command == "/quit"):
            try:
                client.quitting.set()
                client.sock.shutdown(socket.SHUT_RDWR)
                client.sock.close()
            except OSError:
                pass
            break

        else:
            redrawMenu(client, notice=f"Unknown command: {command}. Type `/help` for a list of commands.")

    print("Goodbye, exiting program...")
    if (client.quitting.is_set()):
        sys.exit(0)
    if (client.server_gone.is_set()):
        sys.exit(1)

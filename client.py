"""
Voice-Over-IP terminal client.

Connects to the VoIP server over TCP, registers a username, and displays a
live-updating menu of the other users currently online. The user interacts
with the client through slash commands typed at the "> " prompt (see
HELP_TEXT for the full list).

Protocol overview:
    All messages exchanged with the server are JSON objects encoded as UTF-8,
    one per line (newline-delimited JSON). Every message has a "type" field.

    Handshake:
        1. server -> client: {"type": "connect"}
        2. client -> server: {"type": "register", "username": <str>}
        3. server -> client: {"type": "welcome", "client_id": <int>}
                         or  {"type": "error", "exception": <str>}

    After the handshake:
        server -> client: {"type": "client_list", "clients": [{"username", "id"}, ...]}
        server -> client: {"type": "error", "exception": <str>}
        client -> server: {"type": "client_request", "command": "refresh"}

Threading model:
    The main thread reads user input and sends commands. A background daemon
    thread (recvLoop) receives server messages and redraws the menu. Both
    threads draw to the terminal, so screen output is guarded by
    Client.screen_lock.
"""

import json
import os
import socket
import subprocess
import sys
import threading
from time import sleep
from typing import NoReturn

# Address of the VoIP server to connect to.
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5789

# Text shown when the user enters the /help command.
HELP_TEXT = """List of client commands:

- /help: displays this list of client commands

- /refresh: refreshes the list of online clients on the main menu

- /quit: disconnects the client from the server and exits the program

Entering anything not on this list into the client command prompt will result in an unknown command error."""

class Client:
    """
    Holds the connection and session state for a single client.

    Attributes:
        sock: TCP socket connected to the server.
        buffer: Bytes received from the server that have not yet been parsed
            into a complete newline-terminated message.
        id: Client ID assigned by the server in the "welcome" message
            (-1 until registration succeeds).
        username: Display name chosen by the user.
        clients: Most recent list of online users sent by the server; each
            entry is a dict with "username" and "id" keys.
        screen_lock: Serializes terminal output between the main (input)
            thread and the receiver thread.
        quitting: Set when the user has asked to quit, so the receiver
            thread knows the disconnect was intentional.
        server_gone: Set by the receiver thread when the server closes the
            connection unexpectedly.
    """

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

        The message is serialized as JSON and terminated with a newline so the
        server can split the TCP stream into individual messages.

        Args:
            msg: The message to send; must be JSON-serializable and should
                include a "type" field.

        Raises:
            OSError: If the socket is closed or the send fails.
        """
        text = json.dumps(msg) + "\n"
        self.sock.sendall(text.encode("utf-8"))

    def recv_msg(self):
        """
        Receives messages from the server and handles the buffer.

        Reads from the socket until at least one complete newline-terminated
        message is buffered, then removes that line from the buffer and
        decodes it as JSON. Any extra bytes after the newline are kept in the
        buffer for the next call. Lines that are not valid JSON are skipped
        and the next message is read instead.

        Returns:
            The decoded message (normally a dict), or None if the connection
            was closed by the server or the socket raised an error.
        """
        # Keep reading until the buffer holds at least one full message.
        while (b"\n" not in self.buffer):
            try:
                chunk = self.sock.recv(4096)
            except OSError:
                return None

            # An empty read means the server closed the connection.
            if (chunk == b''):
                return None
            self.buffer += chunk

        # Split off the first complete line; keep the remainder buffered.
        line, buffer = self.buffer.split(b"\n", 1)
        self.buffer = buffer

        try:
            return json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            # Ignore malformed lines and try the next message.
            return self.recv_msg()

def askUsername() -> str:
    """
    Prompts the user for a username until a non-empty one is entered.

    Leading/trailing whitespace is removed and the name is truncated to at
    most 10 characters (the width of the username column in the menu).

    Returns:
        The cleaned-up username.
    """
    while (True):
        username = input("Please enter a username: \n").strip()[:10].strip()
        if (username != ''):
            break

    return username

def clearTerminal() -> None:
    """
    Clears the terminal screen using the platform's clear command
    ("cls" on Windows, "clear" elsewhere).

    Exits the program via fail() if the clear command returns an error.
    """
    try:
        if (os.name == "nt"):
            subprocess.run(["cmd", "/c", "cls"], check=True)
        else:
            subprocess.run(["clear"], check=True)
    except subprocess.CalledProcessError as e:
        fail(f"Command failed with exit code {e.returncode}\nError details: {e.stderr}")

def fail(reason: str | None) -> NoReturn:
    """
    Prints an error message, pauses so the user can read it, and exits the
    program with status code 1.

    Args:
        reason: The message to display before exiting.
    """
    print(reason)
    sleep(5)
    sys.exit(1)

def drawMenu(client: Client):
    """
    Prints the main menu: a welcome line with the client's username and ID,
    followed by a table of the other users currently online.

    Args:
        client: The client whose username, ID and online-user list are shown.
    """
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
    """
    Clears the screen and redraws the main menu, optionally followed by a
    notice, then shows the "> " input prompt again.

    Holds client.screen_lock while drawing so the main thread and the
    receiver thread don't interleave their output.

    Args:
        client: The client whose menu should be drawn.
        notice: Extra text to print under the menu (e.g. help text or an
            error message). Pass "" to show no notice.
    """
    with client.screen_lock:
        clearTerminal()
        drawMenu(client)
        if (notice != ""):
            print(notice)
        print("> ", end="", flush=True)

def recvLoop(client: Client):
    """
    Background receiver loop; runs on its own daemon thread.

    Continuously reads messages from the server and reacts to them:
        - "client_list": replaces client.clients and redraws the menu.
        - "error": redraws the menu with the server's error message.
        - anything else: ignored.

    The loop ends when the connection closes. If the user was quitting, it
    exits silently; otherwise it sets client.server_gone and tells the user
    the server disconnected.

    Args:
        client: The connected client to receive messages for.
    """
    while (True):
        msg = client.recv_msg()

        # If server or client disconnects
        if (msg is None):
            # Disconnect was caused by the user running /quit; nothing to report.
            if (client.quitting.is_set()):
                return
            # Otherwise the server went away; signal the main thread to exit.
            client.server_gone.set()
            redrawMenu(client=client, notice="Server disconnected. Press Enter to exit.")
            return

        msg_type = msg.get("type")

        # Broadcasts
        if (msg_type == "client_list"):
            new_list = msg.get("clients", [])
            # Reject malformed payloads instead of replacing the current list.
            if not isinstance(new_list, list):
                redrawMenu(client=client, notice="Server sent a bad client list.")
                continue

            client.clients = new_list
            redrawMenu(client=client, notice="")

        # If server reported error
        elif (msg_type == "error"):
            redrawMenu(client=client, notice=f"Server error: {msg.get("exception", "unknown")}")

        # Unrecognized message types are ignored.
        else: continue

if __name__ == "__main__":

    # Startup: get a username before connecting
    clearTerminal()
    username = askUsername()

    # Connect to the server (5 second timeout for the initial connect)
    try:
        sock = socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=5)
    except (ConnectionError, TimeoutError) as e:
        fail(f"Could not connect to {SERVER_HOST}:{SERVER_PORT}: {e}")

    # Switch back to blocking mode so recv() waits indefinitely for messages.
    sock.settimeout(None)
    client = Client(sock=sock)

    client.username = username

    # Handshake step 1: server greets client with a "connect" message
    msg = client.recv_msg()

    if (msg is None or (msg.get("type") != "connect")):
        fail(reason="Faulty connection")

    # Handshake step 2: register client username
    client.send_msg({"type": "register", "username": client.username})

    # Handshake step 3: expect "welcome" with the client's assigned ID, or an error
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

    # Start the background receiver; daemon so it won't block exit
    thread = threading.Thread(target=recvLoop, args=(client,), daemon=True)
    thread.start()

    # Main input loop: read and dispatch user commands
    while (True):
        try:
            line = input().strip()
        except (KeyboardInterrupt, EOFError):
            # Treat Ctrl+C / end-of-input as a request to quit.
            line = "/quit"

        # The receiver thread saw the server disconnect; stop reading input.
        if (client.server_gone.is_set()):
            break

        parts = line.split()
        # Blank input: just redraw the menu and prompt again.
        if not parts:
            redrawMenu(client, notice="")
            continue

        command = parts[0]
        if (command == "/help"):
            redrawMenu(client=client, notice=HELP_TEXT)
        elif (command == "/refresh"):
            # Ask the server to resend the client list; recvLoop redraws on reply.
            try:
                client.send_msg({"type": "client_request", "command": "refresh"})
            except OSError:
                pass
        elif (command == "/quit"):
            # Mark the quit as intentional before closing, so recvLoop
            # doesn't report it as a server disconnect.
            try:
                client.quitting.set()
                client.sock.shutdown(socket.SHUT_RDWR)
                client.sock.close()
            except OSError:
                pass
            break

        else:
            redrawMenu(client, notice=f"Unknown command: {command}. Type `/help` for a list of commands.")

    # Shutdown: exit 0 for a user quit, 1 if the server went away
    print("Goodbye, exiting program...")
    if (client.quitting.is_set()):
        sys.exit(0)
    if (client.server_gone.is_set()):
        sys.exit(1)

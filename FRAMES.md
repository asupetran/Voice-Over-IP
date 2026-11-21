# Frames for VoIP Signaling Protocol (TCP)
The server listens on port 5789 for new connections.

## Framing rules (both directions)
- Each message is one JSON object on one line, followed by a single \n.
- Encoding is UTF-8.
- Do not pretty-print (json.dumps(msg) with no indent=).
- Every message has a "type" field.

## Field types

| Field      | Type     | Notes |
|------------|----------|-------|
| `type`     | string   | Message type, see below |
| `status`   | string   | Result of the connection, e.g. `"successful"`. |
| `username` | string   | Username chosen by the client when registering. |
| `client_id`| integer  | The client's assigned port, ranging from 49152–65535. |
| `clients`  | object[] | An array of registered clients, each `{"username": string, "id": integer}`. Excludes the requestor/recipient. |
| `command`  | string   | Client command that requires server data/action. |
| `exception`| string   | The error message associated with any exceptions handled/thrown. |

## Message sequence

```
Client                         Server
  |------ TCP connect ----------->|
  |<----- connect ----------------|   (1)
  |------ register -------------->|   (2)
  |<----- welcome ----------------|   (3) port assigned here
  |<----- client_list ------------|   (4) sent right after welcome
  |                               |
  |------ client_request -------->|   (5) on /refresh
  |<----- client_list ------------|   (4)
```

## Messages

### 1. Connect (Server → Client)
Sent once, right after the TCP connection is accepted. It confirms that the client has reached a server that speaks this protocol. The client must not send `register` before receiving this.

```
{"type": "connect", "status": "successful"}\n
```

### 2. Register (Client → Server)
Sent once by the client after receiving `connect`. Registers a username with the server.

```
{"type": "register", "username": "<user>"}\n
```

### 3. Welcome (Server → Client)
Sent in response to `register`, after the server has assigned the client a port. `client_id` is the assigned port.

```
{"type": "welcome", "client_id": <client_id>}\n
```

### 4. Client List (Server → Client)
Sent immediately after `welcome`, and again in response to each `client_request` with `"command": "refresh"`.

The list contains only **registered** clients. It **excludes the client that receives it**.
For example, the list sent to client `49156` will not contain `49156`.

```
{"type": "client_list", "clients": [{"username": "<user1>", "id": <client_id>}, {"username": "<user2>", "id": <client_id>},...]}\n
```

An empty list is valid:

```
{"type": "client_list", "clients": []}\n
```

### 5. Client Request (Client → Server)
Sent by the client when a command needs data from the server.
In M2 the only command is `refresh`, which requests a new `client_list`.

```
{"type": "client_request", "command": "refresh"}\n
```

### 6. Error (Server -> Client)
Sent by the server whenever a message received from the client results in an error.
Errors include:
    - duplicate names
    - malformed JSON
    - timeouts
    - full port range

```
{"type" : "error", "exception":"<error_message>"}\n
```
This is for debugging purposes.

## Other stuff
- **Error Handling:** We have to decide how to handle each error later on.
- **Disconnects:** When a client disconnects from the server, the port should be released and become available to the next client that registers and connects.
- **Broadcasts:** When a client registers/disconnects, the server should broadcast an updated version of `client_list` to all registered clients.
- **Calls:** `call`, `accept`, `reject`, `end` messages are post M2 work.

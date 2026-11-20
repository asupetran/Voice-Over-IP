import socket
import sys

HOST = '127.0.0.1'
PORT = 5789

soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    soc.bind((HOST, PORT))

except socket.error as message:
    print('Bind failed. Error Code : '
        + str(message[0]) + ' Message '
        + message[1])
    sys.exit()

print('Socket binding operation completed')

soc.listen(9)

conn, address = soc.accept()
print('Connected with ' + address[0] + ':'
      + str(address[1]))

# hostname = socket.gethostname()
# ip = socket.gethostbyname(hostname)
# print(f'Hostname: {hostname}')
# print(f'IP: {ip}')
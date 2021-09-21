
def receive_data(socket, header_size, partial_prev_msg, buffer_size=65536):

    header_msg = bytes()
    prev_buffer_size = len(partial_prev_msg)

    if prev_buffer_size < header_size:
        header_msg = socket.recv(header_size - prev_buffer_size)
        if len(header_msg) != header_size:
            header_msg = partial_prev_msg + header_msg
            partial_prev_msg = bytes()

    elif prev_buffer_size >= header_size:
        header_msg = partial_prev_msg[:header_size]
        partial_prev_msg = partial_prev_msg[header_size:]

    msg_size = int(header_msg.decode("utf-8"))
    new_msg = partial_prev_msg
    partial_prev_msg = bytes()

    if msg_size:
        while True:
            if len(new_msg) < msg_size:
                new_msg += socket.recv(buffer_size)
            elif len(new_msg) > msg_size:
                partial_prev_msg = new_msg[msg_size:]
                new_msg = new_msg[:msg_size]
            if len(new_msg) == msg_size:
                break
        return new_msg, partial_prev_msg

    else:
        return None


def send_data(socket, header_size, msg_data):
    msg_len = len(msg_data)
    if msg_len:
        header = f"{msg_len:<{header_size}}"
        socket.send(bytes(header, "utf-8") + msg_data)


def retry(msg):
    check = True
    while check:
        choice = input(msg)
        if choice.lower() == "y":
            return True
        elif choice.lower() == "n":
            return False

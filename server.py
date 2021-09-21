import socket
import mss
import connection
import os
import ctypes
import string
import random
import requests
import re
import lz4.frame
from PIL import Image,  ImageGrab, ImageTk
from io import BytesIO
from threading import Thread
from multiprocessing import Process, Queue, freeze_support
from pynput.mouse import Button, Controller as Mouse_controller
from pynput.keyboard import Key, Controller as Keyboard_controller
from pyngrok import ngrok, conf
from pyngrok.conf import PyngrokConfig
import tkinter as tk
from tkinter.font import Font
from tkinter import ttk


def find_button(button_code, event_code):
    for key in button_code.keys():
        if event_code in key:
            return button_code.get(key)


def simulate(mouse, keyboard, button_code, key_map, event_code, msg):
    if event_code == -1:
        if len(msg) == 1:
            keyboard.press(msg)
        else:
            keyboard.press(key_map.get(msg))
    elif event_code == -2:
        if len(msg) == 1:
            keyboard.release(msg)
        else:
            keyboard.release(key_map.get(msg))
    elif event_code == 0:
        x, y = msg.split(",")
        mouse.position = (float(x), float(y))
    elif event_code == 7:
        dx, dy = msg.split(",")
        mouse.scroll(int(dx), int(dy))
    elif event_code in (1, 2, 3):
        mouse.press(find_button(button_code, event_code))
    elif event_code in (4, 5, 6):
        mouse.release(find_button(button_code, event_code))


def receive_events(sock, wallpaper_path):
    mouse = Mouse_controller()
    button_code = {(1, 4): Button.left, (2, 5): Button.right, (3, 6): Button.middle}

    keyboard = Keyboard_controller()
    key_map = dict()
    for key_enum in Key:
        key_map.setdefault(key_enum.name, key_enum)

    header_size = 2
    partial_prev_msg = bytes()

    try:
        while True:
            msg = connection.receive_data(sock, header_size, partial_prev_msg, 1024)
            if msg:
                data = msg[0].decode("utf-8")
                # print(f"Event data: {data}")
                event_code = int(data[:2])
                simulate(mouse, keyboard, button_code, key_map, event_code, data[2:])     # msg[0]--> new msg
                partial_prev_msg = msg[1]                                                 # msg[1]--> partial_prev_msg
    except (ConnectionAbortedError, ConnectionResetError, OSError) as exception_obj:
        print(exception_obj.strerror)
    finally:
        if wallpaper_path:
            set_desktop_background(wallpaper_path)
        else:
            print("Unfortunately wallpaper did not restored!")


def capture_screenshot(screenshot_queue, cli_width, cli_height):
    sct = mss.mss()
    sct.compression_level = 6
    mon = {"top": 0, "left": 0, "width": cli_width, "height": cli_height}
    capture = True
    while capture:
        # start_time = time.time()
        screenshot = sct.grab(mon)
        pil_image_obj = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        buffer = BytesIO()
        # if resize:
        #     pil_image_obj = pil_image_obj.resize(display_width, display_height)
        pil_image_obj.save(buffer, format='jpeg', quality=20)
        screenshot_queue.put(lz4.frame.compress(buffer.getvalue()))
        buffer.close()
        # print(f"Screenshot: {(time.time()-start_time):.4f}")


def get_from_queue_and_send(screenshot_queue, sock):
    header_size = 10
    try:
        while True:
            # start_time = time.time()
            jpeg_data = screenshot_queue.get()
            connection.send_data(sock, header_size, jpeg_data)
            # print(f"Upload: {(time.time() - start_time):.4f}")
    except (ConnectionAbortedError, ConnectionResetError, OSError):
        pass


def get_desktop_background_path():
    path_buffer = ctypes.create_unicode_buffer(512)
    success = ctypes.windll.user32.SystemParametersInfoW(115, len(path_buffer), path_buffer, 0)
    if success:
        return path_buffer.value
    else:
        return None


def set_desktop_background(path):
    if path or path == "":              # empty path sets it to black
        ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 0)


def send_screen():
    global process1, process2, process3, remote_client_socket
    # remote display socket
    remote_client_socket, address = server_socket.accept()
    disable_wallpaper = connection.receive_data(remote_client_socket, 2, bytes(), 1024)
    if disable_wallpaper[0].decode("utf-8") == "True":
        set_desktop_background("")
    print(f"Your Desktop is being remotely controlled now!")

    client_width, client_height = ImageGrab.grab().size
    resolution_msg = bytes(str(client_width) + "," + str(client_height), "utf-8")
    connection.send_data(remote_client_socket, 2, resolution_msg)  # send display resolution

    # resolution_msg = connection.receive_data(s, 2, bytes(), 1024)[0].decode("utf-8")
    # display_width, display_height = resolution_msg.split(",")
    # if (client_width, client_height) != (display_width, display_height):
    #     resize_option = True

    screenshot_sync_queue = Queue(1)
    process1 = Process(target=capture_screenshot, args=(screenshot_sync_queue, client_width, client_height), daemon=True
                       )
    process1.start()

    process2 = Process(target=get_from_queue_and_send, args=(screenshot_sync_queue, remote_client_socket), daemon=True)
    process2.start()

    process3 = Process(target=receive_events, args=(remote_client_socket, PATH))
    process3.start()


# #####---------->


def setup_ngrok():
    global url
    conf.DEFAULT_PYNGROK_CONFIG = PyngrokConfig(region="in", ngrok_path="{}".format(os.getenv('APPDATA') +
                                                                                    r'\RemoteApplication\ngrok.exe'))
    # pyngrok_config = PyngrokConfig(region="in")
    ngrok.set_auth_token("1h35E4ZgL4VsxAdkjKuXZ7EMhqG_5Bco3S82TGPYEm2NgpS3h")
    url = ngrok.connect(SERVER_PORT, "tcp", pyngrok_config=conf.DEFAULT_PYNGROK_CONFIG)
    computer_name = re.search(r"//(.+):", url).group(1)
    port_no = re.search(r":(\d+)", url).group(1)
    return computer_name, port_no


def create_listener_socket(server_ip, server_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((server_ip, server_port))
    sock.listen(1)
    return sock


def close_sockets():
    service_socket_list = [command_client_socket, remote_client_socket, chat_client_socket, file_client_socket]
    for sock in service_socket_list:
        if sock:
            sock.close()
    if url:
        ngrok.kill()        # ngrok.disconnect(url)  Only shuts the tunnel
    print("sockets cleaned up")


def process_cleanup():
    process_list = [process1, process2, process3]
    for process in process_list:
        if process:
            if process.is_alive():
                process.kill()
            process.join()
    print("process cleanup.Remote controlled capture stopped")


def start_listener(option_value):
    global remote_client_socket, server_socket, PASSWORD, login_thread
    # Disable buttons
    button_start.configure(state=tk.DISABLED)
    r2.configure(state=tk.DISABLED)
    r1.configure(state=tk.DISABLED)
    connection_frame.grid_forget()
    # label_initial.grid_forget()

    PASSWORD = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    if option_value == 1:
        server_ip = socket.gethostbyname(socket.gethostname())  # Local IP
        public_ip = requests.get('https://api.ipify.org').text

        # Show details
        # Local IP details

        local_ip_label.grid(row=0, column=0, sticky=tk.W, pady=2)

        local_ip_text.insert(1.0, "{:<15} (Works when on same wifi or network)".format(server_ip))
        local_ip_text.configure(font=myFont_normal, state='disabled')
        local_ip_text.grid(row=0, column=1, sticky=tk.W, pady=2)

        # Public IP details
        public_ip_label.grid(row=1, column=0, sticky=tk.W, pady=2)

        public_ip_text.insert(1.0, "{:<15} (Works when on different network)"
                              .format(public_ip))
        public_ip_text.configure(font=myFont_normal, state='disabled')
        public_ip_text.grid(row=1, column=1, sticky=tk.W, pady=2)

        # Port details

        port_label.grid(row=2, column=0, sticky=tk.W, pady=2)

        port_text.insert(1.0, "{:<15}".format(SERVER_PORT))
        port_text.configure(font=myFont_normal, state='disabled')
        port_text.grid(row=2, column=1, sticky=tk.W, pady=2)

        # Password Details
        pass_label.grid(row=3, column=0, sticky=tk.W, pady=2)

        pass_text.insert(1.0, "{:<15}".format(PASSWORD))
        pass_text.configure(font=myFont_normal, state='disabled')
        pass_text.grid(row=3, column=1, sticky=tk.W, pady=2)

        button_stop.grid(row=4, column=0, columnspan=2, sticky=tk.N, pady=(30, 2))

    else:
        server_ip = "127.0.0.1"
        server_name, port = setup_ngrok()

        # Show details
        # Computer name details
        name_label.grid(row=0, column=0, sticky=tk.W, pady=2)

        name_text.insert(1.0, "{:<15} (Works in any network scenario)".format(server_name))
        name_text.configure(font=myFont_normal, state='disabled')
        name_text.grid(row=0, column=1, sticky=tk.W, pady=2)

        # Port details
        port_label.grid(row=1, column=0, sticky=tk.W, pady=2)

        port_text.insert(1.0, "{:<15}".format(port))
        port_text.configure(font=myFont_normal, state='disabled')
        port_text.grid(row=1, column=1, sticky=tk.W, pady=2)

        # Password Details
        pass_label.grid(row=2, column=0, sticky=tk.W, pady=2)

        pass_text.insert(1.0, "{:<15}".format(PASSWORD))
        pass_text.configure(font=myFont_normal, state='disabled')
        pass_text.grid(row=2, column=1, sticky=tk.W, pady=2)

        button_stop.grid(row=3, column=0, columnspan=2, sticky=tk.N, pady=(30, 2))

    server_socket = create_listener_socket(server_ip, SERVER_PORT)
    login_thread = Thread(target=login, name="login_thread", args=(server_socket,), daemon=True)
    login_thread.start()

    # Enable button
    details_frame.grid(row=1, column=0, padx=40, pady=40)
    button_stop.configure(state=tk.NORMAL)
    # print("Remote desktop function can be executed now")
    # remote_display()


def stop_listener():
    global server_socket, remote_client_socket, url
    if CLIENT_CONNECTED:
        connection.send_data(command_client_socket, COMMAND_HEADER_SIZE, bytes("disconnect", "utf-8"))
    # Closing all the sockets
    if server_socket:
        server_socket.close()
    close_sockets()
    process_cleanup()

    if radio_var.get() == 1:
        local_ip_label.grid_forget()
        local_ip_text.grid_forget()
        local_ip_text.configure(state="normal")
        local_ip_text.delete('1.0', tk.END)
        public_ip_label.grid_forget()
        public_ip_text.grid_forget()
        public_ip_text.configure(state="normal")
        public_ip_text.delete('1.0', tk.END)
    elif radio_var.get() == 2:
        name_label.grid_forget()
        name_text.grid_forget()
        name_text.configure(state="normal")
        name_text.delete('1.0', tk.END)

    # Enable buttons
    connection_frame.grid(row=1, column=0, padx=120, pady=80, sticky=tk.W)
    button_start.configure(state=tk.NORMAL)
    r2.configure(state=tk.NORMAL)
    r1.configure(state=tk.NORMAL)
    # label_initial.grid(row=0, column=0, pady=35, sticky=tk.N)

    # Disable button
    button_stop.configure(state=tk.DISABLED)
    details_frame.grid_forget()
    my_notebook.hide(1)

    port_label.grid_forget()
    port_text.grid_forget()
    port_text.configure(state="normal")
    port_text.delete('1.0', tk.END)

    pass_label.grid_forget()
    pass_text.grid_forget()
    pass_text.configure(state="normal")
    pass_text.delete('1.0', tk.END)


# def display_and_get_server_info():
#     print(">>>   Remote Desktop Application   (Coded By: 'ADARSH SINGH' @Overflow) <<<")
#     print("\n")
#     print("Connection mode:")
#     print("1)IP              (Good Performance)")
#     print("2)Computer name   (Normal Performance)")
#
#     connection_mode = True
#     server_ip = str()
#     server_port = 1234
#     while connection_mode:
#         print("\n")
#         choice = input("Choose an option(1 or 2):")
#         if choice == "1" or choice == "2":
#             os.system("cls")
#             print(">>NOTE: This program will allow you to CONTROL other computer Desktop.")
#             print("\n")
#             print(">>Remote control details")
#             if choice == "1":
#                 server_ip = socket.gethostbyname(socket.gethostname())          # Local IP
#                 public_ip = requests.get('https://api.ipify.org').text
#                 print(f"LOCAL IP      --> {server_ip:12} (Works when on same wifi or network)")
#                 print(f"PUBLIC IP     --> {public_ip:12} (Works when on different network and port forwarding is done)
#                 ")
#                 print(f"Port no       --> {server_port}")
#             elif choice == "2":
#                 server_ip = "127.0.0.1"
#                 server_name, port = setup_ngrok()
#                 print(f"Computer name --> {server_name} (Works in any network scenario)")
#                 print(f"Port no       --> {port}")
#             print(f"Password      --> {PASSWORD}")
#             print("\n")
#             print("Waiting for the other computer to connect...")
#             connection_mode = False
#         else:
#             print("Invalid option.Choose either 1 or 2")
#     return server_ip


def login(sock):
    global command_client_socket, remote_client_socket, chat_client_socket, file_client_socket, thread1, \
        CLIENT_CONNECTED
    accept = True
    try:
        while accept:
            print("\n")
            print("Listening for incoming connections")
            command_client_socket, address = sock.accept()
            print(f"Login request from {address[0]}...")
            pass_recv = connection.receive_data(command_client_socket, 2, bytes(), 1024)[0].decode("utf-8")
            if pass_recv == PASSWORD:
                connection.send_data(command_client_socket, 2, bytes("1", "utf-8"))  # success_code--> 1
                # chat socket
                chat_client_socket, address = sock.accept()
                # file transfer socket
                file_client_socket, address = sock.accept()
                print("\n")
                print(f"Connection from {address[0]} has been established!")
                # thread for listening to commands
                thread1 = Thread(target=listen_for_commands, name="listener_for_commands", daemon=True)
                thread1.start()
                CLIENT_CONNECTED = True
                # thread for chat
                recv_chat_msg_thread = Thread(target=receive_chat_message, name="recv_chat_msg_thread", daemon=True)
                recv_chat_msg_thread.start()
                # enable button frame

                my_notebook.add(chat_frame, text=" Chat ")
                accept = False
            else:
                connection.send_data(command_client_socket, 2, bytes("0", "utf-8"))  # failure_code--> 0
                print(f"Wrong password entered by {address[0]}")
                command_client_socket.close()
    except (ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)


def listen_for_commands():
    global login_thread, CLIENT_CONNECTED
    listen = True
    try:
        while listen:
            msg = connection.receive_data(command_client_socket, COMMAND_HEADER_SIZE, bytes(), 1024)[0].decode("utf-8")
            print(f"Message received:{msg}")
            if msg == "start_capture":
                send_screen()
            elif msg == "stop_capture":
                process_cleanup()
            elif msg == "disconnect":
                listen = False
                print("Disconnect message received")
    except (ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)
    except ValueError:
        pass
    finally:
        my_notebook.hide(1)
        CLIENT_CONNECTED = False
        close_sockets()
        process_cleanup()
        login_thread = Thread(target=login, name="login_thread", args=(server_socket,), daemon=True)
        login_thread.start()
        print("Thread1 automatically exits")


def add_text_chat_display_widget(msg, name):
    text_chat_widget.configure(state=tk.NORMAL)
    text_chat_widget.insert(tk.END, "\n")
    text_chat_widget.insert(tk.END, name + ": " + msg)
    text_chat_widget.configure(state="disabled")


def send_chat_message(event):
    try:
        msg = input_text_widget.get()
        if msg and msg.strip() != "":
            input_text_widget.delete(0, "end")
            connection.send_data(chat_client_socket, CHAT_HEADER_SIZE, bytes(msg, "utf-8"))
            add_text_chat_display_widget(msg, LOCAL_CHAT_NAME)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)


def receive_chat_message():
    try:
        while True:
            msg = connection.receive_data(chat_client_socket, CHAT_HEADER_SIZE, bytes())[0].decode("utf-8")
            add_text_chat_display_widget(msg, REMOTE_CHAT_NAME)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)
    except ValueError:
        pass


def download_file(filename):
    partial_prev_msg = bytes()
    msg = connection.receive_data(file_client_socket, FILE_HEADER_SIZE, partial_prev_msg)
    file_size = int(msg[0].decode("utf-8"))
    msg = connection.receive_data(file_client_socket, FILE_HEADER_SIZE, msg[1])
    file_mode = msg[0].decode("utf-8")
    partial_prev_msg = msg[1]
    total_data_size = int()
    with open(filename, file_mode) as f:
        while total_data_size < file_size:
            msg = connection.receive_data(file_client_socket, FILE_HEADER_SIZE, partial_prev_msg)
            data = msg[0]
            partial_prev_msg = msg[1]
            if file_mode == "w" and data:
                f.write(data.decode("utf-8"))
            elif file_mode == "wb" and data:
                f.write(data)
            total_data_size += len(data)


def scan_dir():
    try:
        obj = os.scandir(PATH)
        return obj
    except PermissionError:
        print("No permission to acces this resource")
        back_button("function")
        return None


# def toggle_event_log():
#     global status_event_log
#     if status_event_log == 1:
#         event_frame.grid_forget()
#         status_event_log = 0
#     elif status_event_log == 0:
#         event_frame.grid(row=3, column=0, columnspan=2, padx=40, pady=5, sticky=tk.W)
#         status_event_log = 1


if __name__ == "__main__":
    freeze_support()

    PATH = get_desktop_background_path()

    server_socket = None
    command_client_socket = None
    remote_client_socket = None
    chat_client_socket = None
    file_client_socket = None
    browse_file_client_socket = None

    thread1 = None
    login_thread = None
    process1 = None
    process2 = None
    process3 = None

    PASSWORD = str()
    url = str()
    SERVER_PORT = 1234
    CHAT_HEADER_SIZE = 10
    FILE_HEADER_SIZE = 10
    COMMAND_HEADER_SIZE = 2
    CLIENT_CONNECTED = False
    LOCAL_CHAT_NAME = "Me"
    REMOTE_CHAT_NAME = "Remote Box"

    # Create Root Window
    root = tk.Tk()
    root.title("Remote Box")
    root.iconbitmap("logo.ico")
    root.resizable(False, False)

    # My fonts
    myFont_title = Font(family="Helvetica", size=14, weight="bold")
    myFont_title_normal = Font(family="Helvetica", size=13, weight="bold")
    myFont_normal = Font(family="Helvetica", size=13)

    # My Notebook
    my_notebook = ttk.Notebook(root)
    my_notebook.grid(row=0, column=0, pady=5, columnspan=2)

    # <------Connection Tab -------------->
    listener_frame = tk.LabelFrame(my_notebook, bd=0)
    listener_frame.grid(row=0, column=0)

    # Logo Label
    img_logo = ImageTk.PhotoImage(Image.open("logo.png"))
    label_note = tk.Label(listener_frame, image=img_logo, anchor=tk.CENTER)
    label_note.grid(row=0, column=0, padx=200, pady=5, columnspan=2, sticky=tk.N)

    # Connection Frame
    connection_frame = tk.LabelFrame(listener_frame, text="Connection Mode", padx=90, pady=30)
    connection_frame.configure(font=myFont_title)
    connection_frame.grid(row=1, column=0, padx=120, pady=80, sticky=tk.W)

    # Radio button
    radio_var = tk.IntVar()
    radio_var.set(1)
    r1 = tk.Radiobutton(connection_frame, text="IP", variable=radio_var, value=1)
    r1.configure(font=myFont_normal)
    r1.grid(row=0, column=0, sticky=tk.W, padx=20, pady=5)

    r2 = tk.Radiobutton(connection_frame, text="Computer Name", variable=radio_var, value=2)
    r2.configure(font=myFont_normal)
    r2.grid(row=1, column=0, sticky=tk.W, padx=20, pady=5)

    # Start listener
    button_start = tk.Button(connection_frame, text="Start Listener", padx=2, pady=1,
                             command=lambda: start_listener(radio_var.get()))
    button_start.configure(font=myFont_title_normal)
    button_start.grid(row=2, column=0, sticky=tk.W, pady=(20, 2), padx=(20, 2))

    # Details Frame
    details_frame = tk.LabelFrame(listener_frame, text="Allow Remote Access", padx=20, pady=20, labelanchor=tk.NE)
    details_frame.configure(font=myFont_title)
    details_frame.grid(row=1, column=0, padx=40, pady=40)

    # Details label and text
    # Local IP details
    local_ip_label = tk.Label(details_frame, text="LOCAL IP      :", padx=5, pady=5)
    local_ip_label.configure(font=myFont_title_normal)
    local_ip_text = tk.Text(details_frame, pady=5, width=47, height=1, background="#e6e6e6", bd=0)
    # Public IP details
    public_ip_label = tk.Label(details_frame, text="PUBLIC IP     :", padx=5, pady=5)
    public_ip_label.configure(font=myFont_title_normal)
    public_ip_text = tk.Text(details_frame, pady=5, width=47, height=1, background="#e6e6e6", bd=0)
    # Computer name details
    name_label = tk.Label(details_frame, text="Computer name :", padx=5, pady=5)
    name_label.configure(font=myFont_title_normal)
    name_text = tk.Text(details_frame, pady=5, width=47, height=1, background="#e6e6e6", bd=0)
    # Port details
    port_label = tk.Label(details_frame, text="Port no         :", padx=5, pady=5)
    port_label.configure(font=myFont_title_normal)
    port_text = tk.Text(details_frame, pady=5, width=47, height=1, background="#e6e6e6", bd=0)
    # Password Details
    pass_label = tk.Label(details_frame, text="Password     :", padx=5, pady=5)
    pass_label.configure(font=myFont_title_normal)
    pass_text = tk.Text(details_frame, pady=5, width=47, height=1, background="#e6e6e6", bd=0)

    # stop listener
    button_stop = tk.Button(details_frame, text="Stop Listener", padx=2, pady=1,
                            command=lambda: stop_listener())
    button_stop.configure(font=myFont_title_normal, state="disabled")

    # Disable details frame
    details_frame.grid_forget()

    # Show/Hide Event Logs button
    # event_log_button = tk.Button(buttons_frame, text="Show/Hide Event Logs", padx=2, pady=2, command=toggle_event_log)
    # event_log_button.configure(font=myFont_normal)
    # event_log_button.grid(row=0, column=4, sticky=tk.W, padx=5)

    # <-------------Event log Tab --------------------->
    # Event_log Frame
    event_frame = tk.LabelFrame(my_notebook, text="Event Log", padx=20, pady=20, relief=tk.FLAT)
    event_frame.configure(font=myFont_title)
    event_frame.grid(row=3, column=0, columnspan=2, padx=40, pady=5, sticky=tk.W)

    # Scroll bar to event frame
    scroll_widget = tk.Scrollbar(event_frame)
    scroll_widget.grid(row=0, column=1, sticky=tk.N + tk.S)

    # Text Widget
    text_1 = tk.Text(event_frame, width=50, height=7, font=("Helvetica", 13), padx=10, pady=10,
                     yscrollcommand=scroll_widget.set)
    text_1.insert(1.0, "By Default Show Event Logs")
    text_1.configure(state='disabled')
    text_1.grid(row=0, column=0)

    scroll_widget.config(command=text_1.yview)

    # Status Label
    label_status = tk.Label(root, text="Listening for incoming connections...", relief=tk.SUNKEN, bd=0, anchor=tk.E,
                            padx=10)
    label_status.configure(font=myFont_normal)
    label_status.grid(row=3, column=0, columnspan=2, sticky=tk.W + tk.E)

    # <------Chat Tab -------------->
    chat_frame = tk.LabelFrame(my_notebook, padx=20, pady=20, bd=0)
    chat_frame.grid(row=0, column=0, sticky=tk.N)

    # text_frame = tk.LabelFrame(chat_frame, bd=0)
    # text_frame.grid(row=0, column=0)

    # Scroll bar to event frame
    scroll_chat_widget = tk.Scrollbar(chat_frame)
    scroll_chat_widget.grid(row=0, column=1, sticky=tk.N + tk.S)

    # Text Widget
    text_chat_widget = tk.Text(chat_frame, width=50, height=20, font=("Helvetica", 14), padx=10, pady=10,
                               yscrollcommand=scroll_chat_widget.set)
    text_chat_widget.configure(state='disabled')
    text_chat_widget.grid(row=0, column=0, sticky=tk.N)

    scroll_chat_widget.config(command=text_chat_widget.yview)

    # Frame for input text
    input_text_frame = tk.LabelFrame(chat_frame, pady=5, bd=0)
    input_text_frame.grid(row=1, column=0, sticky=tk.W)

    # Text Widget
    input_text_widget = tk.Entry(input_text_frame, width=50)
    input_text_widget.configure(font=("Helvetica", 14))
    input_text_widget.bind("<Return>", send_chat_message)
    input_text_widget.grid(row=0, column=0, pady=10, sticky=tk.W)

    # Create Tab style
    tab_style = ttk.Style()
    tab_style.configure('TNotebook.Tab', font=('Helvetica', '13', 'bold'))

    # Tab Creation
    my_notebook.add(listener_frame, text=" Connection ")
    my_notebook.add(chat_frame, text=" Chat ")
    my_notebook.add(event_frame, text=" Event Logs ")

    # Hide Tab
    my_notebook.hide(1)

    root.mainloop()

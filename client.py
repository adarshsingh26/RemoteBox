import socket
import mss
import connection
import sys
import os
import time
import ctypes
import lz4.frame
from PIL import Image,  ImageGrab, ImageTk
from io import BytesIO
from threading import Thread
from multiprocessing import Process, Queue, freeze_support
from pynput.mouse import Button, Controller as Mouse_controller
from pynput.keyboard import Key, Controller as Keyboard_controller
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
        print("Program will exit in 10 sec...")
        # time.sleep(10)
        # sock.close()


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


def login():
    # resize_option = False
    global command_server_socket, remote_server_socket, chat_server_socket, file_server_socket, thread1, server_ip, \
        server_port

    execute = True
    server_ip = name_entry.get()
    server_port = int(port_entry.get())
    server_pass = pass_entry.get()
    print(server_ip, server_port, server_pass)
    while execute:
        try:
            command_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            command_server_socket.connect((server_ip, server_port))
            server_pass = bytes(server_pass, "utf-8")
            connection.send_data(command_server_socket, 2, server_pass)      # send password
            login_response = connection.receive_data(command_server_socket, 2, bytes(), 1024)

            if login_response[0].decode("utf-8") != "1":
                print("WRONG Password!..")
            else:
                # chat socket
                chat_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                chat_server_socket.connect((server_ip, server_port))

                # file transfer socket
                file_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                file_server_socket.connect((server_ip, server_port))

                print("\n")
                print("Connected to the remote computer!")
                execute = False

                thread1 = Thread(target=listen_for_commands, daemon=True)
                thread1.start()
                # thread for chat
                recv_chat_msg_thread = Thread(target=receive_chat_message, name="recv_chat_msg_thread", daemon=True)
                recv_chat_msg_thread.start()

                # Enable
                disconnect_button.configure(state="normal")
                my_notebook.add(chat_frame, text=" Chat ")
                # Disable
                name_entry.configure(state="disabled")
                port_entry.configure(state="disabled")
                pass_entry.configure(state="disabled")
                connect_button.configure(state="disabled")

        except OSError as e:
            print(e.strerror)
            execute = False


def disconnect(caller):
    if caller == "button":
        connection.send_data(command_server_socket, COMMAND_HEADER_SIZE, bytes("disconnect", "utf-8"))
    if command_server_socket:
        command_server_socket.close()
    if remote_server_socket:
        remote_server_socket.close()
    if chat_server_socket:
        chat_server_socket.close()
    if file_server_socket:
        file_server_socket.close()
    print("Closed all the sockets")

    # Enable
    name_entry.configure(state="normal")
    port_entry.configure(state="normal")
    pass_entry.configure(state="normal")
    connect_button.configure(state="normal")

    # Disable
    disconnect_button.configure(state="disabled")
    my_notebook.hide(1)


def send_screen():
    global process1, process2, process3, remote_server_socket
    # remote display socket
    remote_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    remote_server_socket.connect((server_ip, server_port))
    disable_wallpaper = connection.receive_data(remote_server_socket, 2, bytes(), 1024)
    if disable_wallpaper[0].decode("utf-8") == "True":
        set_desktop_background("")
    print(f"Your Desktop is being remotely controlled now!")

    client_width, client_height = ImageGrab.grab().size
    resolution_msg = bytes(str(client_width) + "," + str(client_height), "utf-8")
    connection.send_data(remote_server_socket, 2, resolution_msg)  # send display resolution

    # resolution_msg = connection.receive_data(s, 2, bytes(), 1024)[0].decode("utf-8")
    # display_width, display_height = resolution_msg.split(",")
    # if (client_width, client_height) != (display_width, display_height):
    #     resize_option = True

    screenshot_sync_queue = Queue(1)
    process1 = Process(target=capture_screenshot, args=(screenshot_sync_queue, client_width, client_height), daemon=True
                       )
    process1.start()

    process2 = Process(target=get_from_queue_and_send, args=(screenshot_sync_queue, remote_server_socket), daemon=True)
    process2.start()

    process3 = Process(target=receive_events, args=(remote_server_socket, PATH))
    process3.start()
    # process3.join()


def listen_for_commands():
    listen = True
    try:
        while listen:
            msg = connection.receive_data(command_server_socket, COMMAND_HEADER_SIZE, bytes(), 1024)[0].decode("utf-8")
            print(f"Message received:{msg}")
            if msg == "start_capture":
                send_screen()
            elif msg == "stop_capture":
                process1.kill()
                process1.join()
                process2.kill()
                process2.join()
                process3.kill()
                process3.join()
                print("process cleanup.Remote controlled capture stopped")
            elif msg == "disconnect":
                disconnect("command_function")
                listen = False
                print("Disconnect message received")
    except (ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)
    except ValueError:
        pass
    finally:
        disconnect("command_function")
        my_notebook.hide(1)
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
            connection.send_data(chat_server_socket, CHAT_HEADER_SIZE, bytes(msg, "utf-8"))
            add_text_chat_display_widget(msg, LOCAL_CHAT_NAME)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)


def receive_chat_message():
    try:
        while True:
            msg = connection.receive_data(chat_server_socket, CHAT_HEADER_SIZE, bytes())[0].decode("utf-8")
            add_text_chat_display_widget(msg, REMOTE_CHAT_NAME)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)
    except ValueError:
        pass


if __name__ == "__main__":
    freeze_support()

    PATH = get_desktop_background_path()
    command_server_socket = None
    remote_server_socket = None
    chat_server_socket = None
    file_server_socket = None

    thread1 = None
    process1 = None
    process2 = None
    process3 = None

    server_ip = str()
    server_port = int()
    COMMAND_HEADER_SIZE = 2
    CHAT_HEADER_SIZE = 10
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
    my_notebook.grid(row=0, column=0, pady=5)

    # <------Connection Tab -------------->
    connection_frame = tk.LabelFrame(my_notebook, padx=150, pady=5, bd=0)
    connection_frame.grid(row=0, column=0, padx=40, pady=40, sticky=tk.N)

    # Logo Label
    img_logo = ImageTk.PhotoImage(Image.open("logo.png"))
    label_note = tk.Label(connection_frame, image=img_logo, anchor=tk.CENTER)
    label_note.grid(row=0, column=0, pady=5, columnspan=2, sticky=tk.N)

    # Form elements frame
    form_frame = tk.LabelFrame(connection_frame, text="Allow Remote Control", padx=20, pady=5)
    form_frame.configure(font=myFont_title)
    form_frame.grid(row=1, column=0, padx=40, pady=(60, 40), sticky=tk.N)

    # Form for Input data
    name_label = tk.Label(form_frame, text="Computer Name/IP", padx=5, pady=5)
    name_label.configure(font=myFont_title_normal)
    name_label.grid(row=0, column=0, pady=5, columnspan=2, sticky=tk.W)

    name_entry = tk.Entry(form_frame, width=20)
    name_entry.configure(font=myFont_normal)
    name_entry.grid(row=1, column=0, pady=5, columnspan=2, sticky=tk.N)

    port_label = tk.Label(form_frame, text="Port", padx=5, pady=5)
    port_label.configure(font=myFont_title_normal)
    port_label.grid(row=2, column=0, pady=5, columnspan=2, sticky=tk.W)

    port_entry = tk.Entry(form_frame, width=20)
    port_entry.configure(font=myFont_normal)
    port_entry.grid(row=3, column=0, pady=5, columnspan=2, sticky=tk.N)

    pass_label = tk.Label(form_frame, text="Password", padx=5, pady=5)
    pass_label.configure(font=myFont_title_normal)
    pass_label.grid(row=4, column=0, pady=5, columnspan=2, sticky=tk.W)

    pass_entry = tk.Entry(form_frame, width=20)
    pass_entry.configure(font=myFont_normal)
    pass_entry.grid(row=5, column=0, pady=5, columnspan=2, sticky=tk.N)

    # Button frame
    button_frame = tk.LabelFrame(form_frame, padx=2, pady=5, bd=0)
    button_frame.grid(row=6, column=0, padx=5, pady=2)

    # Connect and Disconnect button
    connect_button = tk.Button(button_frame, text="Connect", padx=4, pady=1, command=login)
    connect_button.configure(font=myFont_title_normal)
    connect_button.grid(row=0, column=0, sticky=tk.N, padx=5, pady=5)

    disconnect_button = tk.Button(button_frame, text="Disconnect", padx=2, pady=1, command=lambda: disconnect("button"))
    disconnect_button.configure(font=myFont_title_normal, state=tk.DISABLED)
    disconnect_button.grid(row=0, column=1, sticky=tk.N, padx=5, pady=5)

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
    text_chat_widget.insert(1.0, "By Default Share Funny Jokes")
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

    # Status Label
    label_status = tk.Label(root, text="Listening for incoming connections...", relief=tk.SUNKEN, bd=0, anchor=tk.E,
                            padx=10)
    label_status.configure(font=myFont_normal)
    label_status.grid(row=3, column=0, columnspan=2, sticky=tk.W + tk.E)

    # Create Tab style
    tab_style = ttk.Style()
    tab_style.configure('TNotebook.Tab', font=('Helvetica', '13', 'bold'))

    # Tab Creation
    my_notebook.add(connection_frame, text=" Connection ")
    my_notebook.add(chat_frame, text=" Chat ")

    # Hide Tab
    my_notebook.hide(1)

    root.mainloop()


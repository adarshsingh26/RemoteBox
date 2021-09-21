import socket
from PIL import Image, ImageGrab, ImageTk
import pygetwindow
import time
import os
import string
import random
import win32gui
import requests
import lz4.frame
import re
from io import BytesIO
from threading import Thread
from multiprocessing import freeze_support, Process, Queue as Multiprocess_queue
from pynput.keyboard import Listener as Key_listener
from pynput.mouse import Button, Listener as Mouse_listener
from pyngrok import ngrok, conf
from pyngrok.conf import PyngrokConfig
import tkinter as tk
from tkinter.font import Font
from tkinter import ttk, messagebox
import connection


# execute_thread = True


def send_event(msg, sock):
    connection.send_data(sock, 2, msg)


def get_mouse_data_from_queue(sock, event_queue, resize, cli_width, cli_height, dis_width, dis_height):
    while True:
        event_code = event_queue.get()
        x = event_queue.get()
        y = event_queue.get()
        x, y, within_display = check_within_display(x, y, resize, cli_width, cli_height, dis_width, dis_height)
        if event_code == 0 or event_code == 7:
            if within_display:
                if event_code == 7:
                    x = event_queue.get()
                    y = event_queue.get()
                msg = bytes(f"{event_code:<2}" + str(x) + "," + str(y), "utf-8")
                send_event(msg, sock)
                # print(f"Event data: {msg}")
        elif event_code in range(1, 10):
            if within_display:
                msg = bytes(f"{event_code:<2}", "utf-8")
                send_event(msg, sock)


def scale_x_y(x, y, cli_width, cli_height, dis_width, dis_height):
    scale_x = cli_width / dis_width
    scale_y = cli_height / dis_height
    x *= scale_x
    y *= scale_y
    return round(x, 1), round(y, 1)


def check_within_display(x, y, resize, cli_width, cli_height, dis_width, dis_height):
    active_window = pygetwindow.getWindowsWithTitle(f"Remote Desktop")
    if active_window and (len(active_window) == 1):
        x, y = win32gui.ScreenToClient(active_window[0]._hWnd, (x, y))
        if (0 <= x <= dis_width) and (0 <= y <= dis_height):
            if resize:
                x, y = scale_x_y(x, y, cli_width, cli_height, dis_width, dis_height)
            return x, y, True
    return x, y, False


def on_move(x, y):
    # print("Mouse listener working")
    mouse_event_queue.put(0)  # event_code
    mouse_event_queue.put(x)
    mouse_event_queue.put(y)


def on_click(x, y, button, pressed):
    if pressed:  # mouse down(press)
        mouse_event_queue.put(button_code.get(button)[0])
        mouse_event_queue.put(x)
        mouse_event_queue.put(y)
    else:  # mouse up(release)
        mouse_event_queue.put(button_code.get(button)[1])
        mouse_event_queue.put(x)
        mouse_event_queue.put(y)


def on_scroll(x, y, dx, dy):
    mouse_event_queue.put(7)   # event_code
    mouse_event_queue.put(x)
    mouse_event_queue.put(y)
    mouse_event_queue.put(dx)
    mouse_event_queue.put(dy)


def key_events(key, event_code):
    active_window = pygetwindow.getActiveWindow()
    if active_window:
        # print("Keyboard listener working")
        if active_window.title == f"Remote Desktop":
            try:
                if key.char:
                    msg = bytes(event_code + key.char, "utf-8")  # alphanumeric key
                    send_event(msg, remote_client_socket)
            except AttributeError:
                msg = bytes(event_code + key.name, "utf-8")  # special key
                send_event(msg, remote_client_socket)


def on_press(key):
    key_events(key, "-1")


def on_release(key):
    key_events(key, "-2")


def recv_and_put_into_queue(client_socket, jpeg_queue):
    header_size = 10
    partial_prev_msg = bytes()

    try:
        while True:
            msg = connection.receive_data(client_socket, header_size, partial_prev_msg)
            if msg:
                jpeg_queue.put(lz4.frame.decompress(msg[0]))  # msg[0]--> new msg
                partial_prev_msg = msg[1]  # msg[1]--> partial_prev_msg
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)
    except ValueError:
        pass
    finally:
        print("Thread2 automatically exits")


def display_data(jpeg_queue, status_queue, dis_width, dis_height, resize):
    import os
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
    import pygame
    pygame.init()
    display_surface = pygame.display.set_mode((dis_width, dis_height))
    pygame.display.set_caption(f"Remote Desktop")
    clock = pygame.time.Clock()
    display = True

    while display:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                status_queue.put("stop")
                pygame.quit()
                return
        # start_time = time.time()
        jpeg_buffer = BytesIO(jpeg_queue.get())
        img = Image.open(jpeg_buffer)
        py_image = pygame.image.frombuffer(img.tobytes(), img.size, img.mode)
        # print(f"Display: {(time.time() - start_time):.4f}")
        if resize:
            py_image = pygame.transform.scale(py_image, (dis_width, dis_height))
            # img = img.resize((display_width, display_height))
        jpeg_buffer.close()
        display_surface.blit(py_image, (0, 0))
        print(f"Fps: {int(clock.get_fps())}")
        pygame.display.flip()
        clock.tick(60)


def compare_and_compute_resolution(cli_width, cli_height, ser_width, ser_height):
    resolution_tuple = ((7680, 4320), (3840, 2160), (2560, 1440), (1920, 1080), (1600, 900), (1366, 768), (1280, 720),
                        (1152, 648), (1024, 576), (2560, 1600), (1920, 1200), (1680, 1050), (1440, 900), (1280, 800),
                        (2048, 1536), (1920, 1440), (1856, 1392), (1600, 1200), (1440, 1080), (1400, 1050), (1280, 960),
                        (1024, 768), (960, 720), (800, 600), (640, 480))
    if cli_width >= ser_width or cli_height >= ser_height:
        for resolution in resolution_tuple:
            if (resolution[0] <= ser_width and resolution[1] <= ser_height) and (resolution != (ser_width, ser_height)):
                return resolution
        else:
            return ser_width, ser_height

    else:
        return cli_width, cli_height


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


def start_listener(option_value):
    global remote_client_socket, server_socket, PASSWORD, login_thread
    # Disable buttons
    button_start.configure(state=tk.DISABLED)
    r2.configure(state=tk.DISABLED)
    r1.configure(state=tk.DISABLED)
    label_initial.grid_forget()

    PASSWORD = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    if option_value == 1:
        server_ip = socket.gethostbyname(socket.gethostname())  # Local IP
        public_ip = requests.get('https://api.ipify.org').text

        # Show details
        # Local IP details

        local_ip_label.grid(row=0, column=0, sticky=tk.W, pady=2)

        local_ip_text.insert(1.0, "{:15} (Works when on same wifi or network)".format(server_ip))
        local_ip_text.configure(font=myFont_normal, state='disabled')
        local_ip_text.grid(row=0, column=1, sticky=tk.W, pady=2)

        # Public IP details
        public_ip_label.grid(row=1, column=0, sticky=tk.W, pady=2)

        public_ip_text.insert(1.0, "{:15} (Works when on different network)"
                              .format(public_ip))
        public_ip_text.configure(font=myFont_normal, state='disabled')
        public_ip_text.grid(row=1, column=1, sticky=tk.W, pady=2)

    else:
        server_ip = "127.0.0.1"
        server_name, port = setup_ngrok()

        # Show details
        # Computer name details
        name_label.grid(row=0, column=0, sticky=tk.W, pady=2)

        name_text.insert(1.0, "{:15} (Works in any network scenario)".format(server_name))
        name_text.configure(font=myFont_normal, state='disabled')
        name_text.grid(row=0, column=1, sticky=tk.W, pady=2)

        # Port details
        port_label.grid(row=1, column=0, sticky=tk.W, pady=2)

        port_text.insert(1.0, "{:15}".format(port))
        port_text.configure(font=myFont_normal, state='disabled')
        port_text.grid(row=1, column=1, sticky=tk.W, pady=2)

    # Password Details
    pass_label.grid(row=2, column=0, sticky=tk.W, pady=2)

    pass_text.insert(1.0, "{:15}".format(PASSWORD))
    pass_text.configure(font=myFont_normal, state='disabled')
    pass_text.grid(row=2, column=1, sticky=tk.W, pady=2)

    server_socket = create_listener_socket(server_ip, SERVER_PORT)
    login_thread = Thread(target=login, name="login_thread", args=(server_socket,), daemon=True)
    login_thread.start()

    # Enable button
    button_stop.configure(state=tk.NORMAL)
    # print("Remote desktop function can be executed now")
    # remote_display()


def close_sockets():
    service_socket_list = [command_client_socket, remote_client_socket, chat_client_socket, file_client_socket]
    for sock in service_socket_list:
        if sock:
            sock.close()
    # if command_client_socket:
    #     command_client_socket.close()
    # if remote_client_socket:
    #     remote_client_socket.close()
    # if chat_client_socket:
    #     chat_client_socket.close()
    # if file_client_socket:
    #     file_client_socket.close()
    if url:
        ngrok.kill()        # ngrok.disconnect(url)  Only shuts the tunnel
    print("sockets cleaned up")


def stop_listener():
    global server_socket, remote_client_socket, url
    if CLIENT_CONNECTED:
        connection.send_data(command_client_socket, COMMAND_HEADER_SIZE, bytes("disconnect", "utf-8"))
    # Closing all the sockets
    if server_socket:
        server_socket.close()
    close_sockets()

    # thread_list = [thread1, login_thread]
    # for thread in thread_list:
    #     if thread:
    #         try:
    #             if thread.is_alive():
    #                 status_login_thread = False
    #         except AttributeError:
    #             print("Attribute error raised")
    #         thread.join()

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
        port_label.grid_forget()
        port_text.grid_forget()
        port_text.configure(state="normal")
        port_text.delete('1.0', tk.END)

    # Enable buttons
    button_start.configure(state=tk.NORMAL)
    r2.configure(state=tk.NORMAL)
    r1.configure(state=tk.NORMAL)
    label_initial.grid(row=0, column=0, pady=35, sticky=tk.N)

    # Disable button
    buttons_frame.grid_forget()
    my_notebook.hide(1)
    my_notebook.hide(2)
    button_stop.configure(state=tk.DISABLED)
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
    global command_client_socket, remote_client_socket, chat_client_socket, file_client_socket, thread1
    accept = True
    try:
        while accept:
            print("Listening for incoming connections")
            command_client_socket, address = sock.accept()
            print("\n")
            print(f"Login request from {address[0]}...")
            pass_recv = connection.receive_data(command_client_socket, 2, bytes(), 1024)
            if pass_recv[0].decode("utf-8") == PASSWORD:
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
                # thread for chat
                recv_chat_msg_thread = Thread(target=receive_chat_message, name="recv_chat_msg_thread", daemon=True)
                recv_chat_msg_thread.start()
                # enable button frame
                buttons_frame.grid(row=2, column=0, padx=45, pady=20, columnspan=2, sticky=tk.W + tk.E)
                my_notebook.add(chat_frame, text=" Chat ")
                my_notebook.add(file_transfer_frame, text=" File Transfer ")
                accept = False
            else:
                connection.send_data(command_client_socket, 2, bytes("0", "utf-8"))  # failure_code--> 0
                print(f"Wrong password entered by {address[0]}")
                command_client_socket.close()
    except (ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)


def listen_for_commands():
    global login_thread
    listen = True
    try:
        while listen:
            msg = connection.receive_data(command_client_socket, COMMAND_HEADER_SIZE, bytes(), 1024)[0].decode("utf-8")
            if msg == "disconnect":
                listen = False
                # close all services socket and not the listener socket
                # close_sockets()
                # buttons_frame.grid_forget()
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)
    except ValueError:
        pass
    finally:
        close_sockets()
        buttons_frame.grid_forget()
        my_notebook.add(chat_frame, text=" Chat ")
        my_notebook.add(file_transfer_frame, text=" File Transfer ")
        login_thread = Thread(target=login, name="login_thread", args=(server_socket,), daemon=True)
        login_thread.start()
        print("Thread1 automatically exits")


def cleanup_process_threads():
    process2.join()
    process1.kill()
    process1.join()
    listener_key.stop()
    listener_key.join()
    listener_mouse.stop()
    listener_mouse.join()
    # thread2.join()
    print("cleanup finished")


def cleanup_display_process(status_queue):
    if status_queue.get() == "stop":
        connection.send_data(command_client_socket, COMMAND_HEADER_SIZE, bytes("stop_capture", "utf-8"))
        cleanup_process_threads()


def remote_display():
    global thread2, listener_key, listener_mouse, process1, process2, remote_client_socket, mouse_event_queue
    print("Sending start_capture message")
    connection.send_data(command_client_socket, COMMAND_HEADER_SIZE, bytes("start_capture", "utf-8"))
    print("Sent start_capture message")
    disable_choice = messagebox.askyesno("Remote Box", "Disable the remote computer wallpaper?(yes recommended)")
    # disable_choice = connection.retry("Disable the remote computer wallpaper?(recommended):")
    # remote display socket
    remote_client_socket, address = server_socket.accept()
    # wallpaper_settings
    print(f"Disable choice: {disable_choice}")
    connection.send_data(remote_client_socket, COMMAND_HEADER_SIZE, bytes(str(disable_choice), "utf-8"))
    print("\n")
    print(f">>You can now CONTROL the remote desktop now")
    resize_option = False
    server_width, server_height = ImageGrab.grab().size
    client_resolution = connection.receive_data(remote_client_socket, 2, bytes(), 1024)[0].decode("utf-8")
    client_width, client_height = client_resolution.split(",")

    display_width, display_height = compare_and_compute_resolution(int(client_width), int(client_height), server_width,
                                                                   server_height)
    # display_msg = bytes(str(display_width) + "," + str(display_height), "utf-8")
    # connection.send_data(clientsocket, 2, display_msg)
    if (client_width, client_height) != (display_width, display_height):
        resize_option = True

    jpeg_sync_queue = Multiprocess_queue()

    thread2 = Thread(target=recv_and_put_into_queue, name="recv_stream", args=(remote_client_socket, jpeg_sync_queue),
                     daemon=True)
    thread2.start()

    listener_key = Key_listener(on_press=on_press, on_release=on_release)
    listener_key.start()

    mouse_event_queue = Multiprocess_queue()

    process1 = Process(target=get_mouse_data_from_queue, args=(remote_client_socket, mouse_event_queue, resize_option,
                                                               int(client_width), int(client_height), display_width,
                                                               display_height), daemon=True)
    process1.start()

    listener_mouse = Mouse_listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
    listener_mouse.start()

    execution_status_queue = Multiprocess_queue()

    process2 = Process(target=display_data, args=(jpeg_sync_queue, execution_status_queue, display_width, display_height
                                                  , resize_option), daemon=True)
    process2.start()

    thread3 = Thread(target=cleanup_display_process, args=(execution_status_queue,), daemon=True)
    thread3.start()


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


# def select_service():
#     service = True
#     while service:
#         print("\n")
#         print("Additional services:")
#         print("1)Chat with remote user")
#         print("2)File transfer with remote user")
#         service_choice = input("Choose an option(1 or 2):")
#         if service_choice == "1":
#             pass
#         elif service_choice == "2":
#             pass
#         else:
#             print("Invalid option.Choose either 1 or 2")


def toggle_event_log():
    global status_event_log
    if status_event_log == 1:
        event_frame.grid_forget()
        status_event_log = 0
    elif status_event_log == 0:
        event_frame.grid(row=3, column=0, columnspan=2, padx=40, pady=5, sticky=tk.W)
        status_event_log = 1


if __name__ == "__main__":
    freeze_support()

    server_socket = None
    command_client_socket = None
    remote_client_socket = None
    chat_client_socket = None
    file_client_socket = None

    thread1 = None
    thread2 = None
    login_thread = None
    listener_key = None
    listener_mouse = None
    process1 = None
    process2 = None
    # status_login_thread = None
    # status_commands_thread = None

    CHAT_HEADER_SIZE = 10
    COMMAND_HEADER_SIZE = 2
    CLIENT_CONNECTED = False
    LOCAL_CHAT_NAME = "Me"
    REMOTE_CHAT_NAME = "Remote Box"

    url = str()
    SERVER_PORT = 1234
    PASSWORD = str()
    status_event_log = 1
    button_code = {Button.left: (1, 4), Button.right: (2, 5), Button.middle: (3, 6)}

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
    label_note.grid(row=0, column=0, pady=5, columnspan=2, sticky=tk.N)

    # Title Label
    # label_note = tk.Label(root, text="Control Remote Desktop.", padx=5, pady=5, anchor=tk.CENTER)
    # label_note.configure(font=myFont_title)
    # label_note.grid(row=1, column=0, padx=40, columnspan=2, sticky=tk.N)

    # Connection Frame
    connection_frame = tk.LabelFrame(listener_frame, text="Connection Mode", padx=20, pady=20)
    connection_frame.configure(font=myFont_title)
    connection_frame.grid(row=1, column=0, padx=40, pady=40, sticky=tk.W)

    # Radio button
    radio_var = tk.IntVar()
    radio_var.set(1)
    r1 = tk.Radiobutton(connection_frame, text="IP", variable=radio_var, value=1)
    r1.configure(font=myFont_normal)
    r1.grid(row=0, column=0, sticky=tk.W, pady=2)

    r2 = tk.Radiobutton(connection_frame, text="Computer Name", variable=radio_var, value=2)
    r2.configure(font=myFont_normal)
    r2.grid(row=1, column=0, sticky=tk.W, pady=2)

    # Start and stop listener
    button_start = tk.Button(connection_frame, text="Start Listener", padx=2, pady=2,
                             command=lambda: start_listener(radio_var.get()))
    button_start.configure(font=myFont_title_normal)
    button_start.grid(row=2, column=0, sticky=tk.W, pady=2)

    button_stop = tk.Button(connection_frame, text="Stop Listener", padx=2, pady=2,
                            command=lambda: stop_listener())
    button_stop.configure(font=myFont_title_normal, state=tk.DISABLED)
    button_stop.grid(row=2, column=1, sticky=tk.W, pady=2)

    # Details Frame
    details_frame = tk.LabelFrame(listener_frame, text="Control Remote Desktop", padx=20, pady=20, labelanchor=tk.NE)
    details_frame.configure(font=myFont_title)
    details_frame.grid(row=1, column=1, padx=40, pady=40)

    label_initial = tk.Label(details_frame, text="<-- Select connection mode and start listener to "
                                                 "generate the details", padx=5, pady=5, anchor=tk.CENTER)
    label_initial.configure(font=myFont_normal)
    label_initial.grid(row=0, column=0, pady=35, sticky=tk.N)

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
    port_label = tk.Label(details_frame, text="Port no       :", padx=5, pady=5)
    port_label.configure(font=myFont_title_normal)
    port_text = tk.Text(details_frame, pady=5, width=47, height=1, background="#e6e6e6", bd=0)
    # Password Details
    pass_label = tk.Label(details_frame, text="Password     :", padx=5, pady=5)
    pass_label.configure(font=myFont_title_normal)
    pass_text = tk.Text(details_frame, pady=5, width=47, height=1, background="#e6e6e6", bd=0)

    # Buttons  Frame
    buttons_frame = tk.LabelFrame(listener_frame, text="Access", padx=20, pady=20, bd=0)
    buttons_frame.configure(font=myFont_title)
    buttons_frame.grid(row=2, column=0, padx=45, pady=20, columnspan=2, sticky=tk.W+tk.E)

    # Disable access frame when not connected
    buttons_frame.grid_forget()

    # View Remote Box button
    remote_button = tk.Button(buttons_frame, text="Remote Box", padx=2, pady=2, command=remote_display)
    remote_button.configure(font=myFont_normal)
    remote_button.grid(row=0, column=1, sticky=tk.W, padx=60)

    # Chat button
    chat_button = tk.Button(buttons_frame, text="Chat", padx=3, pady=2, command=lambda: my_notebook.select(1))
    chat_button.configure(font=myFont_normal)
    chat_button.grid(row=0, column=2, sticky=tk.W, padx=60)

    # File transfer button
    file_button = tk.Button(buttons_frame, text="File Transfer", padx=2, pady=2, command=lambda: my_notebook.select(2))
    file_button.configure(font=myFont_normal)
    file_button.grid(row=0, column=3, sticky=tk.W, padx=60)

    # Show/Hide Event Logs button
    event_log_button = tk.Button(buttons_frame, text="Show/Hide Event Logs", padx=2, pady=2, command=toggle_event_log)
    event_log_button.configure(font=myFont_normal)
    event_log_button.grid(row=0, column=4, sticky=tk.W, padx=60)

    # # Event_log Frame
    event_frame = tk.LabelFrame(listener_frame, text="Event Log", padx=20, pady=20, relief=tk.FLAT)
    event_frame.configure(font=myFont_title)
    event_frame.grid(row=3, column=0, columnspan=2, padx=40, pady=5, sticky=tk.W)

    # Scroll bar to event frame
    scroll_widget = tk.Scrollbar(event_frame)
    scroll_widget.grid(row=0, column=1, sticky=tk.N + tk.S)

    # Text Widget
    text_1 = tk.Text(event_frame, width=70, height=7, font=("Helvetica", 13), padx=10, pady=10,
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
    chat_frame = tk.LabelFrame(my_notebook, padx=140, pady=40, bd=0)
    chat_frame.grid(row=0, column=0, sticky=tk.N)

    # text_frame = tk.LabelFrame(chat_frame, bd=0)
    # text_frame.grid(row=0, column=0)

    # Scroll bar to event frame
    scroll_chat_widget = tk.Scrollbar(chat_frame)
    scroll_chat_widget.grid(row=0, column=1, sticky=tk.N + tk.S)

    # Text Widget
    text_chat_widget = tk.Text(chat_frame, width=60, height=25, font=("Helvetica", 14), padx=10, pady=10,
                               yscrollcommand=scroll_chat_widget.set)
    # text_chat_widget.insert(1.0, "By Default Share Funny Jokes")
    text_chat_widget.configure(state='disabled')
    text_chat_widget.grid(row=0, column=0, sticky=tk.N)

    scroll_chat_widget.config(command=text_chat_widget.yview)

    # Frame for input text
    input_text_frame = tk.LabelFrame(chat_frame, pady=5, bd=0)
    input_text_frame.grid(row=1, column=0, sticky=tk.W)

    # Text Widget
    input_text_widget = tk.Entry(input_text_frame, width=62)
    input_text_widget.configure(font=("Helvetica", 14))
    input_text_widget.bind("<Return>", send_chat_message)
    input_text_widget.grid(row=0, column=0, pady=10, sticky=tk.W)

    # <------File Transfer Tab -------------->
    file_transfer_frame = tk.LabelFrame(my_notebook, padx=40, pady=40, bd=0)
    file_transfer_frame.grid(row=0, column=0, sticky=tk.N)

    # Create Tab style
    tab_style = ttk.Style()
    tab_style.configure('TNotebook.Tab', font=('Helvetica', '13', 'bold'))

    # Tab Creation
    my_notebook.add(listener_frame, text=" Connection ")
    my_notebook.add(chat_frame, text=" Chat ")
    my_notebook.add(file_transfer_frame, text=" File Transfer ")

    # Hide Tab
    my_notebook.hide(1)
    my_notebook.hide(2)

    root.mainloop()

    # SERVER_IP = display_and_get_server_info()
    # server_socket = create_listener_socket(SERVER_IP, SERVER_PORT)
    # clientsocket = login(server_socket)
    # remote_display()
    # select_service()

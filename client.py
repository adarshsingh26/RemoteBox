# ###############----------------->import<--------------------############
import socket
from PIL import Image, ImageGrab, ImageTk
import pygetwindow
import re
import os
import time
import win32gui
import lz4.frame
from io import BytesIO
from threading import Thread
from multiprocessing import freeze_support, Process, Queue as Multiprocess_queue
from pynput.keyboard import Listener as Key_listener
from pynput.mouse import Button, Listener as Mouse_listener
import tkinter as tk
from tkinter.font import Font
from tkinter import ttk, messagebox, filedialog
import connection
import win32api
from datetime import datetime


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
                    send_event(msg, remote_server_socket)
            except AttributeError:
                msg = bytes(event_code + key.name, "utf-8")  # special key
                send_event(msg, remote_server_socket)


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


def cleanup_process_threads():
    # process2.join()
    # process1.kill()
    # process1.join()
    process_list = [process1, process2]
    for process in process_list:
        if process:
            if process.is_alive():
                process.kill()
            process.join()
    listener_key.stop()
    listener_key.join()
    listener_mouse.stop()
    listener_mouse.join()
    # thread2.join()
    print("cleanup finished")


def cleanup_display_process(status_queue):
    if status_queue.get() == "stop":
        connection.send_data(command_server_socket, COMMAND_HEADER_SIZE, bytes("stop_capture", "utf-8"))
        cleanup_process_threads()


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


def remote_display():
    global thread2, listener_key, listener_mouse, process1, process2, remote_server_socket, mouse_event_queue
    print("Sending start_capture message")
    connection.send_data(command_server_socket, COMMAND_HEADER_SIZE, bytes("start_capture", "utf-8"))
    print("Sent start_capture message")
    disable_choice = messagebox.askyesno("Remote Box", "Disable the remote computer wallpaper?(yes recommended)")
    # disable_choice = connection.retry("Disable the remote computer wallpaper?(recommended):")

    # remote display socket
    remote_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    remote_server_socket.connect((server_ip, server_port))
    # wallpaper_settings
    print(f"Disable choice: {disable_choice}")
    connection.send_data(remote_server_socket, COMMAND_HEADER_SIZE, bytes(str(disable_choice), "utf-8"))
    print("\n")
    print(f">>You can now CONTROL the remote desktop now")
    resize_option = False
    server_width, server_height = ImageGrab.grab().size
    client_resolution = connection.receive_data(remote_server_socket, 2, bytes(), 1024)[0].decode("utf-8")
    client_width, client_height = client_resolution.split(",")

    display_width, display_height = compare_and_compute_resolution(int(client_width), int(client_height), server_width,
                                                                   server_height)
    # display_msg = bytes(str(display_width) + "," + str(display_height), "utf-8")
    # connection.send_data(clientsocket, 2, display_msg)
    if (client_width, client_height) != (display_width, display_height):
        resize_option = True

    jpeg_sync_queue = Multiprocess_queue()

    thread2 = Thread(target=recv_and_put_into_queue, name="recv_stream", args=(remote_server_socket, jpeg_sync_queue),
                     daemon=True)
    thread2.start()

    listener_key = Key_listener(on_press=on_press, on_release=on_release)
    listener_key.start()

    mouse_event_queue = Multiprocess_queue()

    process1 = Process(target=get_mouse_data_from_queue, args=(remote_server_socket, mouse_event_queue, resize_option,
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


def login():
    # resize_option = False
    global command_server_socket, remote_server_socket, chat_server_socket, file_server_socket, thread1, server_ip, \
        server_port

    server_ip = name_entry.get()
    server_port = int(port_entry.get())
    server_pass = pass_entry.get()
    if len(server_pass) == 6 and server_pass.strip() != "":
        try:
            command_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            command_server_socket.connect((server_ip, server_port))
            server_pass = bytes(server_pass, "utf-8")
            connection.send_data(command_server_socket, 2, server_pass)  # send password
            login_response = connection.receive_data(command_server_socket, 2, bytes(), 1024)[0].decode("utf-8")

            if login_response != "1":
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
                #label_status.configure(state='normal')
                label_status.grid()
                execute = False

                thread1 = Thread(target=listen_for_commands, daemon=True)
                thread1.start()
                # thread for chat
                recv_chat_msg_thread = Thread(target=receive_chat_message, name="recv_chat_msg_thread", daemon=True)
                recv_chat_msg_thread.start()

                # Enable
                disconnect_button.configure(state="normal")
                my_notebook.add(chat_frame, text=" Chat ")
                # my_notebook.add(file_transfer_frame, text=" File Transfer ")
                access_button_frame.grid(row=7, column=0, padx=45, pady=20, columnspan=2, sticky=tk.W + tk.E)
                # Disable
                name_entry.configure(state="disabled")
                port_entry.configure(state="disabled")
                pass_entry.configure(state="disabled")
                connect_button.configure(state="disabled")

        except OSError as e:
            #label_status.configure(state='disabled')
            label_status.grid_remove()
            print(e.strerror)
    else:
        print("Password is not 6 characters")


def close_sockets():
    service_socket_list = [command_server_socket, remote_server_socket, chat_server_socket, file_server_socket]
    for sock in service_socket_list:
        if sock:
            sock.close()
    print("Closed all the sockets")


def disconnect(caller):
    if caller == "button":
        connection.send_data(command_server_socket, COMMAND_HEADER_SIZE, bytes("disconnect", "utf-8"))

    close_sockets()

    # Enable
    name_entry.configure(state="normal")
    port_entry.configure(state="normal")
    pass_entry.configure(state="normal")
    connect_button.configure(state="normal")

    # Disable
    disconnect_button.configure(state="disabled")
    #label_status.configure(state='disabled')
    label_status.grid_remove()

    access_button_frame.grid_forget()
    my_notebook.hide(1)
    my_notebook.hide(2)


def listen_for_commands():
    listen = True
    try:
        while listen:
            msg = connection.receive_data(command_server_socket, COMMAND_HEADER_SIZE, bytes(), 1024)[0].decode("utf-8")
            if msg == "disconnect":
                listen = False
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)
    except ValueError:
        pass
    finally:
        if (file_window is not None) and file_window.winfo_exists():
            file_window.destroy()
            print("top window destroyed")
        #label_status.configure(state='disabled')
        label_status.grid_remove()
        disconnect("message")
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


def upload_file(filename):
    # needs the location of the file to upload
    file_size = os.stat(filename).st_size
    connection.send_data(file_server_socket, FILE_HEADER_SIZE, bytes(str(file_size), "utf-8"))
    file_mode = "r" if (len(filename) > 4) and (filename[len(filename) - 4:] == ".txt") else "rb"
    client_file_mode = "w" if file_mode == "r" else "wb"
    connection.send_data(file_server_socket, FILE_HEADER_SIZE, bytes(client_file_mode, "utf-8"))
    data = True
    with open(filename, file_mode) as f:
        while data:
            if file_mode == "r":
                data = bytes(f.read(65536), "utf-8")
            elif file_mode == "rb":
                data = f.read(65536)
            if data:
                connection.send_data(file_server_socket, FILE_HEADER_SIZE, data)


def file_explore(system_name):
    # global LOCAL_PATH
    system_values = system_choice.get(system_name)
    if system_name == "local":
        try:
            # scan the current path to get the path details
            obj = os.scandir(system_values[2])
        except PermissionError:
            print("No permission to access this resource")
            back_button("restore_prev_path", system_name)
            return
    else:
        pass
    count = 0
    for entry in obj:
        if entry.is_dir() or entry.is_file():
            st = entry.stat()
            # modification datetime
            mod = datetime.fromtimestamp(st.st_mtime).strftime("%d-%m-%Y %I:%M %p")
            if entry.is_dir():
                typ = "File folder"
                size = ""
                update_treeview(system_values[0], count, folder_img, (entry.name, typ, size, mod))
                count += 1
            else:
                typ = "File"
                # get the extension of file to define the file type and icon of the file
                match = re.search(r"\.(\w+)$", entry.name)
                display_img = file_img
                if match:
                    ext = match.group(1)
                    if ext.lower() == "pdf":
                        display_img = pdf_img
                    elif ext.lower() == "exe":
                        display_img = exe_img
                    elif ext.lower() in ("jpg", "png", "bmp", "gif", "tiff"):
                        display_img = photo_img
                    elif ext.lower() == "txt":
                        display_img = txt_img
                    elif ext.lower() in ("doc", "docx", "docm"):
                        display_img = word_img
                    elif ext.lower() in ("ppt", "pptx", "pptm"):
                        display_img = powerpoint_img
                    elif ext.lower() in ("xlsx", "xlsm"):
                        display_img = excel_img
                    elif ext.lower() in ("mp4", "mov", "wmv", "flv", "avi", "mkv"):
                        display_img = video_img
                    elif ext.lower() in ("3gp", "mp3", "wav", "webm", "m4a"):
                        display_img = music_img
                    elif ext.lower() in ("zip", "7z", "rar", "tar", "iso", "gz", "sfx", "apk"):
                        display_img = zip_img
                    typ = ext.upper() + " " + typ

                # Get the appropriate size
                if st.st_size < 1024:
                    size = str(st.st_size) + " bytes"
                elif st.st_size < 1048576:
                    size = str(round(st.st_size / 1024, 1)) + " KB"
                elif st.st_size < 1073741824:
                    size = str(round(st.st_size / (1024 * 1024), 1)) + " MB"
                else:
                    size = str(round(st.st_size / (1024 * 1024 * 1024), 1)) + " GB"

                # insert data into the treeview
                update_treeview(system_values[0], count, display_img, (entry.name, typ, size, mod))
                count += 1

    system_values[1].delete(0, tk.END)
    system_values[1].insert(0, system_values[2].replace(r"\\", "\\"))


def drive_letters(system_name):
    system_values = system_choice.get(system_name)
    drives = win32api.GetLogicalDriveStrings()
    drives = tuple(drives.split(':\\\000')[:-1])
    for i in range(0, len(drives)):
        update_treeview(system_values[0], i, drive_img, (drives[i], "Drive", "", ""))


def back_button(event, system_name):
    # global LOCAL_PATH
    # list of directories excluding 2 elements i.e the empty string and the last directory
    system_values = system_choice.get(system_name)
    li_of_dir = system_values[2].split(r"\\")[:-2]
    if li_of_dir:
        system_choice.get(system_name)[2] = r""
        # joining each element of list with "\\" to form the new path
        for name in li_of_dir:
            system_choice.get(system_name)[2] += name + r"\\"
        if event == "button":
            file_explore(system_name)
    else:
        # clear the local path displayed
        system_values[1].delete(0, tk.END)
        drive_letters(system_name)


def change_path(event=None, system_name=None):
    # global LOCAL_PATH, REMOTE_PATH
    system_values = system_choice.get(system_name)
    items = system_values[0].selection()
    if len(items) == 1:
        col_values = system_values[0].item(items[0], 'values')
        print(f"Selection : {col_values[0]}")
        if col_values[1] == "File folder" or col_values[1] == "Drive":
            if col_values[1] == "Drive":
                system_choice.get(system_name)[2] = col_values[0] + r":\\"
            elif col_values[1] == "File folder":
                system_choice.get(system_name)[2] += col_values[0] + r"\\"
            print(f"Changing path to : {system_choice.get(system_name)[2]}")  # for i in items:
            file_explore(system_name)


def update_treeview(file_tree, iid, img, value):
    if iid == 0:
        file_tree.delete(*file_tree.get_children())
    file_tree.insert(parent="", index="end", iid=iid, text="", image=img, values=value)


def recv_file_details(files_details_queue):
    recv = True
    partial_prev_msg = bytes()
    try:
        while recv:
            msg = connection.receive_data(browse_file_server_socket, FILE_HEADER_SIZE, partial_prev_msg)
            if msg:
                files_details_queue.put(lz4.frame.decompress(msg[0]))  # msg[0]--> new msg
                partial_prev_msg = msg[1]                              # msg[1]--> partial_prev_msg
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)
    except ValueError:
        pass
    finally:
        print("recv_file_details_process automatically exits")


def local_file_treeview():
    global local_file_tree, local_path_entry

    local_top_file_frame = tk.LabelFrame(file_window, bd=0)
    local_top_file_frame.grid(row=0, column=0, sticky=tk.W + tk.E, padx=10, pady=10)

    local_file_frame = tk.LabelFrame(file_window, bd=0)
    local_file_frame.grid(row=1, column=0, sticky=tk.W + tk.E, padx=10)

    # path entry field
    local_path_entry = tk.Entry(local_top_file_frame, width=45)
    local_path_entry.configure(font=("Helvetica", 11, "bold"))
    local_path_entry.grid(row=0, column=1, columnspan=2, sticky=tk.W + tk.E)

    # scrollbar
    local_scroll_file_widget = tk.Scrollbar(local_file_frame)
    local_scroll_file_widget.grid(row=1, column=1, sticky=tk.N + tk.S)

    # Treeview
    local_file_tree = ttk.Treeview(local_file_frame, yscrollcommand=local_scroll_file_widget.set)

    local_scroll_file_widget.configure(command=local_file_tree.yview)
    # defining the columns
    local_file_tree["columns"] = ("Name", "Type", "Size", "Modified")

    # formatting the columns
    local_file_tree.column("#0", width=50, minwidth=50, anchor=tk.W, stretch=tk.NO)
    local_file_tree.column("Name", anchor=tk.W, width=130, minwidth=60)
    local_file_tree.column("Type", anchor=tk.W, width=100, minwidth=50)
    local_file_tree.column("Size", anchor=tk.CENTER, width=80, minwidth=40)
    local_file_tree.column("Modified", anchor=tk.W, width=80, minwidth=40)

    # Heading of columns
    local_file_tree.heading("#0", text="", anchor=tk.W)
    local_file_tree.heading("Name", text="Name", anchor=tk.W)
    local_file_tree.heading("Type", text="Type", anchor=tk.W)
    local_file_tree.heading("Size", text="Size", anchor=tk.CENTER)
    local_file_tree.heading("Modified", text="Modified", anchor=tk.W)

    # local back button
    local_prev_dir_button = tk.Button(local_top_file_frame, bd=0, image=back_img,
                                      command=lambda: back_button("button", "local"))
    local_prev_dir_button.grid(row=0, column=0, sticky=tk.W, padx=10)

    local_path_entry.insert(0, LOCAL_PATH)

    tree_style = ttk.Style()
    tree_style.configure('Treeview', rowheight=40)
    local_file_tree.bind("<Double-1>", lambda event: change_path(event, system_name="local"))
    local_file_tree.grid(row=1, column=0, pady=10, sticky=tk.W + tk.E)

    system_choice["local"][0] = local_file_tree
    system_choice["local"][1] = local_path_entry


def remote_file_treeview():
    global remote_file_tree, remote_path_entry

    remote_top_file_frame = tk.LabelFrame(file_window, bd=0)
    remote_top_file_frame.grid(row=0, column=1, sticky=tk.W + tk.E, padx=10, pady=10)

    remote_file_frame = tk.LabelFrame(file_window, bd=0)
    remote_file_frame.grid(row=1, column=1, sticky=tk.W + tk.E, padx=10)

    # path entry field
    remote_path_entry = tk.Entry(remote_top_file_frame, width=45)
    remote_path_entry.configure(font=("Helvetica", 11, "bold"))
    remote_path_entry.grid(row=0, column=1, columnspan=2, sticky=tk.W + tk.E)

    # scrollbar
    remote_scroll_file_widget = tk.Scrollbar(remote_file_frame)
    remote_scroll_file_widget.grid(row=1, column=1, sticky=tk.N + tk.S)

    # Treeview
    remote_file_tree = ttk.Treeview(remote_file_frame, yscrollcommand=remote_scroll_file_widget.set)

    remote_scroll_file_widget.configure(command=remote_file_tree.yview)
    # defining the columns
    remote_file_tree["columns"] = ("Name", "Type", "Size", "Modified")

    # formatting the columns
    remote_file_tree.column("#0", width=50, minwidth=50, anchor=tk.W, stretch=tk.NO)
    remote_file_tree.column("Name", anchor=tk.W, width=130, minwidth=130)
    remote_file_tree.column("Type", anchor=tk.W, width=100, minwidth=100)
    remote_file_tree.column("Size", anchor=tk.CENTER, width=80, minwidth=80)
    remote_file_tree.column("Modified", anchor=tk.W, width=80, minwidth=80)

    # Heading of columns
    remote_file_tree.heading("#0", text="", anchor=tk.W)
    remote_file_tree.heading("Name", text="Name", anchor=tk.W)
    remote_file_tree.heading("Type", text="Type", anchor=tk.W)
    remote_file_tree.heading("Size", text="Size", anchor=tk.CENTER)
    remote_file_tree.heading("Modified", text="Modified", anchor=tk.W)

    # remote back button
    remote_prev_dir_btn = tk.Button(remote_top_file_frame, bd=0, image=back_img,
                                    command=lambda: back_button("button", "remote"))
    remote_prev_dir_btn.grid(row=0, column=0, sticky=tk.W, padx=10)

    remote_path_entry.insert(0, REMOTE_PATH)

    remote_tree_style = ttk.Style()
    remote_tree_style.configure('Treeview', rowheight=40)
    remote_file_tree.bind("<Double-1>", lambda event: change_path(event, system_name="remote"))
    remote_file_tree.grid(row=1, column=0, pady=10, sticky=tk.W + tk.E)

    system_choice["remote"][0] = remote_file_tree
    system_choice["remote"][1] = remote_path_entry


def check_window_closed():
    window_open = True
    while window_open:
        if (file_window is not None) and file_window.winfo_exists():
            time.sleep(3)
            continue
        else:
            file_button.configure(state="normal")
            window_open = False


def file_transfer_window():
    global file_window
    file_button.configure(state="disabled")

    file_window = tk.Toplevel()
    file_window.title("File Transfer")
    file_window.resizable(False, False)

    # local file treeview
    local_file_treeview()

    # remote file_treeview
    remote_file_treeview()

    files_details_queue = Multiprocess_queue()

    connection.send_data(command_server_socket, COMMAND_HEADER_SIZE, bytes("start_file_explorer", "utf-8"))

    recv_file_details_process = Process(target=recv_file_details, args=(files_details_queue,),
                                        name="recv_file_details_process", daemon=True)
    recv_file_details_process.start()

    update_file_gui_thread = Thread(target=update_treeview, name="update_file_gui_thread", daemon=True)
    update_file_gui_thread.start()

    check_window_status_thread = Thread(target=check_window_closed, name="check_window_status", daemon=True)
    check_window_status_thread.start()

    drive_letters("local")
    drive_letters("remote")


if __name__ == "__main__":
    freeze_support()

    command_server_socket = None
    remote_server_socket = None
    chat_server_socket = None
    file_server_socket = None
    browse_file_server_socket = None

    thread1 = None
    thread2 = None
    listener_key = None
    listener_mouse = None
    process1 = None
    process2 = None

    server_ip = str()
    server_port = int()
    status_event_log = 1

    # local_drives = None
    # remote_drives = None

    LOCAL_PATH = r""
    local_file_tree = None
    local_path_entry = None
    REMOTE_PATH = r""
    remote_file_tree = None
    remote_path_entry = None
    file_window = None

    COMMAND_HEADER_SIZE = 2
    CHAT_HEADER_SIZE = 10
    FILE_HEADER_SIZE = 10
    LOCAL_CHAT_NAME = "Me"
    REMOTE_CHAT_NAME = "Remote Box"

    button_code = {Button.left: (1, 4), Button.right: (2, 5), Button.middle: (3, 6)}
    system_choice = {"local": [local_file_tree, local_path_entry, LOCAL_PATH],
                     "remote": [remote_file_tree, remote_path_entry, REMOTE_PATH]}

    # Create Root Window
    root = tk.Tk()
    root.title("Remote Box")
    root.iconbitmap("logo.ico")
    root.resizable(False, False)

    # icons
    folder_img = tk.PhotoImage(file="file_icons\\folder.png")
    file_img = tk.PhotoImage(file="file_icons\\file.png")
    pdf_img = tk.PhotoImage(file="file_icons\\pdf.png")
    photo_img = tk.PhotoImage(file="file_icons\\photo.png")
    txt_img = tk.PhotoImage(file="file_icons\\txt.png")
    exe_img = tk.PhotoImage(file="file_icons\\exe.png")
    zip_img = tk.PhotoImage(file="file_icons\\zip.png")
    word_img = tk.PhotoImage(file="file_icons\\word.png")
    powerpoint_img = tk.PhotoImage(file="file_icons\\powerpoint.png")
    video_img = tk.PhotoImage(file="file_icons\\video.png")
    music_img = tk.PhotoImage(file="file_icons\\music.png")
    excel_img = tk.PhotoImage(file="file_icons\\excel.png")
    drive_img = tk.PhotoImage(file="file_icons\\drive.png")
    back_img = tk.PhotoImage(file="file_icons\\back.png")

    green_img = tk.PhotoImage(file="green_16.png")

    # My fonts
    myFont_title = Font(family="Helvetica", size=14, weight="bold")
    myFont_title_normal = Font(family="Helvetica", size=13, weight="bold")
    myFont_normal = Font(family="Helvetica", size=13)

    # My Notebook
    my_notebook = ttk.Notebook(root)
    my_notebook.grid(row=0, column=0, pady=5)

    # <------Connection Tab -------------->
    connection_frame = tk.LabelFrame(my_notebook, padx=100, pady=5, bd=0)
    connection_frame.grid(row=0, column=0, padx=40, pady=40, sticky=tk.N)

    # Logo Label
    img_logo = ImageTk.PhotoImage(Image.open("logo.png"))
    label_note = tk.Label(connection_frame, image=img_logo, anchor=tk.CENTER)
    label_note.grid(row=0, column=0, pady=5, columnspan=2, sticky=tk.N)

    # Form elements frame
    form_frame = tk.LabelFrame(connection_frame, text="Control Remote Box", padx=20, pady=5)
    form_frame.configure(font=myFont_title)
    form_frame.grid(row=1, column=0, padx=120, pady=(40, 20), sticky=tk.N)

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

    pass_entry = tk.Entry(form_frame, show="*", width=20)
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

    # Access Button Frame
    access_button_frame = tk.LabelFrame(connection_frame, text="Access", padx=5, pady=15)
    access_button_frame.configure(font=myFont_title)
    access_button_frame.grid(row=7, column=0, padx=10, pady=10, columnspan=2, sticky=tk.W+tk.E)

    # Disable access frame when not connected
    access_button_frame.grid_forget()

    # images
    remote_img = tk.PhotoImage(file="remote_32.png")
    chat_img = tk.PhotoImage(file="chat_32.png")
    file_transfer_img = tk.PhotoImage(file="file_transfer_32.png")

    # View Remote Box button
    remote_button = tk.Button(access_button_frame, text="Remote Box", image=remote_img, compound=tk.TOP, padx=2,
                              pady=2, bd=0, command=remote_display)
    remote_button.configure(font=myFont_normal)
    remote_button.grid(row=0, column=1, sticky=tk.W, padx=30)  # padx =60

    # Chat button
    chat_button = tk.Button(access_button_frame, text="Chat", image=chat_img, compound=tk.TOP, padx=3, pady=2, bd=0,
                            command=lambda: my_notebook.select(1))
    chat_button.configure(font=myFont_normal)
    chat_button.grid(row=0, column=2, sticky=tk.W, padx=30)

    # File transfer button
    file_button = tk.Button(access_button_frame, text="File Transfer", image=file_transfer_img, compound=tk.TOP, padx=2,
                            pady=2, bd=0, command=file_transfer_window)   # lambda: my_notebook.select(2)
    file_button.configure(font=myFont_normal)
    file_button.grid(row=0, column=3, sticky=tk.W, padx=30)

    # <------Chat Tab -------------->
    chat_frame = tk.LabelFrame(my_notebook, padx=20, pady=20, bd=0)
    chat_frame.grid(row=0, column=0, sticky=tk.N)

    # text_frame = tk.LabelFrame(chat_frame, bd=0)
    # text_frame.grid(row=0, column=0)

    # Scroll bar to event frame
    scroll_chat_widget = tk.Scrollbar(chat_frame)
    scroll_chat_widget.grid(row=0, column=1, sticky=tk.N + tk.S)

    # Text Widget
    text_chat_widget = tk.Text(chat_frame, width=60, height=22, font=("Helvetica", 14), padx=10, pady=10,
                               yscrollcommand=scroll_chat_widget.set)
    # text_chat_widget.insert(1.0, "By Default Share Funny Jokes")
    text_chat_widget.configure(state='disabled')
    text_chat_widget.grid(row=0, column=0, sticky=tk.N)

    scroll_chat_widget.config(command=text_chat_widget.yview)

    # Frame for input text
    input_text_frame = tk.LabelFrame(chat_frame, pady=5, bd=0)
    input_text_frame.grid(row=1, column=0, sticky=tk.W)

    # Text Widget
    input_text_widget = tk.Entry(input_text_frame, width=60)
    input_text_widget.configure(font=("Helvetica", 14))
    input_text_widget.bind("<Return>", send_chat_message)
    input_text_widget.grid(row=0, column=0, pady=10, sticky=tk.W)



    # # <------File Transfer Tab -------------->
    # file_transfer_frame = tk.LabelFrame(my_notebook, padx=40, pady=40, bd=0)
    # file_transfer_frame.grid(row=0, column=0, sticky=tk.N)
    #
    # # Upload file frame
    # upload_frame = tk.LabelFrame(file_transfer_frame,text="Upload a File", padx=40, pady=40)
    # upload_frame.configure(font=myFont_title_normal)
    # upload_frame.grid(row=0, column=0, sticky=tk.W+tk.E)
    #
    # # Select a file to upload Button
    # select_file_upload_btn = tk.Button(upload_frame, text="Select File", padx=3, pady=2, command=open_file)
    # select_file_upload_btn.configure(font=myFont_title_normal)
    # select_file_upload_btn.grid(row=0, column=0, sticky=tk.W, padx=30)
    #
    # # Selected file label
    # select_file_upload_label = tk.Label(upload_frame, padx=5, pady=5)
    # select_file_upload_label.configure(font=myFont_title_normal)
    # select_file_upload_label.grid(row=1, column=0, pady=5, sticky=tk.W)
    #
    # # Select location Button
    # select_loc_upload_btn = tk.Button(upload_frame, text="Select Location", padx=3, pady=2)
    # select_loc_upload_btn.configure(font=myFont_title_normal)
    # select_loc_upload_btn.grid(row=0, column=1, sticky=tk.W, padx=30)
    #
    # # Upload Button
    # file_upload_btn = tk.Button(upload_frame, text="Upload", padx=3, pady=2)
    # file_upload_btn.configure(font=myFont_title_normal)
    # file_upload_btn.grid(row=2, column=0, columnspan=2, sticky=tk.N, padx=30)

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
    label_status = tk.Label(root, text="Connected", image=green_img, compound=tk.LEFT, relief=tk.SUNKEN, bd=0, anchor=tk.E,
                            padx=10)
    label_status.configure(font=myFont_normal)
    label_status.grid(row=3, column=0, columnspan=2, sticky=tk.W + tk.E)
    label_status.grid_remove()

    # Create Tab style
    tab_style = ttk.Style()
    tab_style.configure('TNotebook.Tab', font=('Helvetica', '13', 'bold'))

    # Tab Creation
    my_notebook.add(connection_frame, text=" Connection ")
    my_notebook.add(chat_frame, text=" Chat ")
    # my_notebook.add(file_transfer_frame, text=" File Transfer ")
    my_notebook.add(event_frame, text=" Event Logs ")

    # Hide Tab
    my_notebook.hide(1)
    my_notebook.hide(2)

    root.mainloop()

import socket
from PIL import Image, ImageGrab
import pygetwindow
import connection
import time
import os
import string
import random
import win32gui
import requests
import re
from io import BytesIO
from threading import Thread
from multiprocessing import freeze_support, Process, Queue as Multiprocess_queue
from pynput.keyboard import Listener as Key_listener
from pynput.mouse import Button, Listener as Mouse_listener
from pyngrok import ngrok
from pyngrok import conf
from pyngrok.conf import PyngrokConfig


execute_thread = True


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
        elif event_code in range(1, 10):
            if within_display:
                msg = bytes(f"{event_code:<2}", "utf-8")
                send_event(msg, sock)


def scale_x_y(x, y, cli_width, cli_height, dis_width, dis_height):
    scale_x = cli_width / dis_width
    scale_y = cli_height / dis_height
    x *= scale_x
    y *= scale_y
    return round(x, 2), round(y, 2)


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
        if active_window.title == f"Remote Desktop":
            try:
                if key.char:
                    msg = bytes(event_code + key.char, "utf-8")  # alphanumeric key
                    send_event(msg, clientsocket)
            except AttributeError:
                msg = bytes(event_code + key.name, "utf-8")  # special key
                send_event(msg, clientsocket)


def on_press(key):
    key_events(key, "-1")


def on_release(key):
    key_events(key, "-2")


def recv_and_put_into_queue(client_socket, jpeg_queue):
    header_size = 10
    partial_prev_msg = bytes()

    try:
        while execute_thread:
            msg = connection.receive_data(client_socket, header_size, partial_prev_msg)
            if msg:
                jpeg_queue.put(msg[0])  # msg[0]--> new msg
                partial_prev_msg = msg[1]  # msg[1]--> partial_prev_msg
    except (ConnectionAbortedError, ConnectionResetError, OSError) as e:
        print(e.strerror)
    except ValueError:
        pass
    finally:
        print("Program terminated.You could close the program now.")
        time.sleep(10)
        process2.kill()
        client_socket.close()


def display_data(jpeg_queue, dis_width, dis_height, resize):
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
    if cli_width >= ser_width or cli_height >= ser_height:
        for resolution in resolution_tuple:
            if (resolution[0] <= ser_width and resolution[1] <= ser_height) and (resolution != (ser_width, ser_height)):
                return resolution
        else:
            return ser_width, ser_height

    else:
        return cli_width, cli_height


def setup_ngrok():
    conf.DEFAULT_PYNGROK_CONFIG = PyngrokConfig(region="in", ngrok_path="{}".format(os.getenv('APPDATA') +
                                                                                    r'\RemoteApplication\ngrok.exe'))
    # pyngrok_config = PyngrokConfig(region="in")
    ngrok.set_auth_token("1h35E4ZgL4VsxAdkjKuXZ7EMhqG_5Bco3S82TGPYEm2NgpS3h")
    url = ngrok.connect(1234, "tcp", pyngrok_config=conf.DEFAULT_PYNGROK_CONFIG)
    computer_name = re.search(r"//(.+):", url).group(1)
    port_no = re.search(r":(\d+)", url).group(1)
    return computer_name, port_no


if __name__ == "__main__":
    freeze_support()
    server_width, server_height = ImageGrab.grab().size
    resize_option = False
    resolution_tuple = ((7680, 4320), (3840, 2160), (2560, 1440), (1920, 1080), (1600, 900), (1366, 768), (1280, 720),
                        (1152, 648), (1024, 576), (2560, 1600), (1920, 1200), (1680, 1050), (1440, 900), (1280, 800),
                        (2048, 1536), (1920, 1440), (1856, 1392), (1600, 1200), (1440, 1080), (1400, 1050), (1280, 960),
                        (1024, 768), (960, 720), (800, 600), (640, 480))

    print(">>>   Remote Desktop Application   (Coded By: 'ADARSH SINGH' @Overflow) <<<")
    print("\n")
    print("Connection mode:")
    print("1)IP              (Good Performance)")
    print("2)Computer name   (Normal Performance)")

    # while len(password) < 6:
    #     password = input("Set a password for this session(MINIMUM 6 characters):")
    # print(">>Waiting for the client/other person to connect...")
    connection_choice = True
    SERVER_IP = str()
    port = str()
    public_ip = str()
    SERVER_PORT = 1234
    password = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    while connection_choice:
        print("\n")
        choice = input("Choose an option(1 or 2):")
        if choice == "1" or choice == "2":
            os.system("cls")
            print(">>NOTE: This program will allow you to CONTROL other computer Desktop.")
            print("\n")
            print(">>Remote control details")
            if choice == "1":
                SERVER_IP = socket.gethostbyname(socket.gethostname())          # Local IP
                public_ip = requests.get('https://api.ipify.org').text
                print(f"LOCAL IP      --> {SERVER_IP:12} (Works when on same wifi or network)")
                print(f"PUBLIC IP     --> {public_ip:12} (Works when on different network and port forwarding is done)")
                print(f"Port no       --> {SERVER_PORT}")
            elif choice == "2":
                SERVER_IP = "127.0.0.1"
                SERVER_NAME, port = setup_ngrok()
                print(f"Computer name --> {SERVER_NAME} (Works in any network scenario)")
                print(f"Port no       --> {port}")
            print(f"Password      --> {password}")
            print("\n")
            print("Waiting for the other computer to connect...")
            connection_choice = False
        else:
            print("Invalid option.Choose either 1 or 2")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((SERVER_IP, SERVER_PORT))
    s.listen(1)
    accept_request = True
    while accept_request:
        clientsocket, address = s.accept()
        print("\n")
        print(f"Login request from {address[0]}...")
        pass_recv = connection.receive_data(clientsocket, 2, bytes(), 1024)
        if pass_recv[0].decode("utf-8") == password:
            connection.send_data(clientsocket, 2, bytes("1", "utf-8"))  # success_code--> 1
            print("\n")
            print(f"Connection from {address} has been established!")
            choice = connection.retry("Disable the remote computer wallpaper?(recommended):")
            connection.send_data(clientsocket, 2, bytes(str(choice), "utf-8"))  # wallpaper_settings
            print("\n")
            print(f">>You can now CONTROL {address[0]} desktop")
            accept_request = False
        else:
            connection.send_data(clientsocket, 2, bytes("0", "utf-8"))  # failure_code--> 0
            print(f"Wrong password entered by {address[0]}")
            clientsocket.close()

    client_resolution = connection.receive_data(clientsocket, 2, bytes(), 1024)[0].decode("utf-8")
    client_width, client_height = client_resolution.split(",")

    display_width, display_height = compare_and_compute_resolution(int(client_width), int(client_height), server_width,
                                                                   server_height)
    # display_msg = bytes(str(display_width) + "," + str(display_height), "utf-8")
    # connection.send_data(clientsocket, 2, display_msg)
    if (client_width, client_height) != (display_width, display_height):
        resize_option = True

    jpeg_sync_queue = Multiprocess_queue()

    thread1 = Thread(target=recv_and_put_into_queue, args=(clientsocket, jpeg_sync_queue), daemon=True)
    thread1.start()

    listener_key = Key_listener(on_press=on_press, on_release=on_release)
    listener_key.start()

    mouse_event_queue = Multiprocess_queue()
    process1 = Process(target=get_mouse_data_from_queue, args=(clientsocket, mouse_event_queue, resize_option,
                                                               int(client_width), int(client_height), display_width,
                                                               display_height), daemon=True)
    process1.start()

    button_code = {Button.left: (1, 4), Button.right: (2, 5), Button.middle: (3, 6)}

    listener_mouse = Mouse_listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
    listener_mouse.start()

    process2 = Process(target=display_data, args=(jpeg_sync_queue, display_width, display_height, resize_option),
                       daemon=True)
    process2.start()
    process2.join()
    process1.kill()
    process1.join()
    listener_key.stop()
    listener_key.join()
    listener_mouse.stop()
    listener_mouse.join()
    execute_thread = False
    thread1.join()
    # print("Main process ended")
    # print(f"Process 1: {process1.is_alive()}")
    # print(f"Process 2: {process2.is_alive()}")
    # print(f"Thread 1: {thread1.is_alive()}")
    # print(f"Thread 1(dameon): {thread1.isDaemon()}")
    # print(f"mouse: {listener_mouse.is_alive()}")
    # print(f"mouse(dameon): {listener_mouse.isDaemon()}")
    # print(f"keyboard: {listener_key.is_alive()}")
    # print(f"keyboard(dameon): {listener_key.isDaemon()}")
    # print("main process terminated")
    # sys.exit()

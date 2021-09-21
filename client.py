import socket
import mss
import connection
import sys
import os
import time
import ctypes
import lz4.frame
from PIL import Image,  ImageGrab
from io import BytesIO
from multiprocessing import Process, Queue, freeze_support
from pynput.mouse import Button, Controller as Mouse_controller
from pynput.keyboard import Key, Controller as Keyboard_controller


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
        time.sleep(10)
        sock.close()


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


if __name__ == "__main__":
    freeze_support()
    client_width, client_height = ImageGrab.grab().size
    # resize_option = False
    execute = True
    PATH = get_desktop_background_path()
    SERVER_IP = str()
    SERVER_PORT = int()
    while execute:
        try:
            os.system("cls")
            print(">>>   Remote Desktop Application   (Coded By: 'ADARSH SINGH' @Overflow) <<<")
            print(">>NOTE: This program will GIVE other computer your Desktop control.")
            print("\n")

            if SERVER_IP:
                option = connection.retry(f"Connect to {SERVER_IP} on port {SERVER_PORT}? If YES enter 'Y' else enter 'N':")
                if not option:
                    SERVER_IP = input("Enter the other computer IP/name to connect to:")
                    SERVER_PORT = int(input("Enter the port no:"))
            else:
                SERVER_IP = input("Enter the other computer IP/name to connect to:")
                SERVER_PORT = int(input("Enter the port no:"))

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((SERVER_IP, SERVER_PORT))
            SERVER_PASS = bytes(input("Enter the password set by the other computer:"), "utf-8")
            connection.send_data(s, 2, SERVER_PASS)      # send password
            login = connection.receive_data(s, 2, bytes(), 1024)

            if login[0].decode("utf-8") != "1":
                print("WRONG Password!..")
                # print("\n")
                if not connection.retry(">>Want to try again? If YES enter 'Y' else to exit enter 'N':"):
                    sys.exit()
            else:
                print("\n")
                print("Connected to the remote computer!")
                disable_wallpaper = connection.receive_data(s, 2, bytes(), 1024)
                if disable_wallpaper[0].decode("utf-8") == "True":
                    set_desktop_background("")
                print(f"Your Desktop is being remotely controlled now!")
                execute = False

        except OSError as e:
            print(e.strerror)
            print("\n")
            if not connection.retry(">>Want to try again? If YES enter 'Y' else to exit enter 'N':"):
                sys.exit()
            # print(f"ERROR no {e.errno} occurred exiting the program ..... ")

    resolution_msg = bytes(str(client_width) + "," + str(client_height), "utf-8")
    connection.send_data(s, 2, resolution_msg)  # send display resolution

    # resolution_msg = connection.receive_data(s, 2, bytes(), 1024)[0].decode("utf-8")
    # display_width, display_height = resolution_msg.split(",")
    # if (client_width, client_height) != (display_width, display_height):
    #     resize_option = True

    screenshot_sync_queue = Queue(1)
    process1 = Process(target=capture_screenshot, args=(screenshot_sync_queue, client_width, client_height), daemon=True
                       )
    process1.start()

    process2 = Process(target=get_from_queue_and_send, args=(screenshot_sync_queue, s), daemon=True)
    process2.start()

    process3 = Process(target=receive_events, args=(s, PATH))
    process3.start()
    process3.join()

import socket
import mss
import connection
import sys
import os
import time
from PIL import Image,  ImageGrab
from io import BytesIO
# from queue import Queue
from threading import Thread
from multiprocessing import Process, Queue
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
    elif event_code == 10:
        dx, dy = msg.split(",")
        mouse.scroll(int(dx), int(dy))
    elif event_code in (1, 2, 3):
        mouse.press(find_button(button_code, event_code))
    elif event_code in (4, 5, 6):
        mouse.release(find_button(button_code, event_code))
    elif event_code in (7, 8, 9):
        mouse.click(find_button(button_code, event_code), count=2)


def receive_events(sock):
    mouse = Mouse_controller()
    button_code = {(1, 4, 7): Button.left, (2, 5, 8): Button.right, (3, 6, 9): Button.middle}

    keyboard = Keyboard_controller()
    key_map = dict()
    for key_enum in Key:
        key_map.setdefault(key_enum.name, key_enum)

    header_size = 2
    partial_prev_msg = bytes()

    try:
        while True:
            msg = connection.receive_data(sock, header_size, partial_prev_msg)
            if msg:
                data = msg[0].decode("utf-8")
                event_code = int(data[:2])
                simulate(mouse, keyboard, button_code, key_map, event_code, data[2:])     # msg[0]--> new msg
                partial_prev_msg = msg[1]                                                 # msg[1]--> partial_prev_msg
    except (ConnectionAbortedError, ConnectionResetError, OSError) as exception_obj:
        print(exception_obj.strerror)
        time.sleep(15)
        sock.close()
        sys.exit()


def capture_screenshot(screenshot_queue):
    sct = mss.mss()
    sct.compression_level = 6
    mon = {"top": 0, "left": 0, "width": client_width, "height": client_height}
    capture = True
    while capture:
        screenshot = sct.grab(mon)
        pil_image_obj = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        buffer = BytesIO()
        # if resize:
        #     pil_image_obj = pil_image_obj.resize(display_width, display_height)
        pil_image_obj.save(buffer, format='jpeg', quality=15)
        screenshot_queue.put(buffer.getvalue())
        buffer.close()


def get_from_queue_and_send(screenshot_queue, sock):
    header_size = 10
    try:
        while True:
            jpeg_data = screenshot_queue.get()
            connection.send_data(sock, header_size, jpeg_data)
    except (ConnectionAbortedError, ConnectionResetError, OSError) as exception_obj:
        print(exception_obj.strerror)
        time.sleep(15)
        sock.close()
        sys.exit()


def retry(msg):
    check = True
    while check:
        choice = input(msg)
        if choice.lower() == "y":
            return True
        elif choice.lower() == "n":
            return False


if __name__ == "__main__":
    client_width, client_height = ImageGrab.grab().size
    # resize_option = False
    execute = True
    SERVER_IP = ""
    while execute:
        try:
            os.system("cls")
            print(">>REMOTE DESKTOP APPLICATION(Author: 'Adarsh Singh' @Overflow)")
            print(">>NOTE: This program will GIVE other person your Desktop control.")
            print("\n")

            if SERVER_IP:
                option = retry(f"connect to {SERVER_IP}? If YES enter 'Y' else enter 'N':")
                if not option:
                    SERVER_IP = input("Enter the server IP to connect to:")
            else:
                SERVER_IP = input("Enter the server IP to connect to:")

            SERVER_PORT = 1234

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((SERVER_IP, SERVER_PORT))
            SERVER_PASS = bytes(input("Enter the password to connect to the server:"), "utf-8")
            connection.send_data(s, 2, SERVER_PASS)      # send password
            login = connection.receive_data(s, 2, bytes(), 1024)

            if login[0].decode("utf-8") != "1":
                print("WRONG Password!..")
                print("\n")
                if not retry(">>Try again? If YES enter 'Y' else to exit enter 'N':"):
                    sys.exit()
            else:
                print("Connected to the server!")
                print(f"{SERVER_IP} can CONTROL your Desktop now..")
                execute = False

        except OSError as e:
            print(e.strerror)
            print("\n")
            if not retry(">>Try again? If YES enter 'Y' else to exit enter 'N':"):
                sys.exit()
            # print(f"ERROR no {e.errno} occurred exiting the program ..... ")

    resolution_msg = bytes(str(client_width) + "," + str(client_height), "utf-8")
    connection.send_data(s, 2, resolution_msg)  # send display resolution

    # resolution_msg = connection.receive_data(s, 2, bytes(), 1024)[0].decode("utf-8")
    # display_width, display_height = resolution_msg.split(",")
    # if (client_width, client_height) != (display_width, display_height):
    #     resize_option = True

    screenshot_sync_queue = Queue(15)
    thread1 = Thread(target=capture_screenshot, args=(screenshot_sync_queue,), daemon=True)
    thread1.start()

    process1 = Process(target=receive_events, args=(s,), daemon=True)
    process1.start()

    process2 = Process(target=get_from_queue_and_send, args=(screenshot_sync_queue, s), daemon=True)
    process2.start()
    process2.join()

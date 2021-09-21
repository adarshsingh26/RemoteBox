# RemoteBox

[![GitHub](https://img.shields.io/badge/--181717?logo=github&logoColor=ffffff)](https://github.com/adarshsingh26)
[![Python](https://img.shields.io/badge/python-3.7%7C3.8%7C3.9-blue)](https://www.python.org/) 
[![MIT License](https://img.shields.io/badge/license-MIT-blueviolet)](https://github.com/adarshsingh26/ADCOIN/blob/master/LICENSE) 
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/adarshsingh26/ADCOIN/graphs/commit-activity)
[![OpenSource](https://img.shields.io/badge/OpenSource-Yes-brightgreen)](https://opensource.com/resources/what-open-source)


RemoteBox is a `multithreaded` remote desktop application where client can authenticate 
with the remote system using a password and then `view and control the remote desktop`
using the mouse and keyboard as well as chat and transfer files at the same time. 
No networking library used ,`implemented a communication protocol` over the TCP sockets 
for connectivity between system and multithreading to achieve concurrency.

## Table Of Contents

 - [Demo (Coming Soon)]() 
 - [Tech Stack](#tech-stack)
 - [Features](#features)
 - [ToDo](#todo)
 - [Who can use it?](#who-can-use-it)
 - [Repo contents](#repo-contents)
 - [Getting Started](#getting-started)
 - [Overview of how the system works](#overview-of-how-the-system-works) 
 - [Tests](#tests)

## Tech Stack
- **Backend:** `Python 3.7` 
- **GUI:** `Tkinter`

## Features
- Authentication (Random password for each session)
- Multiple option for connectivity (LAN or WAN IP or using ngrok hostname)
- View remote desktop
- Control remote desktop using mouse(move,clicks) and keyboard(single keystrokes,hotkey)
- Chat with remote system
- File transfer(In progress)
- Disable remote desktop wallpaper for the session(Improves fps) 
- Event Logs 
- Connection Status(Listening for connection or Connection Established)
- Multithreaded application 

`Note:` No files touch the disk , it **runs within memory**, hence **improved performace** and no disk usage.

## ToDo
- File Transfer(Core Logic Done,working on custom file manager UI)
- Add to Startup
- Upnp Support

## Who can use it
- `IT administrators`,`System admin` could use it to maintain,transfer files or patch the system remotely. `Any user` could use it as long as they want to access the system remotely.

## Repo contents
- `server.py :` - Contains functions for starting a listener on the system for incoming connections,generating random password for each sssion and live streaming the screen to the client and to simulate the mouse and keyboard commands recieved from the client and much more.
- `client.py` - It contains code for computing the display resolution in which to show the remote stream(client and server can have different display resoltuion).Hooking mouse and keyboard input and sending it to the server and much more.  
- `connection.py` - Implemented a protocol on top of tcp sockets which ensures that communication between two systems is established.Both the client and server uses this to send/recieve any data.  

## Getting Started
1) Clone repo
- `git clone https://github.com/adarshsingh26/RemoteBox.git`

2) Download and install Python 3.8 and make sure to add the path of python into environament variable.

3) Lets create the virtual environment.
- `python -m venv c:\path\to\RemoteBox\myenv`

4) Change directory to root of project and activate the virtual environment.
- `cd c:\users\RemoteBox`
- `myenv\Scripts\activate`


5) Install the modules required to run the project
-  `Navigate to root of project`
- `pip install requirements.txt`


5) If u are the server then you ned to execute server.py
- `python server.py`
 
6) If client then
- `python client.py`

## Overview of how the system works
<p align="center">
   <img src="https://user-images.githubusercontent.com/84853854/134013352-6e7c5415-825a-4c94-b17f-bf85622b4691.png" alt="client-server"/>
</p>

**`On server side:`**
1) Creates a `listener` for incoming connections based on whether the user chose to listen on a ip or the hostname and then show the relevant information to the user, using which remote machines could connect to the system. 

2) Then once connection is established, it starts capturing the screenshot of desktop using `mss`(fast screenshot capturing module), if remote desktop view requested by the client.

3) `Compresses` the screenshot within the memory using `lz4` compression.

4) Stores the `compressed image` in the queue.

5) Gets the data from the `screenshot queue` and sends it to the server.

6) Concurrently the server recieves mouse,keyboard events from the remote machine and `simulates` those actions onto the system.

**`On client side:`**

1) Client first gets the option to `login` to the remote system using its credentials.

2) Once the connection is established user will be shown the options to `view remote desktop` , `chat` or `file transfer`.

3) When user clicks the remote desktop view , he gets the prompt whether to `disable the background` image or not and based on the response information is conveyed to the server.

4) Now the client asks the server for its display resolution and then `compare and computes the client display window resolution` and shows the remote desktop.

5) As the client starts interacting with the remote machine using mouse and keyboard, their `mouse co-ordinates` and key strokes are hooked and put into a queue and data from the queue is `concurently sent` to the remote system.
 
6) Mouse co-ordinates are `scaled` if needed.

`Note:` This is just a short summary much more things are happening behind the scenes .Take a look at code to know more :) 

## Tests
- Tested on `Windows 7,8,10,11` machine.
- Even if the client or server looses the connection in between no error is thrown.(`Exception handling` has been done properly). 



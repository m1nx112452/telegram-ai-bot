import os
import threading
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "🤖 AriaBot 24/7 Web Server is Active!"

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    import bot
    bot.main()

import threading
import time
import uvicorn

class DatabricksBackgroundServer(uvicorn.Server):
    def install_signal_handlers(self):
        # Override to prevent conflicts with the active IPython kernel
        pass

# Configure to listen purely on localhost within the driver instance
config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_config=None)
server = DatabricksBackgroundServer(config=config)

# Execute via a daemonized background thread
server_thread = threading.Thread(target=server.run, daemon=True)
server_thread.start()

# Give the server an instant to initialize ports cleanly
time.sleep(1)
print("FastAPI background process successfully started on http://127.0.0.1:8000")

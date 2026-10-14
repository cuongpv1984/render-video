"""Supervise one API process and one DB worker in the pilot container."""
import multiprocessing
import os
import signal
import time

def api():
    import uvicorn
    uvicorn.run("app.main:app",host="0.0.0.0",port=8080,log_level="info")

def worker():
    from .worker import main
    main()

if __name__=="__main__":
    processes=[multiprocessing.Process(target=api),multiprocessing.Process(target=worker)]
    for p in processes:p.start()
    def stop(*_):
        for p in processes:
            if p.is_alive():p.terminate()
        for p in processes:p.join(timeout=10)
        for p in processes:
            if p.is_alive():p.kill();p.join()
    signal.signal(signal.SIGTERM,stop)
    try:
        while all(p.is_alive() for p in processes):time.sleep(1)
    finally:
        stop()
    raise SystemExit(1)

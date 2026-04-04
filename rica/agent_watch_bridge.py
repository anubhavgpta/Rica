"""Watch bridge for Rica L18 autonomous agent background file watching."""

import queue
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from .models import WatchEvent
from .watcher import FileWatcher


class WatchBridge:
    """Bridge for running FileWatcher in background thread with event queue."""
    
    def __init__(self):
        self._watcher: Optional[FileWatcher] = None
        self._thread: Optional[threading.Thread] = None
        self._event_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._watch_path: Optional[str] = None
        self._watch_lang: Optional[str] = None
    
    def start(self, path: str, lang: Optional[str] = None) -> None:
        """Start FileWatcher in a daemon thread."""
        if self.is_alive():
            self.stop()
        
        self._watch_path = path
        self._watch_lang = lang
        self._stop_event.clear()
        self._event_queue = queue.Queue()
        
        # Start watcher thread
        self._thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name=f"WatchBridge-{path}"
        )
        self._thread.start()
    
    def stop(self) -> None:
        """Stop the watcher thread."""
        if self._watcher:
            self._watcher.stop()
        
        self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        self._watcher = None
        self._thread = None
    
    def is_alive(self) -> bool:
        """Check if watcher thread is alive."""
        return self._thread is not None and self._thread.is_alive()
    
    def drain_events(self) -> list[WatchEvent]:
        """Non-blocking pop all events from queue."""
        events = []
        while True:
            try:
                event = self._event_queue.get_nowait()
                events.append(event)
            except queue.Empty:
                break
        return events
    
    def _watch_loop(self) -> None:
        """Background thread loop for file watching."""
        try:
            # Create and start the FileWatcher
            self._watcher = FileWatcher()
            self._watcher.start(
                path=self._watch_path,
                lang=self._watch_lang,
                callback=self._on_watch_event
            )
            
            # Keep thread alive until stop is called
            while not self._stop_event.is_set():
                time.sleep(0.1)
                
        except Exception as e:
            # Push error event to queue
            error_event = WatchEvent(
                path=self._watch_path or "",
                issues=[{"error": str(e)}],
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            self._event_queue.put(error_event)
        
        finally:
            if self._watcher:
                try:
                    self._watcher.stop()
                except Exception:
                    pass  # Ignore cleanup errors
    
    def _on_watch_event(self, path: str, issues: list[dict]) -> None:
        """Callback for FileWatcher events."""
        event = WatchEvent(
            path=path,
            issues=issues,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        self._event_queue.put(event)

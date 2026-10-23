"""An explicit click offers a copied YouTube URL; dragging always keeps file actions."""
import time
from urllib.parse import urlsplit
from link_selection import media_link


def youtube_link(text):
    value=media_link(text)
    if not value:return None
    host=urlsplit(value).hostname.lower().rstrip('.')
    if host=='youtu.be' or host=='youtube.com' or host.endswith('.youtube.com'):
        return value
    return None


class ClipboardGesture:
    def __init__(self):self.reset()
    def reset(self,left=False):
        self.left=left;self.held=False;self.pending=None;self.press_point=None;self.press_time=0
    def update(self,left,held,point,token,read_clipboard,now=None):
        now=time.monotonic() if now is None else now
        was_left,was_held=self.left,self.held
        self.left,self.held=left,held
        if left and not was_left:self.press_point=point;self.press_time=now
        if self.pending:
            url,origin,window,started=self.pending
            moved=(point[0]-origin[0])**2+(point[1]-origin[1])**2>64
            if moved or not held or token!=window or now-started>1.2:
                self.pending=None
                return ('drag' if left and held and token==window else None),None
            if not left:
                self.pending=None
                # Do not act on clipboard content that changed during the click.
                return ('click',url) if youtube_link(read_clipboard())==url else (None,None)
            return 'pending',None
        if left and held and (not was_left or not was_held):
            # A file may already have moved before the modifier is pressed.
            # Measure from mouse-down, not from the later key press.
            origin=self.press_point
            if origin is None or now-self.press_time>1.2 or (point[0]-origin[0])**2+(point[1]-origin[1])**2>64:return None,None
            url=youtube_link(read_clipboard())
            if url:
                self.pending=(url,origin,token,self.press_time)
                return 'pending',None
        return None,None

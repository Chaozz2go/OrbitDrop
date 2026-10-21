from hashlib import sha256
from pathlib import Path
from PySide6.QtCore import QLockFile,QObject,Signal
from PySide6.QtNetwork import QLocalServer,QLocalSocket

class SingleInstance(QObject):
    activated=Signal()
    def __init__(self,root):
        super().__init__();root=Path(root);root.mkdir(parents=True,exist_ok=True)
        self.name='OrbitDrop-'+sha256(str(root.resolve()).encode()).hexdigest()[:20]
        self.lock=QLockFile(str(root/'instance.lock'));self.lock.setStaleLockTime(0)
        self.server=None
    def acquire(self):
        if not self.lock.tryLock(0):
            client=QLocalSocket();client.connectToServer(self.name)
            if client.waitForConnected(800):client.write(b'activate');client.flush();client.waitForBytesWritten(500);client.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        self.server=QLocalServer(self);self.server.newConnection.connect(self._connected)
        if not self.server.listen(self.name):
            # The lock is sufficient to prevent a second process. Some systems
            # block local IPC; activation then remains unavailable without
            # preventing the first process from starting.
            self.server_error=self.server.errorString()
            self.server.close();self.server=None
        return True
    def _connected(self):
        connection=self.server.nextPendingConnection()
        if connection:
            connection.disconnectFromServer();connection.deleteLater()
        self.activated.emit()
    def release(self):
        if self.server:self.server.close()
        self.lock.unlock()

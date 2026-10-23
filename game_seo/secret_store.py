"""Windows DPAPI, bound to the current Windows user; no plaintext secrets on disk."""
import base64
import ctypes
import os
from ctypes import wintypes


def transform(value, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Secret storage requires Windows DPAPI on this installation.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError('Windows credential protection failed.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


class Secrets:
    def __init__(self, store):
        self.store = store

    def put(self, key, value):
        encrypted = base64.b64encode(transform(value.encode('utf-8'))).decode('ascii')
        with self.store.connection() as db:
            db.execute('INSERT OR REPLACE INTO secure_values VALUES(?,?)', (key, encrypted))

    def get(self, key):
        with self.store.connection() as db:
            row = db.execute('SELECT ciphertext FROM secure_values WHERE id=?', (key,)).fetchone()
        if not row:
            return None
        return transform(base64.b64decode(row[0]), decrypt=True).decode('utf-8')

    def delete(self, key):
        with self.store.connection() as db:
            db.execute('DELETE FROM secure_values WHERE id=?', (key,))

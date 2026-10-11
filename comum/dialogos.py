"""BRFP Super Tool — diálogos nativos do Windows (abrir, salvar, escolher pasta) sem tkinter.

O Python embutido do Super Tool (runtime/python) não traz o tkinter; estes diálogos usam direto o IFileOpenDialog /
IFileSaveDialog do Windows (o mesmo que o Explorer usa) por ctypes. Cada diálogo roda num processo à parte, para não
prender nem derrubar o servidor da ferramenta:

    escolher(modo="abrir" | "salvar" | "pasta", titulo="", inicial=None, tipos=[(nome, "*.png *.jpg")], multiplo=False,
             nome="", extensao="")  -> caminho, lista de caminhos (multiplo) ou None (cancelado)

Linha de comando (usada por escolher): python dialogos.py '<json com os mesmos campos>'  -> imprime o JSON do resultado.
Fora do Windows usa o tkinter, se existir.
"""
import json
import os
import subprocess
import sys

ESTE = os.path.abspath(__file__)


def escolher(modo="abrir", titulo="", inicial=None, tipos=None, multiplo=False, nome="", extensao="", python=None):
    args = {"modo": modo, "titulo": titulo or "", "inicial": inicial or "", "tipos": [list(t) for t in (tipos or [])],
            "multiplo": bool(multiplo), "nome": nome or "", "extensao": extensao or ""}
    try:
        r = subprocess.run([python or sys.executable, ESTE, json.dumps(args)], capture_output=True, text=True,
                           timeout=1800, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = json.loads((r.stdout or "").strip() or "null")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None
    if not out:
        return None
    if isinstance(out, list):
        return [os.path.normpath(p) for p in out]
    return os.path.normpath(out)


# ------------------------------------------------------------------ Windows: IFileDialog por ctypes
def _windows(a):
    import ctypes
    from ctypes import wintypes

    ole32 = ctypes.OleDLL("ole32")
    shell32 = ctypes.OleDLL("shell32")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32")
    ole32w = ctypes.WinDLL("ole32")                              # funções sem HRESULT (CoTaskMemFree)
    ole32w.CoTaskMemFree.restype = None
    ole32w.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    for nome, res, args in (("GetForegroundWindow", wintypes.HWND, []),
                            ("GetWindowThreadProcessId", wintypes.DWORD, [wintypes.HWND, wintypes.LPVOID]),
                            ("AttachThreadInput", wintypes.BOOL, [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]),
                            ("SetForegroundWindow", wintypes.BOOL, [wintypes.HWND]),
                            ("ShowWindow", wintypes.BOOL, [wintypes.HWND, ctypes.c_int]),
                            ("DestroyWindow", wintypes.BOOL, [wintypes.HWND]),
                            ("CreateWindowExW", wintypes.HWND, [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                                                 wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                                                 ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                                                 wintypes.HINSTANCE, wintypes.LPVOID])):
        f = getattr(user32, nome)
        f.restype, f.argtypes = res, args

    class GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

    def guid(s):
        g = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
        return g

    class FILTRO(ctypes.Structure):
        _fields_ = [("nome", wintypes.LPCWSTR), ("padrao", wintypes.LPCWSTR)]

    def metodo(obj, indice, *argtypes):
        """Método 'indice' da vtable da interface COM 'obj' (HRESULT como inteiro, sem exceção automática)."""
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[indice])
        return lambda *x: fn(obj, *x)

    def ok(hr, onde):
        if hr < 0:
            raise OSError(f"{onde}: 0x{hr & 0xFFFFFFFF:08X}")

    def liberar(obj):
        if obj:
            metodo(obj, 2)()

    def caminho_do_item(item):
        p = ctypes.c_void_p()
        ok(metodo(item, 5, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(ctypes.c_int(-2147123200), ctypes.byref(p)),
           "GetDisplayName")                                    # SIGDN_FILESYSPATH = 0x80058000
        try:
            return ctypes.wstring_at(p.value)
        finally:
            ole32w.CoTaskMemFree(p)

    ERRO_CANCELADO = -2147023673                                 # HRESULT_FROM_WIN32(ERROR_CANCELLED) = 0x800704C7
    FOS_OVERWRITEPROMPT, FOS_NOCHANGEDIR, FOS_PICKFOLDERS, FOS_FORCEFILESYSTEM = 0x2, 0x8, 0x20, 0x40
    FOS_ALLOWMULTISELECT, FOS_PATHMUSTEXIST, FOS_FILEMUSTEXIST = 0x200, 0x800, 0x1000

    ole32.CoInitializeEx(None, 0x2 | 0x4)                        # COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE
    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass
    modo = a.get("modo") or "abrir"
    salvar = modo == "salvar"
    clsid = guid("{C0B4E2F3-BA21-4773-8DBA-335EC946EB8B}" if salvar else "{DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7}")
    iid = guid("{84bccd23-5fde-4cdb-aea4-af64b83d78ab}" if salvar else "{d57c7288-d4ad-4768-be02-9d969532d960}")
    dlg = ctypes.c_void_p()
    ok(ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(dlg)), "CoCreateInstance")
    dono = None
    vivos = []                                                   # mantém vivos os buffers passados ao COM
    try:
        opcoes = wintypes.DWORD()
        ok(metodo(dlg, 10, ctypes.POINTER(wintypes.DWORD))(ctypes.byref(opcoes)), "GetOptions")
        o = opcoes.value | FOS_FORCEFILESYSTEM | FOS_NOCHANGEDIR | FOS_PATHMUSTEXIST
        if modo == "pasta":
            o |= FOS_PICKFOLDERS
        elif salvar:
            o |= FOS_OVERWRITEPROMPT
        else:
            o |= FOS_FILEMUSTEXIST | (FOS_ALLOWMULTISELECT if a.get("multiplo") else 0)
        ok(metodo(dlg, 9, wintypes.DWORD)(o), "SetOptions")

        tipos = [t for t in (a.get("tipos") or []) if len(t) == 2] if modo != "pasta" else []
        if tipos:
            arr = (FILTRO * len(tipos))()
            for i, (n, padrao) in enumerate(tipos):
                padrao = ";".join(p for p in str(padrao).replace(",", " ").replace(";", " ").split() if p)
                arr[i].nome, arr[i].padrao = str(n), padrao or "*.*"
            vivos.append(arr)
            ok(metodo(dlg, 4, wintypes.UINT, ctypes.POINTER(FILTRO))(len(tipos), arr), "SetFileTypes")
        if a.get("titulo"):
            metodo(dlg, 17, wintypes.LPCWSTR)(a["titulo"])
        if a.get("nome") and modo != "pasta":
            metodo(dlg, 15, wintypes.LPCWSTR)(a["nome"])
        if salvar and a.get("extensao"):
            metodo(dlg, 22, wintypes.LPCWSTR)(a["extensao"].lstrip("."))
        inicial = a.get("inicial") or ""
        if inicial and not os.path.isdir(inicial):
            inicial = os.path.dirname(inicial)
        if inicial and os.path.isdir(inicial):
            item = ctypes.c_void_p()
            iid_item = guid("{43826d1e-e718-42ee-bc55-a1e261c37bfe}")
            try:
                shell32.SHCreateItemFromParsingName(ctypes.c_wchar_p(os.path.abspath(inicial)), None,
                                                    ctypes.byref(iid_item), ctypes.byref(item))
                metodo(dlg, 12, ctypes.c_void_p)(item)               # SetFolder
            except OSError:
                pass
            finally:
                liberar(item)

        # dono invisível e "sempre no topo": o diálogo aparece na frente do Super Tool (que é de outro processo)
        larg, alt = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        dono = user32.CreateWindowExW(0x8 | 0x80, "STATIC", a.get("titulo") or "BRFP", 0x80000000,  # TOPMOST|TOOLWINDOW, POPUP
                                      larg // 2 - 400, alt // 2 - 300, 0, 0, None, None, None, None)
        if dono:
            frente = user32.GetForegroundWindow()
            meu, dele = kernel32.GetCurrentThreadId(), user32.GetWindowThreadProcessId(frente, None) if frente else 0
            ligado = bool(dele and dele != meu and user32.AttachThreadInput(meu, dele, True))
            user32.ShowWindow(dono, 5)
            user32.SetForegroundWindow(dono)
            if ligado:
                user32.AttachThreadInput(meu, dele, False)

        hr = metodo(dlg, 3, wintypes.HWND)(dono)                     # Show
        if hr == ERRO_CANCELADO:
            return None
        ok(hr, "Show")
        if modo == "abrir" and a.get("multiplo"):
            lista = ctypes.c_void_p()
            ok(metodo(dlg, 27, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(lista)), "GetResults")
            try:
                n = wintypes.DWORD()
                ok(metodo(lista, 7, ctypes.POINTER(wintypes.DWORD))(ctypes.byref(n)), "GetCount")
                out = []
                for i in range(n.value):
                    item = ctypes.c_void_p()
                    ok(metodo(lista, 8, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(i, ctypes.byref(item)), "GetItemAt")
                    try:
                        out.append(caminho_do_item(item))
                    finally:
                        liberar(item)
                return out
            finally:
                liberar(lista)
        item = ctypes.c_void_p()
        ok(metodo(dlg, 20, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(item)), "GetResult")
        try:
            return caminho_do_item(item)
        finally:
            liberar(item)
    finally:
        if dono:
            user32.DestroyWindow(dono)
        liberar(dlg)


def _tkinter(a):
    import tkinter as tk
    import tkinter.filedialog as fd
    r = tk.Tk()
    r.withdraw()
    r.attributes("-topmost", True)
    tipos = [(n, p.replace(";", " ")) for n, p in (a.get("tipos") or [])] or [("Todos", "*.*")]
    k = dict(title=a.get("titulo") or "", initialdir=a.get("inicial") or None)
    if a["modo"] == "pasta":
        return fd.askdirectory(mustexist=True, **k) or None
    if a["modo"] == "salvar":
        return fd.asksaveasfilename(filetypes=tipos, initialfile=a.get("nome") or "",
                                    defaultextension=a.get("extensao") or "", **k) or None
    if a.get("multiplo"):
        return list(fd.askopenfilenames(filetypes=tipos, **k) or []) or None
    return fd.askopenfilename(filetypes=tipos, **k) or None


def main():
    a = json.loads(sys.argv[1])
    try:
        out = _windows(a) if os.name == "nt" else _tkinter(a)
    except Exception as ex:  # noqa: BLE001
        sys.stderr.write(f"{type(ex).__name__}: {ex}\n")
        out = None
    sys.stdout.write(json.dumps(out))            # ASCII: independe da codificação do console


if __name__ == "__main__":
    main()

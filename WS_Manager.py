from __future__ import annotations
import ctypes, datetime, json, os, queue, re, shutil, subprocess, sys, threading, time, webbrowser, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import messagebox, scrolledtext, ttk, filedialog
import tkinter as tk
from typing import Dict, List, Optional, Tuple, Any

os.environ["PYTHONCOM__SKIP_REGISTRATION"] = "1"

if getattr(sys, 'frozen', False):
    APP_PATH = os.path.dirname(sys.executable)
else:
    APP_PATH = os.path.dirname(os.path.abspath(__file__))

ICON_PATH = os.path.join(APP_PATH, "icon.ico")
SERVICES_DB_FILE = os.path.join(APP_PATH, "services_database.json")

BG = "#F5F6FA"
BG2 = "#FFFFFF"
BG3 = "#EFF1F9"
CARD = "#FFFFFF"
ACCENT = "#5B5EF4"
ACCENT2 = "#7879F1"
DANGER = "#EF4444"
WARN = "#F59E0B"
OK = "#22C55E"
FG = "#1E1F2E"
FG2 = "#6B7280"
FG3 = "#9CA3AF"
SEL_BG = "#EEF0FD"
SEL_FG = "#3730A3"
BORDER = "#E2E4EF"
HEAD_BG = "#F0F1FB"
HEAD_FG = "#4B5563"

MAX_WORKERS = 50
BACKUP_DIR = os.path.join(APP_PATH, "backups")
DELETED_SERVICES_FILE = os.path.join(APP_PATH, "deleted_services.json")
SNAPSHOT_FILE = os.path.join(APP_PATH, "service_snapshot.json")
LOG_FILE = os.path.join(APP_PATH, "service_log.txt")
FIRST_RUN_FLAG = os.path.join(APP_PATH, ".first_run_done")
UNKNOWN_SERVICES_FILE = os.path.join(APP_PATH, "unknown_services.json")
os.makedirs(BACKUP_DIR, exist_ok=True)

PROTECTED_SERVICES = ["mpssvc", "WinDefend", "WdNisSvc", "WdFilter", "WdNisDrv", "SecurityHealthService", "Sense", "wscsvc", "SgrmBroker"]
CRITICAL_SERVICES = ["TrustedInstaller", "DcomLaunch", "RpcSs", "PlugPlay", "EventLog", "Power", "LSM", "KeyIso", "Dnscache", "Dhcp", "Netman", "Nsi", "RpcEptMapper", "SamSs", "Schedule", "Winmgmt"]

START_TYPE_MAP = {"auto": "🟢 Авто", "delayed": "🟡 Авто (отлож.)", "demand": "🔵 Вручную", "disabled": "🔴 Отключена", "boot": "🟣 Загрузочная", "system": "🟣 Системная", "unknown": "❓ Неизвестно"}
STATUS_MAP = {"running": "▶ Работает", "stopped": "■ Остановлена", "paused": "⏸ Приостановлена", "unknown": "? Неизвестно"}

USER_SUFFIX_SERVICES = frozenset(["CDPUserSvc", "PrintWorkflowUserSvc", "WpnUserService", "BluetoothUserService", "BcastDVRUserService", "DevicesFlowUserSvc", "OneSyncSvc", "UserDataSvc", "ConsentUxUserSvc", "UdkUserSvc", "DevicePickerUserSvc", "ClipboardUserService", "MessagingService", "PimIndexMaintenance", "ContactData", "UnistoreSvc", "CaptureService", "cbdhsvc", "DeviceAssociationBrokerSvc", "PimIndexMaintenanceSvc"])

_user_svc_cache = {}
_user_svc_cache_lock = threading.Lock()

RISK_LABEL = {"low": "✅ Безопасно", "medium": "⚠ Осторожно", "high": "🔴 Опасно", "unknown": "❓ Неизвестно"}

PRESETS = {
    "🎮 Максимум FPS (SSD)": {
        "categories": ["Телеметрия", "Xbox", "Поиск", "Производительность", "Диагностика"],
        "exclude_services": ["MMCSS", "AudioSrv", "AudioEndpointBuilder", "SysMain"],
        "desc": "Отключает телеметрию, Xbox, поиск, SysMain и другие службы снижающие FPS. Оптимизирован для SSD-накопителей."
    },
    "🎮 Максимум FPS (HDD)": {
        "categories": ["Телеметрия", "Xbox", "Поиск", "Производительность", "Диагностика"],
        "exclude_services": ["MMCSS", "AudioSrv", "AudioEndpointBuilder"],
        "desc": "Отключает телеметрию, Xbox, поиск и другие службы снижающие FPS. SysMain оставлен включённым для ускорения работы HDD."
    },
    "🔒 Приватность (безопасный)": {
        "categories": ["Телеметрия", "Геолокация", "Приватность", "Удалённый доступ", "Синхронизация", "Диагностика"],
        "exclude_services": [
            # Защищаем камеру и микрофон
            "SensorService", "SensorDataService", "SensorsApi", "SensorMonitor",
            # Защищаем Microsoft Store
            "InstallService", "StoreInstallService", "WSearch", "LicenseManager", 
            "AppXSvc", "ClipSVC", "BITS", "DoSvc", "WpnService", "WpnUserService",
            # Критичные для работы
            "BrokerInfrastructure", "CoreMessaging", "DcomLaunch", "RpcSs"
        ],
        "desc": "Отключает телеметрию, геолокацию, удалённый доступ и синхронизацию. Камера, микрофон и Microsoft Store остаются рабочими."
    }
}

GITHUB_URL = "https://github.com/Almarus/WS-manager"

_LOG_LOCK = threading.Lock()
_LOG_SIZE_LIMIT = 10 * 1024 * 1024

def append_log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _LOG_LOCK:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > _LOG_SIZE_LIMIT:
            try:
                shutil.copy2(LOG_FILE, LOG_FILE + f".{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.bak")
                open(LOG_FILE, "w").close()
            except:
                pass
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")

def load_services_database():
    if not os.path.exists(SERVICES_DB_FILE):
        return {}
    try:
        with open(SERVICES_DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

SERVICES = load_services_database()

def resolve_user_service_name(sid):
    with _user_svc_cache_lock:
        if sid in _user_svc_cache:
            return _user_svc_cache[sid]
    base_match = re.match(r'^(.+?)_[a-fA-F0-9]{4,6}$', sid)
    if base_match and (base_match.group(1) in USER_SUFFIX_SERVICES or base_match.group(1) in SERVICES):
        try:
            r = subprocess.run(["sc", "query", sid], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            if "SERVICE_NAME:" in r.stdout:
                with _user_svc_cache_lock:
                    _user_svc_cache[sid] = sid
                return sid
        except:
            pass
    if sid in USER_SUFFIX_SERVICES:
        try:
            r = subprocess.run(["wmic", "service", "where", f"name like '{sid}_%'", "get", "name"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in r.stdout.splitlines():
                name = line.strip()
                if name and "_" in name and name.startswith(sid):
                    with _user_svc_cache_lock:
                        _user_svc_cache[sid] = name
                    return name
        except:
            pass
    return sid

def run_sc(args, timeout=8):
    for enc in ["cp866", "utf-8", "windows-1251", "latin-1"]:
        try:
            r = subprocess.run(["sc"] + args, capture_output=True, text=True, encoding=enc,
                               errors="replace", creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
            return r.returncode, r.stdout + r.stderr
        except UnicodeDecodeError:
            continue
        except subprocess.TimeoutExpired:
            return -2, "timeout"
        except Exception as e:
            return -1, str(e)
    try:
        r = subprocess.run(["sc"] + args, capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
        return r.returncode, r.stdout.decode("utf-8", errors="ignore") + r.stderr.decode("utf-8", errors="ignore")
    except Exception as e:
        return -1, str(e)

def _parse_sc_query_status(output: str) -> str:
    """
    Парсим статус по числовому коду STATE — не зависит от локализации Windows.
    Коды: 1=Stopped, 2=Start_Pending, 3=Stop_Pending, 4=Running, 5=Continue_Pending,
          6=Pause_Pending, 7=Paused
    """
    for line in output.splitlines():
        line = line.strip()
        if re.match(r'STATE\s*:', line, re.IGNORECASE):
            m = re.search(r'STATE\s*:\s*(\d+)', line, re.IGNORECASE)
            if m:
                code = int(m.group(1))
                if code == 4:
                    return "running"
                elif code in (1, 3):
                    return "stopped"
                elif code == 7:
                    return "paused"
                else:
                    return "stopped"
    # Текстовый fallback
    upper = output.upper()
    if "RUNNING" in upper:
        return "running"
    elif "STOPPED" in upper:
        return "stopped"
    elif "PAUSED" in upper:
        return "paused"
    return "unknown"

def _parse_sc_qc_start_type(output: str) -> str:
    """
    Парсим тип запуска по числовому коду START_TYPE — не зависит от локализации.
    Коды: 0=Boot, 1=System, 2=Auto, 3=Demand, 4=Disabled
    Delayed-Auto определяется отдельной строкой DELAYED_AUTO_START : 1
    """
    start = "unknown"
    is_delayed = False
    for line in output.splitlines():
        line_strip = line.strip()
        if re.match(r'START_TYPE\s*:', line_strip, re.IGNORECASE):
            m = re.search(r'START_TYPE\s*:\s*(\d+)', line_strip, re.IGNORECASE)
            if m:
                code = int(m.group(1))
                if code == 0:
                    start = "boot"
                elif code == 1:
                    start = "system"
                elif code == 2:
                    start = "auto"
                elif code == 3:
                    start = "demand"
                elif code == 4:
                    start = "disabled"
        if re.match(r'DELAYED_AUTO_START\s*:', line_strip, re.IGNORECASE):
            m = re.search(r'DELAYED_AUTO_START\s*:\s*(\d+)', line_strip, re.IGNORECASE)
            if m and m.group(1) == "1":
                is_delayed = True
        # Текстовый fallback
        lo = line_strip.lower()
        if start == "unknown":
            if "delayed" in lo and "auto" in lo:
                is_delayed = True
                start = "auto"
            elif "auto_start" in lo or ("auto" in lo and "demand" not in lo and "disabled" not in lo):
                start = "auto"
            elif "demand_start" in lo or "demand" in lo or "manual" in lo:
                start = "demand"
            elif "disabled" in lo:
                start = "disabled"
            elif "boot_start" in lo or "boot" in lo:
                start = "boot"
            elif "system_start" in lo or "system" in lo:
                start = "system"
    if start == "auto" and is_delayed:
        start = "delayed"
    return start

def get_all_services_names():
    """
    PowerShell как основной метод (работает на всех версиях включая Win11 без WMIC).
    WMIC и sc query как fallback.
    """
    services = []
    # Метод 1: PowerShell Get-Service
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-Service | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, creationflags=subprocess.CREATE_NO_WINDOW
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                name = line.strip()
                if name and not name.startswith("_"):
                    services.append(name)
        if services:
            return services
    except:
        pass
    # Метод 2: WMIC
    try:
        result = subprocess.run(
            ['wmic', 'service', 'get', 'name', '/format:csv'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=10, creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                name = parts[-1].strip('"').strip()
                if name and not name.startswith("_"):
                    services.append(name)
        if services:
            return services
    except:
        pass
    # Метод 3: sc query
    try:
        r = subprocess.run(["sc", "query", "state=", "all"], capture_output=True,
                           text=True, encoding="cp866", errors="replace",
                           timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("SERVICE_NAME:"):
                name = line.split(":", 1)[1].strip()
                if name and not name.startswith("_"):
                    services.append(name)
    except:
        pass
    return services

def query_service(sid):
    """Статус через числовой парсинг sc query; тип запуска через sc qc с поддержкой delayed."""
    real = resolve_user_service_name(sid)
    status = "unknown"
    try:
        _, qout = run_sc(["query", real], timeout=5)
        status = _parse_sc_query_status(qout)
    except:
        pass
    start = "unknown"
    try:
        _, cout = run_sc(["qc", real], timeout=5)
        start = _parse_sc_qc_start_type(cout)
    except:
        pass
    return {"status": status, "start_type": start}

def get_service_dependencies_list(sid):
    """
    sc qc выводит зависимости на нескольких строках — парсим все строки до следующего заголовка.
    """
    real_sid = resolve_user_service_name(sid)
    code, cout = run_sc(["qc", real_sid], timeout=8)
    if code != 0:
        return []
    deps = []
    in_deps = False
    for line in cout.splitlines():
        line_strip = line.strip()
        if re.match(r'DEPENDENCIES\s*:', line_strip, re.IGNORECASE):
            in_deps = True
            parts = line_strip.split(":", 1)
            if len(parts) > 1:
                raw = parts[1].strip()
                for token in raw.split():
                    token = token.strip().rstrip('/').strip()
                    if token and token not in (":", "\\", "(", ")", "N/A", "/"):
                        if "/" in token:
                            token = token.split("/")[0].strip()
                        if token and token != real_sid:
                            deps.append(token)
            continue
        if in_deps:
            # Новый заголовок (без отступа + двоеточие) — конец блока зависимостей
            if line and not line[0].isspace() and ":" in line_strip:
                break
            for token in line_strip.split():
                token = token.strip().rstrip('/').strip()
                if token and token not in (":", "\\", "(", ")", "N/A", "/"):
                    if "/" in token:
                        token = token.split("/")[0].strip()
                    if token and token != real_sid:
                        deps.append(token)
    # Дедупликация с сохранением порядка
    seen = set()
    unique_deps = []
    for d in deps:
        if d not in seen:
            seen.add(d)
            unique_deps.append(d)
    return unique_deps

def stop_service(sid):
    real_sid = resolve_user_service_name(sid)
    c, _ = run_sc(["stop", real_sid], timeout=10)
    if c != 0 and sid in PROTECTED_SERVICES:
        return force_disable_protected_service(sid)
    return c == 0

def start_service(sid):
    c, _ = run_sc(["start", sid])
    if c != 0 and sid in PROTECTED_SERVICES:
        return force_enable_protected_service(sid)
    return c == 0

def disable_service(sid):
    if sid in CRITICAL_SERVICES:
        return False
    if sid in PROTECTED_SERVICES:
        return force_disable_protected_service(sid)
    real_sid = resolve_user_service_name(sid)
    stop_service(real_sid)
    c, _ = run_sc(["config", real_sid, "start=", "disabled"], timeout=10)
    if c != 0:
        try:
            key_path = f"SYSTEM\\CurrentControlSet\\Services\\{real_sid}"
            subprocess.run(["reg", "add", f"HKLM\\{key_path}", "/v", "Start", "/t", "REG_DWORD", "/d", "4", "/f"],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        except:
            pass
    run_sc(["triggerinfo", real_sid, "delete"], timeout=8)
    run_sc(["failure", real_sid, "reset=", "0", "actions="], timeout=8)
    if c != 0:
        return force_disable_protected_service(sid)
    return True

def force_disable_protected_service(sid):
    try:
        key_path = f"SYSTEM\\CurrentControlSet\\Services\\{sid}"
        check = subprocess.run(["reg", "query", f"HKLM\\{key_path}"], capture_output=True,
                               timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        if check.returncode != 0:
            return False
        subprocess.run(["reg", "add", f"HKLM\\{key_path}", "/v", "Start", "/t", "REG_DWORD", "/d", "4", "/f"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        if sid not in ["WinDefend", "mpssvc"]:
            subprocess.run(["reg", "add", f"HKLM\\{key_path}", "/v", "FailureActions", "/t", "REG_BINARY",
                            "/d", "00000000000000000000000000000000", "/f"],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        run_sc(["stop", sid])
        return True
    except:
        return False

def force_enable_protected_service(sid):
    try:
        key_path = f"SYSTEM\\CurrentControlSet\\Services\\{sid}"
        check = subprocess.run(["reg", "query", f"HKLM\\{key_path}"], capture_output=True,
                               timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        if check.returncode != 0:
            return False
        subprocess.run(["reg", "add", f"HKLM\\{key_path}", "/v", "Start", "/t", "REG_DWORD", "/d", "2", "/f"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        run_sc(["start", sid])
        return True
    except:
        return False

def enable_service(sid, start_type="auto"):
    if sid in CRITICAL_SERVICES:
        return False
    if sid in PROTECTED_SERVICES:
        return force_enable_protected_service(sid)
    sc_t = "demand" if start_type == "demand" else "auto"
    c, _ = run_sc(["config", sid, "start=", sc_t])
    run_sc(["start", sid])
    return c == 0

def backup_service(sid):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BACKUP_DIR, f"{sid}_{ts}.reg")
    try:
        r = subprocess.run(
            ["reg", "export", f"HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\{sid}", path, "/y"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15
        )
        if r.returncode == 0 and os.path.exists(path):
            return path
    except:
        pass
    return None

def delete_service(sid):
    deleted_data = load_deleted_services()
    first_deleted = deleted_data[sid].get("deleted_date") if sid in deleted_data else datetime.datetime.now().isoformat()
    svc = SERVICES.get(sid)
    unknown_svc = get_unknown_services().get(sid)
    if svc:
        service_info = {"name": svc.get("name", sid), "category": svc.get("category", "Неизвестные"),
                        "desc": svc.get("desc", ""), "risk": svc.get("risk", "unknown"),
                        "tags": svc.get("tags", []), "gaming_recommend": svc.get("gaming_recommend", "")}
    elif unknown_svc:
        service_info = {"name": unknown_svc.get("name", sid), "category": "❓ Неизвестные",
                        "desc": unknown_svc.get("desc", "Неизвестная служба"), "risk": "unknown",
                        "tags": ["unknown"], "gaming_recommend": ""}
    else:
        service_info = {"name": sid, "category": "❓ Неизвестные", "desc": "Неизвестная служба",
                        "risk": "unknown", "tags": ["unknown"], "gaming_recommend": ""}
    deleted_data[sid] = {**service_info, "deleted_date": first_deleted,
                         "last_modified": datetime.datetime.now().isoformat(),
                         "backup_file": None,
                         "deleted_count": deleted_data.get(sid, {}).get("deleted_count", 0) + 1}
    backs = get_backup_files(sid)
    if backs:
        deleted_data[sid]["backup_file"] = backs[0]
    save_deleted_services(deleted_data)
    run_sc(["stop", sid])
    return run_sc(["delete", sid])[0] == 0

def restore_deleted_service(sid):
    deleted_data = load_deleted_services()
    if sid not in deleted_data:
        return False, "Служба не найдена"
    info = deleted_data[sid]
    if info.get("backup_file") and os.path.exists(info["backup_file"]):
        if restore_service_from_reg(info["backup_file"]):
            del deleted_data[sid]
            save_deleted_services(deleted_data)
            return True, "Восстановлено из резервной копии"
    for bin_path in [f"C:\\Windows\\System32\\svchost.exe -k {sid}",
                     f"C:\\Windows\\System32\\{sid}.exe",
                     f"C:\\Program Files\\{sid}\\{sid}.exe"]:
        r = subprocess.run(["sc", "create", sid, "binPath=", bin_path, "start=", "demand"],
                           capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        if r.returncode == 0:
            del deleted_data[sid]
            save_deleted_services(deleted_data)
            return True, "Служба восстановлена"
    return False, "Не удалось восстановить"

def load_deleted_services():
    if not os.path.exists(DELETED_SERVICES_FILE):
        return {}
    try:
        with open(DELETED_SERVICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_deleted_services(data):
    try:
        with open(DELETED_SERVICES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def get_unknown_services():
    if not os.path.exists(UNKNOWN_SERVICES_FILE):
        return {}
    try:
        with open(UNKNOWN_SERVICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_unknown_services(data):
    try:
        with open(UNKNOWN_SERVICES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def restore_service_from_reg(reg_file):
    if not os.path.exists(reg_file):
        return False
    try:
        content = None
        for enc in ("utf-16", "utf-8-sig", "utf-8"):
            try:
                with open(reg_file, "r", encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        if content is None or not content.strip().startswith("Windows Registry Editor Version"):
            return False
        return subprocess.run(["reg", "import", reg_file], capture_output=True, text=True,
                              creationflags=subprocess.CREATE_NO_WINDOW, timeout=15).returncode == 0
    except:
        return False

def get_backup_files(sid):
    if not os.path.isdir(BACKUP_DIR):
        return []
    files = [f for f in os.listdir(BACKUP_DIR) if f.startswith(sid + "_") and f.endswith(".reg")]
    files.sort(reverse=True)
    return [os.path.join(BACKUP_DIR, f) for f in files]

def save_snapshot(data):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        return None
    with open(SNAPSHOT_FILE, encoding="utf-8") as f:
        return json.load(f)

def get_categories():
    cats = set(svc.get("category", "Без категории") for svc in SERVICES.values())
    return ["Все"] + sorted(cats) + ["❓ Неизвестные", "🗑 Удалённые"]

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except:
        return False

def search_service_online(service_name):
    webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(f'За что отвечает служба {service_name} и можно ли её отключить')}")

def get_real_sid(tree_id):
    if tree_id.startswith("unk_"):
        return tree_id[4:]
    if tree_id.startswith("del_"):
        return tree_id[4:]
    return tree_id

class ThreadSafeCache:
    def __init__(self, ttl=60):
        self._cache, self._timestamps, self._ttl = {}, {}, ttl
        self._lock = threading.RLock()

    def get(self, key, default=None):
        with self._lock:
            if key in self._cache and time.time() - self._timestamps.get(key, 0) < self._ttl:
                return self._cache[key]
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            return default

    def set(self, key, value):
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()

    def update(self, items):
        with self._lock:
            for k, v in items.items():
                self._cache[k] = v
                self._timestamps[k] = time.time()

    def pop(self, key, default=None):
        with self._lock:
            self._timestamps.pop(key, None)
            return self._cache.pop(key, default)

    def get_all(self):
        with self._lock:
            return self._cache.copy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WS Manager v2.0")
        self.geometry("1340x900")
        self.minsize(1050, 700)
        self.configure(bg=BG)
        try:
            if getattr(sys, 'frozen', False):
                self.iconbitmap(os.path.join(os.path.dirname(sys.executable), "icon.ico"))
            elif os.path.exists(ICON_PATH):
                self.iconbitmap(ICON_PATH)
        except:
            pass

        if not os.path.exists(FIRST_RUN_FLAG):
            self.state('zoomed')

        self._cache = ThreadSafeCache(ttl=120)
        self._sort_col, self._sort_rev = "name", False
        self._ui_q = queue.Queue()
        self._updating = False
        self._update_lock = threading.Lock()
        self._unknown_services = get_unknown_services()
        self._skip_disable_confirm = False
        self._skip_critical_confirm = False
        self._skip_protected_confirm = False
        self._skip_deps_confirm = False
        self._thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self._sorted_items_cache = None
        self._sort_cache_key = None

        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=BG2, troughcolor=BG3,
                    borderwidth=0, relief="flat", font=("Segoe UI", 10))
        s.configure("Treeview", background=BG2, foreground=FG, fieldbackground=BG2,
                    rowheight=28, font=("Segoe UI", 10), borderwidth=0)
        s.configure("Treeview.Heading", background=HEAD_BG, foreground=HEAD_FG,
                    font=("Segoe UI", 10, "bold"), relief="flat", borderwidth=0, padding=(8, 6))
        s.map("Treeview", background=[("selected", SEL_BG)], foreground=[("selected", SEL_FG)])
        s.configure("TCombobox", fieldbackground=BG2, background=BG2, foreground=FG,
                    arrowcolor=ACCENT, selectbackground=SEL_BG, selectforeground=SEL_FG, borderwidth=1)
        s.map("TCombobox", fieldbackground=[("readonly", BG2)])

        self._build()
        self._poll_queue()
        self.after(50, self._load_statuses)
        self.after(500, self._check_first_run)

    def _show_confirm_dialog(self, title, message):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("520x220")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        main_frame = tk.Frame(dialog, bg=BG, padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        tk.Label(main_frame, text=message, bg=BG, fg=FG, font=("Segoe UI", 10),
                 justify="left", wraplength=460, anchor="w").pack(fill="x", pady=(0, 15))
        bottom_frame = tk.Frame(main_frame, bg=BG)
        bottom_frame.pack(fill="x", side="bottom")
        skip_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bottom_frame, text="Больше не показывать это окно", variable=skip_var,
                       bg=BG, fg=FG2, font=("Segoe UI", 9), selectcolor=BG2,
                       activebackground=BG, activeforeground=FG).pack(side="left", anchor="w")
        btn_frame = tk.Frame(bottom_frame, bg=BG)
        btn_frame.pack(side="right")
        result = [None]

        def on_yes():
            result[0] = 'skip' if skip_var.get() else 'yes'
            dialog.destroy()

        def on_no():
            dialog.destroy()

        tk.Button(btn_frame, text="Да", command=on_yes, bg=ACCENT, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=20, pady=6, bd=0, cursor="hand2").pack(side="right", padx=(5, 0))
        tk.Button(btn_frame, text="Нет", command=on_no, bg=BG3, fg=FG, relief="flat",
                  font=("Segoe UI", 10), padx=20, pady=6, bd=0, cursor="hand2").pack(side="right")
        dialog.wait_window()
        return result[0]

    def _check_first_run(self):
        if not os.path.exists(FIRST_RUN_FLAG):
            if messagebox.askyesno("Первый запуск",
                                   "Это первый запуск программы.\n\nСохранить текущее состояние всех служб как точку восстановления?"):
                self._ui(lambda: self._status_lbl.configure(text="⏳ Создание точки восстановления…"))
                self._thread_pool.submit(self._create_initial_snapshot)
            with open(FIRST_RUN_FLAG, "w") as f:
                f.write("1")

    def _create_initial_snapshot(self):
        all_services = list(SERVICES.keys()) + list(self._unknown_services.keys())
        total, done, snap, lock = len(all_services), [0], {}, threading.Lock()

        def qone(sid):
            r = query_service(sid)
            with lock:
                snap[sid] = r
                done[0] += 1
                d = done[0]
            self._ui(lambda d=d: self._prog.configure(value=min(d / total * 100, 100)))

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            list(ex.map(qone, all_services))
        snap["_meta"] = {"time": datetime.datetime.now().isoformat(), "count": total, "type": "initial"}
        save_snapshot(snap)
        self._cache.update({k: v for k, v in snap.items() if not k.startswith("_")})
        append_log("Создана начальная точка восстановления")
        self._ui(lambda: (
            self._rebuild_tree(),
            self._status_lbl.configure(text="✅ Точка восстановления создана"),
            self._prog.configure(value=100)
        ))

    def _build(self):
        h = tk.Frame(self, bg=ACCENT)
        h.pack(fill="x")
        left = tk.Frame(h, bg=ACCENT)
        left.pack(side="left", fill="y", padx=20, pady=12)
        tk.Label(left, text="⚡ WS Manager v2.0", font=("Segoe UI", 17, "bold"),
                 bg=ACCENT, fg="#FFFFFF").pack(anchor="w")
        tk.Label(left, text=f"Автор: Павел Прилуцкий  •  {len(SERVICES)} служб в базе",
                 font=("Segoe UI", 9), bg=ACCENT, fg="#C7C9FF").pack(anchor="w")
        right = tk.Frame(h, bg=ACCENT)
        right.pack(side="right", padx=20, pady=12)

        def link(parent, text, url):
            l = tk.Label(parent, text=text, font=("Segoe UI", 9, "underline"),
                         bg=ACCENT, fg="#C7D2FF", cursor="hand2")
            l.pack(anchor="e")
            l.bind("<Button-1>", lambda e: webbrowser.open(url))

        link(right, "📰 IXBT: Pavel_Priluckiy", "https://www.ixbt.com/live/Pavel_Priluckiy/")
        link(right, "💬 VK: vk.com/kerfaers", "https://vk.com/kerfaers")
        if not is_admin():
            tk.Label(h, text="  ⚠ Запустите от имени Администратора!",
                     font=("Segoe UI", 11, "bold"), bg="#DC2626", fg="#FFF",
                     padx=14, pady=14).pack(side="right", fill="y")

        tb = tk.Frame(self, bg=BG, pady=8, padx=16)
        tb.pack(fill="x")
        tk.Label(tb, text="Категория", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(side="left")
        self._cat_var = tk.StringVar(value="Все")
        ttk.Combobox(tb, textvariable=self._cat_var, values=get_categories(),
                     state="readonly", width=20, font=("Segoe UI", 10)).pack(side="left", padx=(4, 14))
        self._cat_var.trace_add("write", lambda *_: self._invalidate_sort_cache())
        tk.Label(tb, text="Риск", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(side="left")
        self._risk_var = tk.StringVar(value="Все")
        ttk.Combobox(tb, textvariable=self._risk_var,
                     values=["Все", "✅ Безопасно", "⚠ Осторожно", "🔴 Опасно", "❓ Неизвестно"],
                     state="readonly", width=16, font=("Segoe UI", 10)).pack(side="left", padx=(4, 14))
        self._risk_var.trace_add("write", lambda *_: self._invalidate_sort_cache())
        tk.Label(tb, text="Статус", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(side="left")
        self._sf_var = tk.StringVar(value="Все")
        ttk.Combobox(tb, textvariable=self._sf_var,
                     values=["Все", "▶ Работает", "■ Остановлена", "? Неизвестно"],
                     state="readonly", width=14, font=("Segoe UI", 10)).pack(side="left", padx=(4, 14))
        self._sf_var.trace_add("write", lambda *_: self._invalidate_sort_cache())
        tk.Label(tb, text="🔍", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(side="left")
        self._sq_var = tk.StringVar()
        self._sq_var.trace_add("write", lambda *_: self._invalidate_sort_cache())
        tk.Entry(tb, textvariable=self._sq_var, bg=BG2, fg=FG, insertbackground=ACCENT,
                 font=("Segoe UI", 10), relief="solid", bd=1, highlightthickness=0,
                 width=28).pack(side="left", padx=(4, 14))
        tk.Label(tb, text="Пресет:", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(side="left")
        self._preset_var = tk.StringVar(value="— выбрать —")
        pcb = ttk.Combobox(tb, textvariable=self._preset_var, values=list(PRESETS.keys()),
                            state="readonly", width=28, font=("Segoe UI", 10))
        pcb.pack(side="left", padx=(4, 6))
        pcb.bind("<<ComboboxSelected>>", self._apply_preset)
        self._ref_btn = tk.Button(tb, text="🔄 Обновить", command=self._load_statuses,
                                  bg=BG3, fg=ACCENT, relief="flat", font=("Segoe UI", 9),
                                  cursor="hand2", padx=10, pady=4, bd=0)
        self._ref_btn.pack(side="right", padx=4)

        main_paned = tk.PanedWindow(self, orient="vertical", bg=BORDER, sashwidth=4)
        main_paned.pack(fill="both", expand=True, padx=14, pady=(4, 0))

        tree_frame = tk.Frame(main_paned, bg=BORDER, bd=1, relief="flat")
        self._tree = ttk.Treeview(tree_frame,
                                   columns=("name", "category", "risk", "status", "start"),
                                   show="headings", selectmode="extended")
        self._tree.heading("name", text="Служба", command=lambda: self._sort_by("name"))
        self._tree.column("name", width=370, anchor="w", stretch=True)
        self._tree.heading("category", text="Категория", command=lambda: self._sort_by("category"))
        self._tree.column("category", width=145, anchor="center")
        self._tree.heading("risk", text="Риск", command=lambda: self._sort_by("risk"))
        self._tree.column("risk", width=120, anchor="center")
        self._tree.heading("status", text="Статус", command=lambda: self._sort_by("status"))
        self._tree.column("status", width=120, anchor="center")
        self._tree.heading("start", text="Тип запуска", command=lambda: self._sort_by("start"))
        self._tree.column("start", width=130, anchor="center")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        # БАГ: в оригинале был двойной bind — второй перезаписывал первый.
        # Теперь единый обработчик _on_tree_select делает и on_select и upd_sel.
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-1>", self._on_dbl)
        self._tree.bind("<Button-3>", self._show_context_menu)
        main_paned.add(tree_frame, height=500)

        det_frame = tk.Frame(main_paned, bg=CARD, bd=0, relief="flat",
                             highlightbackground=BORDER, highlightthickness=1)
        self._detail = scrolledtext.ScrolledText(det_frame, wrap="word", bg=CARD, fg=FG2,
                                                  font=("Segoe UI", 10), relief="flat",
                                                  state="disabled", padx=10, pady=8)
        self._detail.pack(fill="both", expand=True)
        main_paned.add(det_frame, height=250)

        act = tk.Frame(self, bg=BG, pady=7, padx=14)
        act.pack(fill="x")
        self._btn_dis = tk.Button(act, text="🔴 Отключить выбранные", command=self._disable_selected,
                                   bg="#FEF2F2", fg=DANGER, relief="flat", font=("Segoe UI", 10, "bold"),
                                   cursor="hand2", padx=12, pady=6, bd=0)
        self._btn_dis.pack(side="left", padx=(0, 6))
        self._btn_en = tk.Button(act, text="🟢 Включить выбранные", command=self._enable_selected,
                                  bg="#F0FDF4", fg=OK, relief="flat", font=("Segoe UI", 10, "bold"),
                                  cursor="hand2", padx=12, pady=6, bd=0)
        self._btn_en.pack(side="left", padx=(0, 6))
        self._snap_btn = tk.Button(act, text="📸 Сохранить состояние", command=self._take_snapshot,
                                    bg=BG3, fg=ACCENT, relief="flat", font=("Segoe UI", 10, "bold"),
                                    cursor="hand2", padx=12, pady=6, bd=0)
        self._snap_btn.pack(side="left", padx=(0, 6))
        self._restore_btn = tk.Button(act, text="♻ Восстановить состояние", command=self._restore_snapshot,
                                       bg=BG3, fg=ACCENT2, relief="flat", font=("Segoe UI", 10, "bold"),
                                       cursor="hand2", padx=12, pady=6, bd=0)
        self._restore_btn.pack(side="left", padx=(0, 6))
        self._del_btn = tk.Button(act, text="🗑 Удалённые службы", command=self._show_deleted_services,
                                   bg=BG3, fg=DANGER, relief="flat", font=("Segoe UI", 10, "bold"),
                                   cursor="hand2", padx=12, pady=6, bd=0)
        self._del_btn.pack(side="left", padx=(0, 6))
        tk.Button(act, text="📋 Лог", command=self._open_log, bg=BG3, fg=FG2, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2", padx=10, pady=4, bd=0).pack(side="left", padx=(0, 6))
        self._sel_lbl = tk.Label(act, text="", bg=BG, fg=FG2, font=("Segoe UI", 9))
        self._sel_lbl.pack(side="right")

        sb = tk.Frame(self, bg=BG3)
        sb.pack(fill="x", side="bottom")
        self._prog = ttk.Progressbar(sb, orient="horizontal", mode="determinate")
        self._prog.pack(fill="x")
        inner = tk.Frame(sb, bg=BG3)
        inner.pack(fill="x", padx=12, pady=3)
        self._status_lbl = tk.Label(inner, text="Готов к работе", bg=BG3, fg=FG2,
                                     font=("Segoe UI", 9), anchor="w")
        self._status_lbl.pack(side="left", fill="x", expand=True)
        self._count_lbl = tk.Label(inner, text="", bg=BG3, fg=FG2, font=("Segoe UI", 9))
        self._count_lbl.pack(side="right")

    def _on_tree_select(self, event=None):
        """Единый обработчик выбора в дереве."""
        self._on_select(event)
        self._upd_sel()

    def _invalidate_sort_cache(self):
        self._sorted_items_cache = None
        self._sort_cache_key = None
        self._rebuild_tree()

    def _search_online(self, sid):
        real_sid = get_real_sid(sid)
        svc = SERVICES.get(real_sid, {})
        unk = self._unknown_services.get(real_sid, {})
        search_service_online(svc.get("name", unk.get("name", real_sid)))

    def _show_context_menu(self, event):
        row = self._tree.identify_row(event.y)
        if not row:
            return
        if row not in self._tree.selection():
            self._tree.selection_set(row)
        sid = row
        if sid.startswith("del_"):
            real_sid = sid[4:]
            menu = tk.Menu(self, tearoff=0, bg=BG2, fg=FG, activebackground=SEL_BG,
                           activeforeground=SEL_FG, relief="flat", font=("Segoe UI", 10), bd=1)
            menu.add_command(label="♻ Восстановить службу", command=lambda: self._restore_deleted(real_sid))
            menu.add_separator()
            menu.add_command(label="🗑 Удалить из списка", command=lambda: self._remove_from_deleted(real_sid))
            menu.add_separator()
            menu.add_command(label="🔍 Искать в интернете", command=lambda: self._search_online(real_sid))
            menu.tk_popup(event.x_root, event.y_root)
            return
        real_sid = get_real_sid(sid)
        menu = tk.Menu(self, tearoff=0, bg=BG2, fg=FG, activebackground=SEL_BG,
                       activeforeground=SEL_FG, relief="flat", font=("Segoe UI", 10), bd=1)
        st = self._cache.get(real_sid, {}).get("status", "unknown")
        menu.add_command(label="▶  Запустить службу", command=lambda: self._ctx_start(real_sid),
                         state="normal" if st != "running" else "disabled")
        menu.add_command(label="■  Остановить службу", command=lambda: self._ctx_stop(real_sid),
                         state="normal" if st == "running" else "disabled")
        menu.add_separator()
        menu.add_command(label="🔴 Отключить (запретить)", command=lambda: self._ctx_disable(real_sid))
        menu.add_command(label="🟢 Включить (авто)", command=lambda: self._ctx_enable(real_sid))
        menu.add_separator()
        menu.add_command(label="💾 Создать резервную копию", command=lambda: self._ctx_backup(real_sid))
        menu.add_command(label="🗑  Удалить службу (с бэкапом)", command=lambda: self._ctx_delete(real_sid))
        menu.add_command(label="♻  Восстановить из бэкапа…", command=lambda: self._ctx_restore_backup(real_sid))
        menu.add_separator()
        menu.add_command(label="🔍 Искать в интернете", command=lambda: self._search_online(real_sid))
        menu.add_separator()
        menu.add_command(label="📤 Экспортировать неизвестные службы", command=self._export_unknown_services)
        menu.tk_popup(event.x_root, event.y_root)

    def _export_unknown_services(self):
        if not self._unknown_services:
            messagebox.showinfo("Нет неизвестных служб", "Все службы в системе известны.")
            return
        if not messagebox.askyesno("Экспорт неизвестных служб",
                                    f"Найдено {len(self._unknown_services)} неизвестных служб.\n\n"
                                    f"💡 Чтобы помочь улучшить программу, отправляйте неизвестные службы на страницу программы на GitHub.\n"
                                    f"Автор их отсортирует и обязательно добавит в программу.\n\n"
                                    f"🔗 {GITHUB_URL}\n\nПродолжить экспорт?"):
            return
        filepath = filedialog.asksaveasfilename(title="Сохранить неизвестные службы",
                                                 defaultextension=".txt",
                                                 filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")])
        if not filepath:
            return
        with open(filepath, "w", encoding="utf-8") as f:
            for sid, info in self._unknown_services.items():
                f.write(f"[{sid}]\nname={info.get('name', sid)}\ncategory={info.get('category', '❓ Неизвестные')}\n"
                        f"desc={info.get('desc', '')}\nrisk={info.get('risk', 'unknown')}\n"
                        f"tags={','.join(info.get('tags', []))}\ngaming_recommend={info.get('gaming_recommend', '')}\n\n")
        messagebox.showinfo("Экспорт завершён",
                            f"Экспортировано {len(self._unknown_services)} служб в:\n{filepath}\n\n"
                            f"📤 Отправьте этот файл на GitHub:\n{GITHUB_URL}")

    def _show_deleted_services(self):
        deleted = load_deleted_services()
        if not deleted:
            messagebox.showinfo("Удалённые службы", "Нет удалённых служб в списке.")
            return
        win = tk.Toplevel(self)
        win.title("🗑 Удалённые службы")
        win.geometry("700x450")
        win.configure(bg=BG)
        tk.Label(win, text="Список удалённых служб:", bg=BG, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(pady=10, padx=14, anchor="w")
        tk.Label(win, text="Выберите службу для восстановления", bg=BG, fg=FG2,
                 font=("Segoe UI", 9)).pack(padx=14, anchor="w")
        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=14, pady=5)
        listbox = tk.Listbox(frame, bg=BG2, fg=FG, font=("Consolas", 10),
                             selectbackground=SEL_BG, selectforeground=SEL_FG, relief="flat", bd=1)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for sid, info in deleted.items():
            listbox.insert("end",
                           f"{sid} - {info.get('name', sid)} (удалена: {info.get('deleted_date', 'неизвестно')[:16]})")

        def restore_selected():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("Выбор", "Выберите службу для восстановления.")
                return
            sid = list(deleted.keys())[selection[0]]
            if messagebox.askyesno("Восстановление", f"Восстановить службу {sid}?"):
                success, msg = restore_deleted_service(sid)
                if success:
                    messagebox.showinfo("Успех", msg)
                    win.destroy()
                    self._load_statuses()
                else:
                    messagebox.showerror("Ошибка", msg)

        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(fill="x", pady=10, padx=14)
        tk.Button(btn_frame, text="♻ Восстановить выбранную", command=restore_selected,
                  bg=ACCENT, fg="white", relief="flat", font=("Segoe UI", 10, "bold"),
                  padx=12, pady=6, bd=0).pack(side="left", padx=4)
        tk.Button(btn_frame, text="❌ Закрыть", command=win.destroy, bg=BG3, fg=FG2,
                  relief="flat", font=("Segoe UI", 10), padx=12, pady=6, bd=0).pack(side="left", padx=4)

    def _remove_from_deleted(self, sid):
        deleted = load_deleted_services()
        if sid in deleted and messagebox.askyesno("Удалить из списка",
                                                   f"Удалить службу {sid} из списка удалённых?\n"
                                                   f"(Это не восстановит службу, только удалит запись о ней)"):
            del deleted[sid]
            save_deleted_services(deleted)
            self._rebuild_tree()

    def _poll_queue(self):
        try:
            while True:
                self._ui_q.get_nowait()()
        except queue.Empty:
            pass
        self.after(35, self._poll_queue)

    def _ui(self, fn):
        self._ui_q.put(fn)

    def _rebuild_tree(self, *_):
        with self._update_lock:
            if self._updating:
                return
            self._updating = True
        try:
            cache_data = self._cache.get_all()
            deleted_data = load_deleted_services()
            cache_key = (
                self._cat_var.get(), self._risk_var.get(), self._sf_var.get(),
                self._sq_var.get().lower().strip(), self._sort_col, self._sort_rev,
                # включаем кол-во unknown services в ключ кеша — сбрасывается при их изменении
                len(self._unknown_services)
            )
            if self._sort_cache_key == cache_key and self._sorted_items_cache is not None:
                items = self._sorted_items_cache
            else:
                items = self._compute_sorted_items(cache_data, deleted_data)
                self._sorted_items_cache = items
                self._sort_cache_key = cache_key

            current_ids = set(self._tree.get_children())
            new_ids = set()
            running = stopped = unknown = 0
            deleted_count = len(deleted_data)
            unknown_count = 0

            for sid in items:
                if sid in deleted_data:
                    tree_id = f"del_{sid}"
                    info = deleted_data[sid]
                    values = (info.get("name", sid), "🗑 Удалённые",
                              RISK_LABEL.get(info.get("risk", "low"), "✅ Безопасно"),
                              "🗑 Удалена", "🗑 Удалена")
                    tags = ("deleted",)
                elif sid in SERVICES:
                    tree_id = sid
                    svc = SERVICES[sid]
                    info = cache_data.get(sid, {})
                    st = info.get("status", "")
                    sta = info.get("start_type", "")
                    rl = RISK_LABEL.get(svc.get("risk", ""), "❓ Неизвестно")
                    values = (svc.get("name", sid), svc.get("category", "❓ Неизвестные"), rl,
                              STATUS_MAP.get(st, "? Неизвестно"), START_TYPE_MAP.get(sta, "❓ Неизвестно"))
                    tags = (svc.get("risk", "unknown"),)
                    if st == "running":
                        running += 1
                    elif st == "stopped":
                        stopped += 1
                    else:
                        unknown += 1
                else:
                    tree_id = f"unk_{sid}"
                    info = cache_data.get(sid, {})
                    st = info.get("status", "")
                    sta = info.get("start_type", "")
                    unk = self._unknown_services.get(sid, {})
                    values = (unk.get("name", sid), unk.get("category", "❓ Неизвестные"),
                              "❓ Неизвестно", STATUS_MAP.get(st, "? Неизвестно"),
                              START_TYPE_MAP.get(sta, "❓ Неизвестно"))
                    tags = ("unknown",)
                    unknown_count += 1
                    if st == "running":
                        running += 1
                    elif st == "stopped":
                        stopped += 1
                    else:
                        unknown += 1

                new_ids.add(tree_id)
                if tree_id in current_ids:
                    try:
                        self._tree.item(tree_id, values=values, tags=tags)
                    except:
                        pass
                else:
                    self._tree.insert("", "end", iid=tree_id, values=values, tags=tags)

            for old_id in current_ids - new_ids:
                try:
                    self._tree.delete(old_id)
                except:
                    pass

            self._tree.tag_configure("low", foreground="#166534")
            self._tree.tag_configure("medium", foreground="#92400E")
            self._tree.tag_configure("high", foreground="#991B1B")
            self._tree.tag_configure("unknown", foreground="#8B5CF6")
            self._tree.tag_configure("deleted", foreground="#DC2626")
            self._count_lbl.configure(
                text=f"Служб: {len(items)}   ▶ {running}   ■ {stopped}   ? {unknown}   ❓ {unknown_count}   🗑 {deleted_count}"
            )
        finally:
            with self._update_lock:
                self._updating = False

    def _compute_sorted_items(self, cache_data, deleted_data):
        cat = self._cat_var.get()
        rm = {"✅ Безопасно": "low", "⚠ Осторожно": "medium", "🔴 Опасно": "high",
              "❓ Неизвестно": "unknown", "Все": None}
        risk = rm.get(self._risk_var.get())
        sf_map = {"▶ Работает": "running", "■ Остановлена": "stopped", "? Неизвестно": "unknown", "Все": None}
        sf = sf_map.get(self._sf_var.get())
        q = self._sq_var.get().lower().strip()
        items = []

        if cat == "🗑 Удалённые":
            items = list(deleted_data.keys())
        elif cat == "❓ Неизвестные":
            items = [sid for sid in self._unknown_services if sid not in SERVICES]
        else:
            for sid, svc in SERVICES.items():
                if cat != "Все" and svc.get("category") != cat:
                    continue
                if risk and svc.get("risk") != risk:
                    continue
                st = cache_data.get(sid, {}).get("status", "")
                if sf and st != sf:
                    continue
                if q and q not in f"{svc.get('name', '')} {sid} {svc.get('desc', '')} {svc.get('category', '')} {' '.join(svc.get('tags', []))}".lower():
                    continue
                items.append(sid)
            if cat == "Все":
                for sid in self._unknown_services:
                    if sid not in SERVICES:
                        if risk and risk != "unknown":
                            continue
                        st = cache_data.get(sid, {}).get("status", "")
                        if sf and st != sf:
                            continue
                        if q and q not in sid.lower():
                            continue
                        items.append(sid)

        def sort_key(s):
            if s in deleted_data:
                if self._sort_col == "name":
                    return deleted_data[s].get("name", s).lower()
                elif self._sort_col == "category":
                    return "🗑 Удалённые"
                elif self._sort_col == "risk":
                    return "deleted"
                elif self._sort_col in ("status", "start"):
                    return "🗑 Удалена"
                return s
            elif s in SERVICES:
                svc = SERVICES[s]
                info = cache_data.get(s, {})
                if self._sort_col == "name":
                    return svc.get("name", s).lower()
                elif self._sort_col == "category":
                    return svc.get("category", "").lower()
                elif self._sort_col == "risk":
                    return {"low": 0, "medium": 1, "high": 2}.get(svc.get("risk"), 9)
                elif self._sort_col == "status":
                    return info.get("status", "")
                elif self._sort_col == "start":
                    return info.get("start_type", "")
                return s
            else:
                info = cache_data.get(s, {})
                unk = self._unknown_services.get(s, {})
                if self._sort_col == "name":
                    return unk.get("name", s).lower()
                elif self._sort_col == "category":
                    return unk.get("category", "❓ Неизвестные").lower()
                elif self._sort_col == "risk":
                    return 3
                elif self._sort_col == "status":
                    return info.get("status", "")
                elif self._sort_col == "start":
                    return info.get("start_type", "")
                return s

        items.sort(key=sort_key, reverse=self._sort_rev)
        return items

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col, self._sort_rev = col, False
        self._sorted_items_cache = None
        self._sort_cache_key = None
        self._rebuild_tree()

    def _upd_sel(self):
        n = len(self._tree.selection())
        self._sel_lbl.configure(text=f"  Выбрано: {n}" if n else "")

    def _on_select(self, _=None):
        sel = self._tree.selection()
        if not sel:
            return
        sid = sel[-1]
        real_sid = get_real_sid(sid)
        if sid.startswith("del_"):
            info = load_deleted_services().get(real_sid, {})
            text = (f"[{real_sid}]  {info.get('name', 'Неизвестно')}\n"
                    f"Категория: 🗑 Удалённые\n"
                    f"Риск: {RISK_LABEL.get(info.get('risk', 'low'), '✅ Безопасно')}\n"
                    f"Статус: 🗑 Удалена\nТип запуска: 🗑 Удалена\n"
                    f"Дата удаления: {info.get('deleted_date', 'неизвестно')[:19]}\n\n"
                    f"{info.get('desc', 'Описание отсутствует')}")
            if info.get('gaming_recommend'):
                text += f"\n\n🎮 Для игрового ПК: {info['gaming_recommend']}"
        elif sid.startswith("unk_"):
            info = self._cache.get(real_sid, {})
            unk = self._unknown_services.get(real_sid, {})
            backs = get_backup_files(real_sid)
            backs_str = f"Резервных копий: {len(backs)}" if backs else "Резервных копий: нет"
            text = (f"[{real_sid}]  {unk.get('name', real_sid)}\n"
                    f"Категория: {unk.get('category', '❓ Неизвестные')}   "
                    f"Риск: ❓ Неизвестно   "
                    f"Статус: {STATUS_MAP.get(info.get('status', ''), '? Неизвестно')}   "
                    f"Тип запуска: {START_TYPE_MAP.get(info.get('start_type', ''), '❓ Неизвестно')}   "
                    f"{backs_str}\n\n"
                    f"{unk.get('desc', 'Неизвестная служба. Используйте поиск в интернете для получения информации.')}")
        else:
            svc = SERVICES.get(real_sid)
            info = self._cache.get(real_sid, {})
            backs = get_backup_files(real_sid)
            backs_str = f"Резервных копий: {len(backs)}" if backs else "Резервных копий: нет"
            if svc:
                text = (f"[{real_sid}]  {svc.get('name', real_sid)}\n"
                        f"Категория: {svc.get('category', '')}   "
                        f"Риск: {RISK_LABEL.get(svc.get('risk', ''), '')}   "
                        f"Статус: {STATUS_MAP.get(info.get('status', ''), '? Неизвестно')}   "
                        f"Тип запуска: {START_TYPE_MAP.get(info.get('start_type', ''), '❓ Неизвестно')}   "
                        f"{backs_str}\n"
                        f"Назначение: {', '.join(svc.get('tags', [])) or '—'}\n\n"
                        f"{svc.get('desc', '')}")
                if svc.get('gaming_recommend'):
                    text += f"\n\n🎮 Для игрового ПК: {svc['gaming_recommend']}"
            else:
                text = f"[{real_sid}]  Служба не найдена в базе.\n{backs_str}"
        self._detail.configure(state="normal")
        self._detail.delete("1.0", "end")
        self._detail.insert("end", text)
        self._detail.configure(state="disabled")

    def _on_dbl(self, event):
        """
        Двойной клик: запускает/останавливает службу (не disable/enable),
        чтобы не показывать диалоги подтверждения при случайном двойном клике.
        """
        sid = self._tree.focus()
        if not sid or sid.startswith("del_"):
            return
        real_sid = get_real_sid(sid)
        st = self._cache.get(real_sid, {}).get("status", "unknown")
        if st == "running":
            self._ctx_stop(real_sid)
        else:
            self._ctx_start(real_sid)

    def _restore_deleted(self, sid):
        if messagebox.askyesno("Восстановление", f"Восстановить службу {sid}?"):
            success, msg = restore_deleted_service(sid)
            if success:
                messagebox.showinfo("Успех", msg)
                self._load_statuses()
            else:
                messagebox.showerror("Ошибка", msg)

    def _ctx_start(self, sid):
        self._thread_pool.submit(self._ctx_start_worker, sid)

    def _ctx_start_worker(self, sid):
        ok = start_service(sid)
        self._cache.set(sid, query_service(sid))
        append_log(f"ЗАПУСК {'ОК' if ok else 'ОШИБКА'}  {sid}")
        self._ui(lambda: (
            self._rebuild_tree(),
            self._status_lbl.configure(text=f"{'✅ Запущена' if ok else '❌ Ошибка запуска'}: {sid}")
        ))

    def _ctx_stop(self, sid):
        self._thread_pool.submit(self._ctx_stop_worker, sid)

    def _ctx_stop_worker(self, sid):
        ok = stop_service(sid)
        self._cache.set(sid, query_service(sid))
        append_log(f"ОСТАНОВКА {'ОК' if ok else 'ОШИБКА'}  {sid}")
        self._ui(lambda: (
            self._rebuild_tree(),
            self._status_lbl.configure(text=f"{'■ Остановлена' if ok else '❌ Ошибка остановки'}: {sid}")
        ))

    def _ctx_disable(self, sid, parent_sid=None):
        svc = SERVICES.get(sid, {})
        unk = self._unknown_services.get(sid, {})
        svc_name = svc.get("name", unk.get("name", sid))

        if sid in CRITICAL_SERVICES and not self._skip_critical_confirm:
            result = self._show_confirm_dialog(
                "Критическая служба",
                f"⚠ Внимание! Служба «{svc_name}» является критической для системы.\n\n"
                f"Её отключение может сделать систему нестабильной или неработоспособной!\n\n"
                f"Всё равно отключить?"
            )
            if result is None:
                return
            if result == 'skip':
                self._skip_critical_confirm = True

        if sid in PROTECTED_SERVICES and not self._skip_protected_confirm:
            warn_msg = "⚠ Внимание! Это защищённая служба.\n\n"
            if sid == "mpssvc":
                warn_msg += ("Отключение брандмауэра сделает систему уязвимой для сетевых атак.\n"
                             "Убедитесь что у вас установлен сторонний фаервол.")
            elif sid in ["WinDefend", "WdFilter", "WdNisDrv", "WdNisSvc", "SecurityHealthService"]:
                warn_msg += ("Отключение антивируса Defender сделает систему беззащитной перед вирусами.\n"
                             "Убедитесь что у вас установлен сторонний антивирус.")
            result = self._show_confirm_dialog("Защищённая служба",
                                               f"{warn_msg}\n\nВсё равно отключить «{svc_name}»?")
            if result is None:
                return
            if result == 'skip':
                self._skip_protected_confirm = True

        deps = get_service_dependencies_list(sid)
        if deps and not parent_sid and not self._skip_deps_confirm:
            dep_names = []
            for dep in deps:
                dsvc = SERVICES.get(dep, self._unknown_services.get(dep, {}))
                dep_names.append(f"{dep} ({dsvc.get('name', dep)})" if dsvc else dep)
            result = self._show_confirm_dialog(
                "Зависимые службы",
                f"Для отключения «{svc_name}» необходимо сначала отключить:\n\n"
                + "\n".join(f"  • {d}" for d in dep_names)
                + "\n\nОтключить зависимые службы и продолжить?"
            )
            if result is None:
                return
            if result == 'skip':
                self._skip_deps_confirm = True
            for dep in deps:
                self._ctx_disable(dep, sid)
            # После отключения зависимостей отключаем и саму службу
            self._thread_pool.submit(self._ctx_disable_worker, sid)
            return

        if not self._skip_disable_confirm:
            result = self._show_confirm_dialog("Отключить службу",
                                               f"Отключить службу «{svc_name}» ({sid})?")
            if result is None:
                return
            if result == 'skip':
                self._skip_disable_confirm = True

        self._thread_pool.submit(self._ctx_disable_worker, sid)

    def _ctx_disable_worker(self, sid):
        ok = disable_service(sid)
        self._cache.set(sid, query_service(sid))
        append_log(f"ОТКЛЮЧЕНИЕ {'ОК' if ok else 'ОШИБКА'}  {sid}")
        if not ok:
            deps = get_service_dependencies_list(sid)
            if deps:
                dep_names = []
                for dep in deps:
                    dsvc = SERVICES.get(dep, self._unknown_services.get(dep, {}))
                    dep_names.append(f"{dep} ({dsvc.get('name', dep)})" if dsvc else dep)
                append_log(f"ОШИБКА отключения {sid}. Зависимости: {', '.join(dep_names)}")
            else:
                append_log(f"ОШИБКА отключения {sid}.")
        self._ui(lambda: (
            self._rebuild_tree(),
            self._status_lbl.configure(text=f"{'🔴 Отключена' if ok else '❌ Ошибка'}: {sid}")
        ))

    def _ctx_enable(self, sid):
        self._thread_pool.submit(self._ctx_enable_worker, sid)

    def _ctx_enable_worker(self, sid):
        ok = enable_service(sid)
        self._cache.set(sid, query_service(sid))
        append_log(f"ВКЛЮЧЕНИЕ {'ОК' if ok else 'ОШИБКА'}  {sid}")
        self._ui(lambda: (
            self._rebuild_tree(),
            self._status_lbl.configure(text=f"{'🟢 Включена' if ok else '❌ Ошибка'}: {sid}")
        ))

    def _ctx_backup(self, sid):
        self._thread_pool.submit(self._ctx_backup_worker, sid)

    def _ctx_backup_worker(self, sid):
        path = backup_service(sid)
        if path:
            append_log(f"БЭКАП ОК  {sid}  -> {path}")
            self._ui(lambda: (
                self._status_lbl.configure(text=f"💾 Резервная копия сохранена: {path}"),
                messagebox.showinfo("Резервная копия создана", f"Сохранено:\n{path}")
            ))
        else:
            append_log(f"БЭКАП ОШИБКА  {sid}")
            self._ui(lambda: self._status_lbl.configure(text=f"❌ Ошибка создания резервной копии: {sid}"))

    def _ctx_delete(self, sid):
        svc = SERVICES.get(sid, {})
        unk = self._unknown_services.get(sid, {})
        name = svc.get("name", unk.get("name", sid))
        risk = svc.get("risk", "unknown") if svc else "unknown"
        if risk == "high" and not messagebox.askyesno(
                "Удалить критическую службу",
                f"Удалить службу:\n{name} ({sid})?\n\n"
                f"⚠⚠⚠ ОПАСНО! Это критически важная служба. Удаление может сделать систему неработоспособной!"):
            return
        elif sid in CRITICAL_SERVICES and not messagebox.askyesno(
                "Удалить системную службу",
                f"Удалить службу:\n{name} ({sid})?\n\n⚠ Осторожно! Это системная служба."):
            return
        elif not messagebox.askyesno(
                "Удалить службу",
                f"Удалить службу:\n{name} ({sid})?\n\n"
                f"Перед удалением будет создана резервная копия в папку backups/."):
            return
        self._thread_pool.submit(self._ctx_delete_worker, sid)

    def _ctx_delete_worker(self, sid):
        self._ui(lambda: self._status_lbl.configure(text=f"💾 Создание резервной копии {sid}…"))
        path = backup_service(sid)
        if path:
            append_log(f"БЭКАП_ПЕРЕД_УДАЛЕНИЕМ ОК  {sid}  -> {path}")
        ok = delete_service(sid)
        if ok:
            self._cache.pop(sid, None)
            append_log(f"УДАЛЕНИЕ ОК  {sid}")
        else:
            append_log(f"УДАЛЕНИЕ ОШИБКА  {sid}")
        self._ui(lambda: (
            self._rebuild_tree(),
            self._status_lbl.configure(text=f"{'🗑 Служба удалена' if ok else '❌ Ошибка удаления'}: {sid}")
        ))

    def _ctx_restore_backup(self, sid):
        files = get_backup_files(sid)
        if not files:
            path = filedialog.askopenfilename(
                title=f"Выберите .reg файл для восстановления {sid}",
                initialdir=BACKUP_DIR,
                filetypes=[("Файлы реестра", "*.reg"), ("Все файлы", "*.*")]
            )
            if not path:
                return
            files = [path]
        if len(files) > 1:
            dlg = tk.Toplevel(self)
            dlg.title("Выбор резервной копии")
            dlg.geometry("600x300")
            dlg.configure(bg=BG)
            dlg.grab_set()
            tk.Label(dlg, text=f"Выберите резервную копию для {sid}:", bg=BG, fg=FG,
                     font=("Segoe UI", 11)).pack(pady=10, padx=14, anchor="w")
            lb = tk.Listbox(dlg, bg=BG2, fg=FG, font=("Consolas", 9),
                            selectbackground=SEL_BG, selectforeground=SEL_FG, relief="flat", bd=0)
            lb.pack(fill="both", expand=True, padx=14)
            for f in files:
                lb.insert("end", os.path.basename(f))
            lb.selection_set(0)
            chosen = [files[0]]

            def do_ok():
                idx = lb.curselection()
                if idx:
                    chosen[0] = files[idx[0]]
                dlg.destroy()

            tk.Button(dlg, text="♻ Восстановить", command=do_ok, bg=BG3, fg=ACCENT, relief="flat",
                      font=("Segoe UI", 10, "bold"), cursor="hand2", padx=12, pady=6, bd=0).pack(pady=8)
            self.wait_window(dlg)
            reg_file = chosen[0]
        else:
            reg_file = files[0]
        self._thread_pool.submit(self._ctx_restore_backup_worker, sid, reg_file)

    def _ctx_restore_backup_worker(self, sid, reg_file):
        ok = restore_service_from_reg(reg_file)
        if ok:
            run_sc(["start", sid])
            self._cache.set(sid, query_service(sid))
            append_log(f"ВОССТАНОВЛЕНИЕ ОК  {sid}  из {reg_file}")
        else:
            append_log(f"ВОССТАНОВЛЕНИЕ ОШИБКА  {sid}")
        self._ui(lambda: (
            self._rebuild_tree(),
            self._status_lbl.configure(
                text=f"{'♻ Восстановлено' if ok else '❌ Ошибка восстановления'}: {sid}")
        ))

    def _load_statuses(self):
        self._status_lbl.configure(text="⏳ Загрузка статусов служб…")
        self._ref_btn.configure(state="disabled")
        self._prog["value"] = 0
        all_services = list(SERVICES.keys())
        self._thread_pool.submit(self._load_unknown_services_later)
        total = len(all_services)
        done = [0]
        lock = threading.Lock()
        new_cache = {}

        def worker():
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                futures = {ex.submit(query_service, sid): sid for sid in all_services}
                for fut in as_completed(futures):
                    sid = futures[fut]
                    try:
                        new_cache[sid] = fut.result()
                    except:
                        new_cache[sid] = {"status": "unknown", "start_type": "unknown"}
                    with lock:
                        done[0] += 1
                        if done[0] % 20 == 0:
                            d = done[0]
                            self._ui(lambda d=d: self._prog.configure(value=min(d / total * 100, 100)))
            self._cache.update(new_cache)
            self._ui(self._on_loaded)

        self._thread_pool.submit(worker)

    def _load_unknown_services_later(self):
        time.sleep(2)
        all_system_services = get_all_services_names()
        new_unknown = {}
        for service_name in all_system_services:
            if service_name not in SERVICES:
                base_match = re.match(r'^(.+?)_[a-fA-F0-9]{4,6}$', service_name)
                if base_match and base_match.group(1) in SERVICES:
                    base_svc = SERVICES[base_match.group(1)]
                    new_unknown[service_name] = {
                        "name": f"{base_svc.get('name', base_match.group(1))} (польз.)",
                        "category": base_svc.get("category", "❓ Неизвестные"),
                        "desc": f"Пользовательский экземпляр службы {base_svc.get('name', base_match.group(1))}.",
                        "risk": base_svc.get("risk", "unknown"),
                        "tags": base_svc.get("tags", []) + ["user_instance"],
                        "gaming_recommend": base_svc.get("gaming_recommend", "")
                    }
                    continue
                new_unknown[service_name] = self._unknown_services.get(
                    service_name,
                    {"name": service_name, "category": "❓ Неизвестные",
                     "desc": "Неизвестная служба", "risk": "unknown",
                     "tags": ["unknown"], "gaming_recommend": ""}
                )
        if new_unknown != self._unknown_services:
            self._unknown_services = new_unknown
            save_unknown_services(new_unknown)
            # Сбрасываем кеш сортировки при изменении unknown services
            self._sorted_items_cache = None
            self._sort_cache_key = None
            new_services = [s for s in new_unknown if s not in self._cache.get_all()]
            if new_services:
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                    futures = {ex.submit(query_service, sid): sid for sid in new_services}
                    new_cache_upd = {}
                    for fut in as_completed(futures):
                        sid = futures[fut]
                        try:
                            new_cache_upd[sid] = fut.result()
                        except:
                            new_cache_upd[sid] = {"status": "unknown", "start_type": "unknown"}
                    self._cache.update(new_cache_upd)
        self._ui(self._rebuild_tree)

    def _on_loaded(self):
        self._rebuild_tree()
        self._ref_btn.configure(state="normal")
        self._status_lbl.configure(text="✅ Статусы обновлены")
        self._prog["value"] = 100

    def _apply_preset(self, _=None):
        name = self._preset_var.get()
        info = PRESETS.get(name)
        if not info:
            return
        targets = []
        categories = info.get("categories", [])
        exclude_services = info.get("exclude_services", [])
        for sid, svc in SERVICES.items():
            if sid in CRITICAL_SERVICES or sid in PROTECTED_SERVICES or sid in exclude_services:
                continue
            if svc.get("risk") == "high":
                continue
            if svc.get("category", "") in categories:
                targets.append(sid)
        self._cat_var.set("Все")
        self._risk_var.set("Все")
        self._sf_var.set("Все")
        self._sq_var.set("")
        self._sorted_items_cache = None
        self._sort_cache_key = None
        self._rebuild_tree()
        existing = []
        for s in targets:
            tree_id = f"unk_{s}" if s in self._unknown_services and s not in SERVICES else s
            if self._tree.exists(tree_id):
                existing.append(tree_id)
        if existing:
            self._tree.selection_set(existing)
            self._tree.see(existing[0])
        self._status_lbl.configure(
            text=f"Пресет «{name}»: выбрано {len(existing)} служб — нажмите «Отключить»"
        )

    def _disable_selected(self):
        sel = list(self._tree.selection())
        if not sel:
            messagebox.showinfo("Нет выбора", "Выберите службы.")
            return
        real_sids = [get_real_sid(s) for s in sel if not s.startswith("del_")]
        if not real_sids:
            messagebox.showinfo("Нет выбора", "Выберите существующие службы.")
            return
        critical_in_sel = [s for s in real_sids if s in CRITICAL_SERVICES]
        if critical_in_sel and not messagebox.askyesno(
                "Критические службы",
                "⚠ Следующие службы являются критическими для системы:\n\n"
                + "\n".join(f"  • {SERVICES.get(s, {}).get('name', s)} ({s})" for s in critical_in_sel)
                + "\n\nИх отключение может сделать систему нестабильной!\n\nПродолжить?"):
            return
        names_list = [
            f"  • {SERVICES[s].get('name', s)}" if s in SERVICES
            else f"  • {self._unknown_services[s].get('name', s)} [Неизвестная]" if s in self._unknown_services
            else f"  • {s}"
            for s in real_sids
        ]
        if messagebox.askyesno("Отключить",
                               f"Отключить {len(real_sids)} служб?\n\n" + "\n".join(names_list)):
            self._run_bulk(real_sids, "disable")

    def _enable_selected(self):
        sel = list(self._tree.selection())
        if not sel:
            messagebox.showinfo("Нет выбора", "Выберите службы.")
            return
        real_sids = [get_real_sid(s) for s in sel if not s.startswith("del_")]
        if not real_sids:
            messagebox.showinfo("Нет выбора", "Выберите существующие службы.")
            return
        names_list = [
            f"  • {SERVICES[s].get('name', s)}" if s in SERVICES
            else f"  • {self._unknown_services[s].get('name', s)} [Неизвестная]" if s in self._unknown_services
            else f"  • {s}"
            for s in real_sids
        ]
        if messagebox.askyesno("Включить",
                               f"Включить {len(real_sids)} служб?\n\n" + "\n".join(names_list)):
            self._run_bulk(real_sids, "enable")

    def _run_bulk(self, sids, action):
        # Не фильтруем по текущему статусу — он может быть "unknown" если кеш устарел.
        total = len(sids)
        done = [0]
        ok = [0]
        fail = []
        lock = threading.Lock()
        self._status_lbl.configure(
            text=f"⏳ {'Отключение' if action == 'disable' else 'Включение'} {total} служб…"
        )
        self._prog["value"] = 0
        self._btn_dis.configure(state="disabled")
        self._btn_en.configure(state="disabled")

        def process(sid):
            if action == "disable":
                if sid in CRITICAL_SERVICES:
                    with lock:
                        fail.append(sid)
                        done[0] += 1
                        d = done[0]
                    self._ui(lambda d=d: self._prog.configure(value=min(d / total * 100, 100)))
                    return
                for dep in get_service_dependencies_list(sid):
                    if dep != sid and dep not in CRITICAL_SERVICES:
                        disable_service(dep)
                        self._cache.set(dep, query_service(dep))
                res = disable_service(sid)
                if not res:
                    deps = get_service_dependencies_list(sid)
                    if deps:
                        dep_names = []
                        for dep in deps:
                            dsvc = SERVICES.get(dep, self._unknown_services.get(dep, {}))
                            dep_names.append(f"{dep} ({dsvc.get('name', dep)})" if dsvc else dep)
                        append_log(f"ОШИБКА отключения {sid}. Зависимости: {', '.join(dep_names)}")
            else:
                res = enable_service(sid, self._cache.get(sid, {}).get("start_type", "auto"))
            self._cache.set(sid, query_service(sid))
            with lock:
                done[0] += 1
                d = done[0]
                if res:
                    ok[0] += 1
                else:
                    fail.append(sid)
            self._ui(lambda d=d: self._prog.configure(value=min(d / total * 100, 100)))

        self._thread_pool.submit(lambda: self._run_bulk_worker(process, sids, total, ok, fail, action))

    def _run_bulk_worker(self, process, sids_to_process, total, ok, fail, action):
        with ThreadPoolExecutor(max_workers=min(8, total)) as ex:
            list(ex.map(process, sids_to_process))
        self._ui(lambda: (
            self._rebuild_tree(),
            self._status_lbl.configure(
                text=f"✅ {'Отключено' if action == 'disable' else 'Включено'}: {ok[0]}"
                     + (f"   ❌ Ошибки: {len(fail)}" if fail else "")
            ),
            self._prog.configure(value=100),
            self._btn_dis.configure(state="normal"),
            self._btn_en.configure(state="normal")
        ))

    def _take_snapshot(self):
        if not messagebox.askyesno("Сохранить состояние",
                                    "Сохранить текущее состояние всех служб?\n\n"
                                    "При восстановлении будут восстановлены только те службы, "
                                    "которые сейчас запущены."):
            return
        self._status_lbl.configure(text="⏳ Сохранение состояния служб…")
        self._prog["value"] = 0
        all_services = list(SERVICES.keys()) + list(self._unknown_services.keys())
        total, done, snap, lock = len(all_services), [0], {}, threading.Lock()

        def qone(sid):
            r = query_service(sid)
            with lock:
                snap[sid] = r
                done[0] += 1
                d = done[0]
            self._ui(lambda d=d: self._prog.configure(value=min(d / total * 100, 100)))

        def worker():
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                list(ex.map(qone, all_services))
            snap["_meta"] = {"time": datetime.datetime.now().isoformat(), "count": total, "type": "manual"}
            save_snapshot(snap)
            self._cache.update({k: v for k, v in snap.items() if not k.startswith("_")})
            append_log("Сохранено состояние служб")
            self._ui(lambda: (
                self._rebuild_tree(),
                self._status_lbl.configure(text=f"📸 Состояние сохранено → {SNAPSHOT_FILE}"),
                self._prog.configure(value=100)
            ))

        self._thread_pool.submit(worker)

    def _restore_snapshot(self):
        snap = load_snapshot()
        if not snap:
            messagebox.showwarning("Снимок не найден",
                                   "Сначала сохраните состояние служб (📸 Сохранить состояние).")
            return
        meta = snap.get("_meta", {})
        if not messagebox.askyesno("Восстановить состояние",
                                    f"Восстановить состояние служб?\n"
                                    f"Дата сохранения: {meta.get('time', '?')}\n\n"
                                    f"Будут восстановлены только те службы, "
                                    f"которые были запущены на момент сохранения."):
            return
        running_targets = [(sid, st) for sid, st in snap.items()
                           if not sid.startswith("_") and st.get("status") == "running"]
        total = len(running_targets)
        done = [0]
        ok = [0]
        lock = threading.Lock()
        self._status_lbl.configure(text=f"⏳ Восстановление {total} служб…")
        self._prog["value"] = 0
        self._btn_dis.configure(state="disabled")
        self._btn_en.configure(state="disabled")
        self._snap_btn.configure(state="disabled")
        self._restore_btn.configure(state="disabled")

        def restore_one(item):
            sid, state = item
            enable_service(sid, state.get("start_type", "auto"))
            self._cache.set(sid, query_service(sid))
            append_log(f"ВОССТАНОВЛЕНИЕ  {sid}")
            with lock:
                ok[0] += 1
                done[0] += 1
                d = done[0]
            self._ui(lambda d=d: self._prog.configure(value=min(d / total * 100, 100)))

        def worker():
            with ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(restore_one, running_targets))
            self._ui(lambda: (
                self._rebuild_tree(),
                self._status_lbl.configure(text=f"♻ Восстановлено: {ok[0]} служб"),
                self._prog.configure(value=100),
                self._btn_dis.configure(state="normal"),
                self._btn_en.configure(state="normal"),
                self._snap_btn.configure(state="normal"),
                self._restore_btn.configure(state="normal")
            ))

        self._thread_pool.submit(worker)

    def _open_log(self):
        win = tk.Toplevel(self)
        win.title("📋 Журнал действий")
        win.geometry("860x520")
        win.configure(bg=BG)
        txt = scrolledtext.ScrolledText(win, bg=BG2, fg=FG2, font=("Consolas", 9),
                                         relief="flat", padx=10, pady=8)
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, encoding="utf-8") as f:
                txt.insert("end", f.read())
        else:
            txt.insert("end", "Журнал пуст.")
        txt.configure(state="disabled")

        def clear():
            open(LOG_FILE, "w").close()
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.configure(state="disabled")

        bf = tk.Frame(win, bg=BG)
        bf.pack(pady=4)
        tk.Button(bf, text="🗑 Очистить журнал", command=clear, bg="#FEF2F2", fg=DANGER,
                  relief="flat", font=("Segoe UI", 9), cursor="hand2", padx=10, pady=4, bd=0).pack(side="left", padx=4)
        tk.Button(bf, text="📁 Открыть папку backups", command=lambda: os.startfile(BACKUP_DIR),
                  bg=BG3, fg=ACCENT, relief="flat", font=("Segoe UI", 9),
                  cursor="hand2", padx=10, pady=4, bd=0).pack(side="left", padx=4)


if __name__ == "__main__":
    if sys.platform != "win32":
        print("Программа работает только на Windows.")
        sys.exit(1)
    if not is_admin():
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                subprocess.list2cmdline(sys.argv), None, 1
            )
        except:
            pass
        sys.exit(0)
    App().mainloop()
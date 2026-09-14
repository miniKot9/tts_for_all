import threading
import tkinter as tk
from tkinter import ttk, messagebox
import sounddevice as sd
import torch
import re
import json
import os
import keyboard
import win32gui
import win32con
import ctypes
import ctypes.wintypes
import time
import numpy as np

# ============ ФУНКЦИЯ ДЛЯ ПРЕОБРАЗОВАНИЯ ЧИСЕЛ В ТЕКСТ ============
def number_to_words(text):
    """Преобразует цифры в слова для озвучивания (поддержка тысяч, миллионов, '10к', '2кк')"""
    
    units_male = {
        0: '', 1: 'один', 2: 'два', 3: 'три', 4: 'четыре',
        5: 'пять', 6: 'шесть', 7: 'семь', 8: 'восемь', 9: 'девять'
    }
    
    units_female = {
        0: '', 1: 'одна', 2: 'две', 3: 'три', 4: 'четыре',
        5: 'пять', 6: 'шесть', 7: 'семь', 8: 'восемь', 9: 'девять'
    }
    
    tens = {
        0: '', 1: 'десять', 2: 'двадцать', 3: 'тридцать', 4: 'сорок',
        5: 'пятьдесят', 6: 'шестьдесят', 7: 'семьдесят',
        8: 'восемьдесят', 9: 'девяносто'
    }
    
    hundreds = {
        0: '', 1: 'сто', 2: 'двести', 3: 'триста', 4: 'четыреста',
        5: 'пятьсот', 6: 'шестьсот', 7: 'семьсот',
        8: 'восемьсот', 9: 'девятьсот'
    }
    
    teens = {
        10: 'десять', 11: 'одиннадцать', 12: 'двенадцать',
        13: 'тринадцать', 14: 'четырнадцать', 15: 'пятнадцать',
        16: 'шестнадцать', 17: 'семнадцать', 18: 'восемнадцать',
        19: 'девятнадцать'
    }
    
    def plural_form(n, form1, form2, form5):
        n_abs = abs(n) % 100
        n1 = n_abs % 10
        if 11 <= n_abs <= 19:
            return form5
        if n1 == 1:
            return form1
        if 2 <= n1 <= 4:
            return form2
        return form5
    
    def triplet_to_words(n, female=False):
        if n == 0:
            return ''
        result = []
        h = n // 100
        if h > 0:
            result.append(hundreds[h])
        remainder = n % 100
        if 10 <= remainder <= 19:
            result.append(teens[remainder])
        else:
            t = remainder // 10
            u = remainder % 10
            if t > 0:
                result.append(tens[t])
            if u > 0:
                result.append(units_female[u] if female else units_male[u])
        return ' '.join(result)
    
    def convert_number(num):
        if num == 0:
            return 'ноль'
        if num < 0:
            return 'минус ' + convert_number(abs(num))
        result = []
        billions = num // 1_000_000_000
        if billions > 0:
            result.append(triplet_to_words(billions))
            result.append(plural_form(billions, 'миллиард', 'миллиарда', 'миллиардов'))
        millions = (num // 1_000_000) % 1000
        if millions > 0:
            result.append(triplet_to_words(millions))
            result.append(plural_form(millions, 'миллион', 'миллиона', 'миллионов'))
        thousands = (num // 1_000) % 1000
        if thousands > 0:
            result.append(triplet_to_words(thousands, female=True))
            result.append(plural_form(thousands, 'тысяча', 'тысячи', 'тысяч'))
        remainder = num % 1000
        if remainder > 0:
            result.append(triplet_to_words(remainder))
        return ' '.join(filter(None, result))
    
    def replace_k_suffix(match):
        number_str = match.group(1)
        suffix = match.group(2).lower()
        try:
            number = float(number_str)
        except ValueError:
            return match.group(0)
        k_count = len(suffix)
        if k_count == 1:
            result_num = int(number * 1_000)
        elif k_count == 2:
            result_num = int(number * 1_000_000)
        elif k_count >= 3:
            result_num = int(number * 1_000_000_000)
        else:
            return match.group(0)
        return convert_number(result_num)
    
    text = re.sub(r'(\d+(?:[.,]\d+)?)\s*([кkКK]+)\b', replace_k_suffix, text)
    
    def replace_number(match):
        num_str = match.group(0)
        decimal_match = re.match(r'^(\d+)[.,](\d{1,2})$', num_str)
        if decimal_match and len(num_str) <= 6:
            whole = int(decimal_match.group(1))
            frac = decimal_match.group(2)
            result = convert_number(whole)
            result += ' целых ' if frac else ''
            frac_num = int(frac)
            result += convert_number(frac_num)
            return result
        clean = num_str.replace(' ', '').replace(',', '').replace('.', '')
        try:
            num = int(clean)
            if num > 999_999_999_999:
                return num_str
            return convert_number(num)
        except ValueError:
            return num_str
    
    pattern = r'\b\d{1,3}(?:[ ,.]\d{3})+(?:\d+)?\b|\b\d+\b'
    result = re.sub(pattern, replace_number, text)
    return result


# ============ ЗАГРУЗЧИК ПРАВИЛ ЗАМЕНЫ ============
class ReplacementsLoader:
    """Загружает правила замены из текстового файла"""
    
    def __init__(self, filename="replacements.txt"):
        self.filename = filename
        self.rules = []
        self.load()
    
    def load(self):
        self.rules = []
        if not os.path.exists(self.filename):
            print(f"⚠️ Файл {self.filename} не найден, создаю шаблон...")
            self._create_default_file()
            return
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' not in line:
                        continue
                    parts = line.split('=', 1)
                    if len(parts) != 2:
                        continue
                    search = parts[0].strip()
                    replace = parts[1].strip()
                    if not search:
                        continue
                    pattern = re.compile(
                        r'\b' + re.escape(search) + r'\b',
                        re.IGNORECASE
                    )
                    self.rules.append((pattern, replace))
            print(f"✅ Загружено {len(self.rules)} правил из {self.filename}")
        except Exception as e:
            print(f"❌ Ошибка загрузки {self.filename}: {e}")
    
    def apply(self, text):
        for pattern, replacement in self.rules:
            text = pattern.sub(replacement, text)
        return text
    
    def _create_default_file(self):
        default_content = """# ============================================
# ПРАВИЛА ЗАМЕНЫ ДЛЯ TTS
# ============================================
# Формат: что_искать = на_что_заменить
# - Замена только для целых слов (\\b с обеих сторон)
# - Регистр не важен
# - Строки с # игнорируются
# ============================================

# ===== СОКРАЩЕНИЯ =====
хз = хэзэ
мб = может быть
плз = пожалуйста
спс = спасибо
"""
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                f.write(default_content)
            print(f"✅ Создан файл {self.filename} с примерами")
        except Exception as e:
            print(f"❌ Не удалось создать {self.filename}: {e}")


# ============ ФУНКЦИЯ ДЛЯ ДОБАВЛЕНИЯ ЭМОЦИОНАЛЬНЫХ ПОДСКАЗОК ============
def add_emotion_tags(text, replacements=None, language="ru"):
    """Заменяет сокращения и знаки эмоций на слова-подсказки для TTS модели"""
    
    # ===== 1. ЗАМЕНЫ ИЗ ФАЙЛА =====
    if replacements is not None:
        text = replacements.apply(text)
    
    # ===== 2. ЗНАКИ ЭМОЦИЙ (только для русского) =====
    if language == "ru":
        text = re.sub(r'\?+', ' вопрос ', text)
        text = re.sub(r'!+', ' восклицаю ', text)
        text = re.sub(r'\)+', ' хе ', text)
        text = re.sub(r'\(+', ' расстройство ', text)
        text = re.sub(r'\(%', ' процент ', text)
        text = re.sub(r'\bВС\b', ' вэ эс ', text)
        text = re.sub(r'\bН\b', ' эн ', text)
        text = re.sub(r'\bНЕ\b', ' эн е ', text)
        text = re.sub(r'\bСЕ\b', ' эс е ', text)
        text = re.sub(r'\bВС\b', ' вэ эс ', text)
        text = re.sub(r'\bВН\b', ' вэ эн ', text)
    
    # ===== 3. ЭМОТИКОНЫ (универсальные) =====
    text = re.sub(r'\b:P\b', ' бее ', text, flags=re.IGNORECASE)
    
    # ===== 4. ОЧИСТКА ПРОБЕЛОВ =====
    text = re.sub(r'\s+', ' ', text).strip()
    
    # ===== 5. ТОЧКА В КОНЦЕ =====
    if text and text[-1] not in '.!?…':
        text += '.'
    
    return text


# ============ КЛАСС ДЛЯ РАБОТЫ С НАСТРОЙКАМИ ============
class SettingsManager:
    def __init__(self, filename="tts_settings.json"):
        self.filename = filename
        self.default_settings = {
            "language": "Русский",
            "voice": "",
            "device": "",
            "window_geometry": "700x620",
            "monitor_enabled": False,
            "monitor_device": "",
            "monitor_volume": 80,
            "current_tab": "main"   # "main" или "settings"
        }
    
    def load(self):
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    for key, value in self.default_settings.items():
                        if key not in settings:
                            settings[key] = value
                    return settings
        except Exception as e:
            print(f"Ошибка загрузки настроек: {e}")
        return self.default_settings.copy()
    
    def save(self, settings):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")
            return False


# ============ КЛАСС TTS ДВИЖКА (мультиязычный) ============
class TTS_Engine:
    """Движок Silero TTS с поддержкой нескольких языков"""
    
    # Доступные языки и их параметры
    LANGUAGES = {
        "Русский": {
            "code": "ru",
            "speaker_model": "v3_1_ru",
            "voices": {
                "kseniya (женский)": "xenia",
                "baya (женский)": "baya",
                "aidar (мужской)": "aidar",
                "eugene (мужской)": "eugene",
            }
        },
        "English": {
            "code": "en",
            "speaker_model": "v3_en",
            "voices": {
                "en_0 (женский)": "en_0",
                "en_1 (женский)": "en_1",
                "en_2 (мужской)": "en_2",
                "en_3 (мужской)": "en_3",
                "en_4 (женский)": "en_4",
                "en_5 (мужской)": "en_5",
                "en_6 (женский)": "en_6",
                "en_7 (мужской)": "en_7",
                "en_8 (женский)": "en_8",
                "en_9 (мужской)": "en_9",
            }
        },
        "Deutsch": {
            "code": "de",
            "speaker_model": "v3_de",
            "voices": {
                "eva_k (женский)": "eva_k",
                "bernd (мужской)": "bernd",
                "karlsson (мужской)": "karlsson",
            }
        },
        "Español": {
            "code": "es",
            "speaker_model": "v3_es",
            "voices": {
                "es_0 (женский)": "es_0",
                "es_1 (мужской)": "es_1",
                "es_2 (мужской)": "es_2",
            }
        },
        "Français": {
            "code": "fr",
            "speaker_model": "v3_fr",
            "voices": {
                "fr_0 (женский)": "fr_0",
                "fr_1 (мужской)": "fr_1",
                "fr_2 (женский)": "fr_2",
                "fr_3 (мужской)": "fr_3",
                "fr_4 (женский)": "fr_4",
                "fr_5 (мужской)": "fr_5",
            }
        },
        "Українська": {
            "code": "ua",
            "speaker_model": "v3_ua",
            "voices": {
                "ua_0 (женский)": "ua_0",
                "ua_1 (мужской)": "ua_1",
                "ua_2 (женский)": "ua_2",
                "ua_3 (мужской)": "ua_3",
                "ua_4 (женский)": "ua_4",
            }
        },
    }
    
    def __init__(self):
        self.models = {}              # кэш моделей по коду языка
        self.sample_rate = 48000
        self.current_language_display = "Русский"
        self.current_speaker = "xenia"
        self.available_speakers = []
        self._lock = threading.Lock()  # защита от одновременной загрузки
    
    def get_language_code(self, display_name):
        """Возвращает код языка по отображаемому имени"""
        return self.LANGUAGES.get(display_name, {}).get("code", "ru")
    
    def get_voices(self, display_name):
        """Возвращает словарь голосов для языка"""
        return self.LANGUAGES.get(display_name, {}).get("voices", {})
    
    def is_loaded(self, language_code):
        """Проверяет, загружена ли модель для языка"""
        return language_code in self.models
    
    def load_model(self, language_display="Русский", progress_callback=None):
        """Загружает модель для указанного языка (с кэшированием)"""
        lang_info = self.LANGUAGES.get(language_display)
        if not lang_info:
            raise ValueError(f"Неизвестный язык: {language_display}")
        
        lang_code = lang_info["code"]
        
        # Если модель уже загружена — просто переключаемся
        if lang_code in self.models:
            self.current_language_display = language_display
            self.available_speakers = list(lang_info["voices"].values())
            if progress_callback:
                progress_callback(f"✓ Модель {language_display} уже загружена")
            return
        
        if progress_callback:
            progress_callback(f"Загрузка модели {language_display}...")
        
        try:
            model, example_text = torch.hub.load(
                repo_or_dir='snakers4/silero-models',
                model='silero_tts',
                language=lang_code,
                speaker=lang_info["speaker_model"]
            )
            model.to(torch.device('cpu'))
            
            with self._lock:
                self.models[lang_code] = model
                self.current_language_display = language_display
                self.available_speakers = list(lang_info["voices"].values())
            
            if progress_callback:
                progress_callback(f"✓ Модель {language_display} загружена")
        except Exception as ex:
            if progress_callback:
                progress_callback(f"Ошибка загрузки {language_display}: {ex}")
            raise
    
    def synthesize(self, text, speaker=None, language_display=None):
        """Синтез речи на указанном языке"""
        if language_display is None:
            language_display = self.current_language_display
        
        lang_code = self.get_language_code(language_display)
        
        if lang_code not in self.models:
            raise RuntimeError(f"Модель {language_display} не загружена")
        
        model = self.models[lang_code]
        
        if speaker is None:
            speaker = self.current_speaker
        
        # Проверка доступности голоса
        available = list(self.get_voices(language_display).values())
        if available and speaker not in available:
            fallback = available[0]
            print(f"Голос {speaker} недоступен, используем {fallback}")
            speaker = fallback
        
        with torch.no_grad():
            audio = model.apply_tts(
                text=text,
                speaker=speaker,
                sample_rate=self.sample_rate
            )
        return audio.numpy()


# ============ ГЛАВНОЕ ПРИЛОЖЕНИЕ ============
class TTS_App:
    
    def __init__(self, root):
        self.root = root
        self.root.title("TTS для Discord (Silero, мультиязычный)")
        self.root.geometry("700x780")
        self.root.configure(bg="#2b2b2b")
        
        self.previous_window = None
        self.opened_by_hotkey = False
        self.lang_loading = False  # флаг, что сейчас идёт загрузка модели
        
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.load()
        if "window_geometry" in self.settings:
            self.root.geometry(self.settings["window_geometry"])
        
        self.engine = TTS_Engine()
        self.is_playing = False
        self.audio_devices = self._get_audio_devices()
        
        # Загрузка правил замены (для русского)
        self.replacements = ReplacementsLoader("replacements.txt")
        # Загрузка английских правил, если есть файл
        self.replacements_en = ReplacementsLoader("replacements_en.txt")
        
        self.settings_expanded = tk.BooleanVar(value=self.settings.get("settings_expanded", True))
        
        self._build_ui()
        self._apply_saved_settings()
        
        self._setup_global_hotkey()
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Загружаем модель для сохранённого языка
        saved_lang = self.settings.get("language", "Русский")
        threading.Thread(target=self._load_model_async, args=(saved_lang,), daemon=True).start()
    
    def _setup_global_hotkey(self):
        try:
            keyboard.add_hotkey('ctrl+enter',
                              lambda: self.root.after(0, self._show_and_focus))
            print("✓ Глобальная горячая клавиша Ctrl+Enter активна")
        except Exception as e:
            print(f"Не удалось установить глобальную горячую клавишу: {e}")
    
    def _force_foreground(self, hwnd):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
        user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
        kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD
        kernel32.GetCurrentThreadId.argtypes = []
        user32.AttachThreadInput.restype = ctypes.wintypes.BOOL
        user32.AttachThreadInput.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.BOOL]
        
        foreground_hwnd = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()
        
        if foreground_thread != current_thread:
            user32.AttachThreadInput(current_thread, foreground_thread, True)
            user32.BringWindowToTop(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.AttachThreadInput(current_thread, foreground_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
    
    def _show_and_focus(self):
        self.previous_window = win32gui.GetForegroundWindow()
        self.opened_by_hotkey = True
        self.root.update_idletasks()
        
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
        except:
            hwnd = None
        
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.update()
        time.sleep(0.05)
        
        if hwnd:
            try:
                self._force_foreground(hwnd)
            except Exception as e:
                print(f"Ошибка захвата фокуса: {e}")
        
        self.root.after(150, lambda: self.root.attributes('-topmost', False))
        self.root.after(100, lambda: self.text_entry.focus_force())
    
    def _get_audio_devices(self):
        devices = sd.query_devices()
        return [(i, d['name']) for i, d in enumerate(devices) if d['max_output_channels'] > 0]
    
    
    def _build_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', background='#2b2b2b', foreground='white', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10))
        style.configure('TCombobox', font=('Segoe UI', 10))
        style.configure('TCheckbutton', background='#2b2b2b', foreground='white', font=('Segoe UI', 10))
        
        # ============================================================
        # ===== ШАПКА С ЗАГОЛОВКОМ И ВКЛАДКАМИ =====
        # ============================================================
        header = tk.Frame(self.root, bg="#1a1a1a", height=50)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)
        
        # Заголовок слева
        tk.Label(
            header, text="🎙️ TTS",
            bg="#1a1a1a", fg="#4fc3f7",
            font=('Segoe UI', 13, 'bold'),
            padx=15
        ).pack(side=tk.LEFT, fill=tk.Y)
        
        # Контейнер для вкладок справа
        tabs_frame = tk.Frame(header, bg="#1a1a1a")
        tabs_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Вкладка «Основная»
        self.btn_tab_main = tk.Button(
            tabs_frame, text="📝 Основная",
            bg="#222222", fg="#888888",
            font=('Segoe UI', 10, 'bold'),
            relief=tk.FLAT, bd=0,
            padx=20, pady=0,
            cursor='hand2',
            activebackground="#2b2b2b",
            activeforeground="#ffffff",
            command=lambda: self._switch_tab("main")
        )
        self.btn_tab_main.pack(side=tk.LEFT, fill=tk.Y)
        
        # Вкладка «Настройки»
        self.btn_tab_settings = tk.Button(
            tabs_frame, text="⚙️ Настройки",
            bg="#222222", fg="#888888",
            font=('Segoe UI', 10, 'bold'),
            relief=tk.FLAT, bd=0,
            padx=20, pady=0,
            cursor='hand2',
            activebackground="#2b2b2b",
            activeforeground="#ffffff",
            command=lambda: self._switch_tab("settings")
        )
        self.btn_tab_settings.pack(side=tk.LEFT, fill=tk.Y)
        
        # ============================================================
        # ===== КОНТЕНТ (сюда пакуются страницы вкладок) =====
        # ============================================================
        self.content = tk.Frame(self.root, bg="#2b2b2b")
        self.content.pack(fill=tk.BOTH, expand=True)
        
        # ============================================================
        # ===== СТРАНИЦА 1: ОСНОВНАЯ =====
        # ============================================================
        self.page_main = tk.Frame(self.content, bg="#2b2b2b", padx=20, pady=15)
        
        text_frame = tk.Frame(self.page_main, bg="#2b2b2b")
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        tk.Label(text_frame, text="✏️ Текст (Enter — озвучить):",
                 bg="#2b2b2b", fg="white", font=('Segoe UI', 10), anchor='w').pack(fill=tk.X, pady=(0, 4))
        
        self.text_entry = tk.Text(
            text_frame, height=8,
            bg="#1e1e1e", fg="white",
            insertbackground="white", font=('Segoe UI', 11),
            relief=tk.FLAT, padx=8, pady=8,
            wrap=tk.WORD
        )
        self.text_entry.pack(fill=tk.BOTH, expand=True)
        self.text_entry.bind('<Return>', self._on_enter)
        self.text_entry.bind('<Key>', self._handle_hotkeys)
        
        # Кнопки основной страницы
        btn_frame = tk.Frame(self.page_main, bg="#2b2b2b")
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.speak_btn = tk.Button(
            btn_frame, text="🔊 Озвучить",
            bg="#4fc3f7", fg="black",
            font=('Segoe UI', 11, 'bold'),
            relief=tk.FLAT, bd=0,
            padx=20, pady=10,
            cursor='hand2',
            width=13, height=1,
            activebackground="#3ab0d6",
            command=self._speak
        )
        self.speak_btn.pack(side=tk.LEFT, padx=(0, 6))
        
        self.stop_btn = tk.Button(
            btn_frame, text="⏹ Стоп",
            bg="#ef5350", fg="white",
            font=('Segoe UI', 11, 'bold'),
            relief=tk.FLAT, bd=0,
            padx=20, pady=10,
            cursor='hand2',
            width=10, height=1,
            activebackground="#c62828",
            command=self._stop
        )
        self.stop_btn.pack(side=tk.LEFT, padx=6)
        
        tk.Button(
            btn_frame, text="🔄 Правила",
            bg="#444444", fg="white",
            font=('Segoe UI', 10),
            relief=tk.FLAT, bd=0,
            padx=20, pady=10,
            cursor='hand2',
            width=12, height=1,
            activebackground="#555555",
            command=self._reload_replacements
        ).pack(side=tk.LEFT, padx=6)
        
        tk.Label(
            self.page_main,
            text="💡 В Discord выберите «VB-Audio Virtual Cable» как устройство ввода",
            bg="#2b2b2b", fg="#888",
            font=('Segoe UI', 9), anchor='w'
        ).pack(fill=tk.X, pady=(10, 0))
        
        tk.Label(
            self.page_main,
            text="⌨️ Ctrl+Enter — открыть | Enter — озвучить | Esc — свернуть",
            bg="#2b2b2b", fg="#666",
            font=('Segoe UI', 8), anchor='w'
        ).pack(fill=tk.X, pady=(2, 0))
        
        # ============================================================
        # ===== СТРАНИЦА 2: НАСТРОЙКИ =====
        # ============================================================
        self.page_settings = tk.Frame(self.content, bg="#2b2b2b", padx=20, pady=15)
        
        # ===== ЯЗЫК =====
        tk.Label(self.page_settings, text="🌍 Язык:",
                 bg="#2b2b2b", fg="white", font=('Segoe UI', 10), anchor='w').pack(fill=tk.X, pady=(0, 3))
        
        self.language_var = tk.StringVar()
        language_names = list(self.engine.LANGUAGES.keys())
        self.language_combo = ttk.Combobox(
            self.page_settings,
            textvariable=self.language_var,
            values=language_names,
            state='readonly'
        )
        self.language_combo.pack(fill=tk.X, pady=(0, 12))
        self.language_combo.bind('<<ComboboxSelected>>', self._on_language_change)
        
        # ===== ГОЛОС =====
        tk.Label(self.page_settings, text="🎤 Голос:",
                 bg="#2b2b2b", fg="white", font=('Segoe UI', 10), anchor='w').pack(fill=tk.X, pady=(0, 3))
        
        self.voice_var = tk.StringVar()
        self.voice_combo = ttk.Combobox(
            self.page_settings,
            textvariable=self.voice_var,
            values=[], state='readonly'
        )
        self.voice_combo.pack(fill=tk.X, pady=(0, 12))
        self.voice_combo.bind('<<ComboboxSelected>>', self._on_voice_change)
        
        # ===== АУДИОВЫХОД =====
        tk.Label(self.page_settings, text="🔊 Аудиовыход (VB-Cable для Discord):",
                 bg="#2b2b2b", fg="white", font=('Segoe UI', 10), anchor='w').pack(fill=tk.X, pady=(0, 3))
        
        self.device_var = tk.StringVar()
        device_names = [f"{i}: {name}" for i, name in self.audio_devices]
        self.device_combo = ttk.Combobox(
            self.page_settings,
            textvariable=self.device_var,
            values=device_names, state='readonly'
        )
        self.device_combo.pack(fill=tk.X, pady=(0, 12))
        self.device_combo.bind('<<ComboboxSelected>>', self._on_device_change)
        
        for i, (idx, name) in enumerate(self.audio_devices):
            if 'cable' in name.lower() or 'vb' in name.lower():
                self.device_combo.current(i)
                break
        else:
            if device_names:
                self.device_combo.current(0)
        
        # ===== РАЗДЕЛИТЕЛЬ =====
        sep_frame = tk.Frame(self.page_settings, bg="#2b2b2b")
        sep_frame.pack(fill=tk.X, pady=(5, 10))
        tk.Label(sep_frame, text="🎧 ПРОСЛУШИВАНИЕ",
                 bg="#2b2b2b", fg="#4fc3f7",
                 font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
        tk.Frame(sep_frame, bg="#444444", height=1).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0), pady=8)
        
        # ===== ЧЕКБОКС ПРОСЛУШИВАНИЯ =====
        self.monitor_enabled_var = tk.BooleanVar(value=self.settings.get("monitor_enabled", False))
        self.monitor_checkbox = tk.Checkbutton(
            self.page_settings,
            text="Включить прослушивание в динамиках",
            variable=self.monitor_enabled_var,
            bg="#2b2b2b", fg="white",
            selectcolor="#1e1e1e",
            activebackground="#2b2b2b", activeforeground="white",
            font=('Segoe UI', 10),
            cursor='hand2',
            command=self._on_monitor_toggle
        )
        self.monitor_checkbox.pack(anchor='w', pady=(0, 10))
        
        # ===== КОНТЕЙНЕР ДЛЯ ДОП. ПОЛЕЙ (появляются при включении) =====
        self.monitor_details = tk.Frame(self.page_settings, bg="#2b2b2b")
        
        tk.Label(self.monitor_details, text="🎧 Устройство прослушивания:",
                 bg="#2b2b2b", fg="#ccc", font=('Segoe UI', 10), anchor='w').pack(fill=tk.X, pady=(0, 3))
        
        self.monitor_device_var = tk.StringVar()
        self.monitor_device_combo = ttk.Combobox(
            self.monitor_details,
            textvariable=self.monitor_device_var,
            values=device_names, state='readonly'
        )
        self.monitor_device_combo.pack(fill=tk.X, pady=(0, 10))
        self.monitor_device_combo.bind('<<ComboboxSelected>>', self._on_monitor_device_change)
        
        # Громкость прослушивания
        vol_frame = tk.Frame(self.monitor_details, bg="#2b2b2b")
        vol_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(vol_frame, text="Громкость:",
                 bg="#2b2b2b", fg="#ccc", font=('Segoe UI', 10)).pack(side=tk.LEFT)
        
        self.monitor_volume_value_label = tk.Label(
            vol_frame, text=str(self.settings.get("monitor_volume", 80)),
            bg="#2b2b2b", fg="#4fc3f7", font=('Segoe UI', 10, 'bold'),
            width=4
        )
        self.monitor_volume_value_label.pack(side=tk.RIGHT)
        
        self.monitor_volume_var = tk.IntVar(value=self.settings.get("monitor_volume", 80))
        self.monitor_volume_slider = tk.Scale(
            self.monitor_details,
            from_=0, to=100,
            orient=tk.HORIZONTAL,
            variable=self.monitor_volume_var,
            bg="#2b2b2b", fg="white",
            troughcolor="#1e1e1e",
            activebackground="#4fc3f7",
            highlightthickness=0,
            showvalue=False,
            sliderrelief=tk.FLAT,
            length=300,
            command=self._on_monitor_volume_change
        )
        self.monitor_volume_slider.pack(fill=tk.X)
        
        tk.Label(
            self.monitor_details,
            text="💡 Включите, чтобы слышать TTS в динамиках. Discord всё равно получит звук через кабель.",
            bg="#2b2b2b", fg="#666",
            font=('Segoe UI', 8),
            anchor='w', wraplength=600, justify='left'
        ).pack(fill=tk.X, pady=(5, 0))
        
        # ============================================================
        # ===== СТАТУС-БАР ВНИЗУ =====
        # ============================================================
        status_frame = tk.Frame(self.root, bg="#1a1a1a", height=28)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        status_frame.pack_propagate(False)
        
        self.status_label = tk.Label(
            status_frame, text="Загрузка...",
            bg="#1a1a1a", fg="#f0c040",
            font=('Segoe UI', 9),
            anchor='w', padx=15
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.Y)
        
        self.progress = ttk.Progressbar(
            status_frame, mode='indeterminate', length=200
        )
        self.progress.pack(side=tk.RIGHT, padx=10, pady=4)
        self.progress.start()
        
        # Применяем сохранённую вкладку
        saved_tab = self.settings.get("current_tab", "main")
        self._switch_tab(saved_tab)
        
        # Обновляем состояние полей прослушивания
        self._toggle_monitor_fields()
        
        # Привязка Escape
        self.root.bind_all('<Escape>', self._on_escape)
        
    def _reload_replacements(self):
        """Перезагружает правила замены"""
        self.replacements.load()
        self.replacements_en.load()
        messagebox.showinfo("Готово",
            f"Правила перезагружены\n"
            f"Русские: {len(self.replacements.rules)}\n"
            f"Английские: {len(self.replacements_en.rules)}")
    
    
    # ===== Обработчики =====
    def _switch_tab(self, tab_name):
        """Переключает между вкладками 'main' и 'settings'"""
        if tab_name == "main":
            self.page_settings.pack_forget()
            self.page_main.pack(fill=tk.BOTH, expand=True)
            # Подсветка активной вкладки
            self.btn_tab_main.config(bg="#2b2b2b", fg="#ffffff")
            self.btn_tab_settings.config(bg="#222222", fg="#888888")
        else:
            self.page_main.pack_forget()
            self.page_settings.pack(fill=tk.BOTH, expand=True)
            self.btn_tab_settings.config(bg="#2b2b2b", fg="#ffffff")
            self.btn_tab_main.config(bg="#222222", fg="#888888")
        
        # Сохраняем выбор
        self.settings["current_tab"] = tab_name
        self.settings_manager.save(self.settings)
    
    def _toggle_monitor_fields(self):
        """Показывает/скрывает поля прослушивания в зависимости от галочки"""
        if self.monitor_enabled_var.get():
            # Показываем поля (после чекбокса)
            self.monitor_details.pack(fill=tk.X, pady=(0, 5))
        else:
            # Скрываем поля
            self.monitor_details.pack_forget()
    
    def _on_monitor_toggle(self):
        self._toggle_monitor_fields()
        self._save_settings()
    
    def _on_monitor_device_change(self, event=None):
        self._save_settings()
    
    def _on_monitor_volume_change(self, value):
        # Обновляем число рядом со слайдером
        self.monitor_volume_value_label.config(text=str(int(float(value))))
        self._save_settings()
    
    def _handle_hotkeys(self, event):
        if not (event.state & 0x4):
            return
        keycode = event.keycode
        if keycode == 65:
            self.text_entry.tag_add('sel', '1.0', 'end-1c')
            self.text_entry.mark_set('insert', '1.0')
            self.text_entry.see('insert')
            return 'break'
        elif keycode == 67:
            try:
                selected = self.text_entry.get('sel.first', 'sel.last')
                self.root.clipboard_clear()
                self.root.clipboard_append(selected)
            except tk.TclError:
                pass
            return 'break'
        elif keycode == 88:
            try:
                selected = self.text_entry.get('sel.first', 'sel.last')
                self.root.clipboard_clear()
                self.root.clipboard_append(selected)
                self.text_entry.delete('sel.first', 'sel.last')
            except tk.TclError:
                pass
            return 'break'
        elif keycode == 86:
            try:
                text = self.root.clipboard_get()
                self.text_entry.insert(tk.INSERT, text)
            except tk.TclError:
                pass
            return 'break'
    
    def _apply_saved_settings(self):
        """Восстановление настроек"""
        # Язык
        saved_lang = self.settings.get("language", "Русский")
        if saved_lang in self.engine.LANGUAGES:
            self.language_var.set(saved_lang)
        
        # Обновляем список голосов
        voices = self.engine.get_voices(self.language_var.get())
        voice_names = list(voices.keys())
        self.voice_combo['values'] = voice_names
        
        # Голос
        saved_voice = self.settings.get("voice", "")
        if saved_voice and saved_voice in voice_names:
            self.voice_combo.set(saved_voice)
            self.engine.current_speaker = voices[saved_voice]
        elif voice_names:
            self.voice_combo.set(voice_names[0])
            self.engine.current_speaker = voices[voice_names[0]]
        
        # Основное устройство
        saved_device = self.settings.get("device", "")
        if saved_device:
            device_names = self.device_combo['values']
            for i, name in enumerate(device_names):
                if saved_device in name:
                    self.device_combo.current(i)
                    break
        
        # Устройство прослушивания
        saved_monitor_device = self.settings.get("monitor_device", "")
        if saved_monitor_device:
            device_names = self.monitor_device_combo['values']
            for i, name in enumerate(device_names):
                if saved_monitor_device in name:
                    self.monitor_device_combo.current(i)
                    break
        else:
            if self.monitor_device_combo['values']:
                self.monitor_device_combo.current(0)
    
    def _save_settings(self):
        self.settings["language"] = self.language_var.get()
        self.settings["voice"] = self.voice_var.get()
        self.settings["device"] = self.device_var.get()
        self.settings["window_geometry"] = self.root.geometry()
        self.settings["monitor_enabled"] = self.monitor_enabled_var.get()
        self.settings["monitor_device"] = self.monitor_device_var.get()
        self.settings["monitor_volume"] = self.monitor_volume_var.get()
        self.settings["settings_expanded"] = self.settings_expanded.get()
        self.settings_manager.save(self.settings)
    
    def _on_language_change(self, event=None):
        """Смена языка — обновляем голоса и загружаем модель"""
        if self.lang_loading:
            messagebox.showwarning("Подождите", "Модель ещё загружается...")
            return
        
        lang_display = self.language_var.get()
        lang_code = self.engine.get_language_code(lang_display)
        
        # Обновляем список голосов
        voices = self.engine.get_voices(lang_display)
        voice_names = list(voices.keys())
        self.voice_combo['values'] = voice_names
        if voice_names:
            self.voice_combo.set(voice_names[0])
            self.engine.current_speaker = voices[voice_names[0]]
        
        self._save_settings()
        
        # Если модель уже загружена — не нужно ничего качать
        if self.engine.is_loaded(lang_code):
            self.status_label.config(text=f"✓ Модель {lang_display} уже загружена",
                                     foreground='#66bb6a')
            self.engine.current_language_display = lang_display
            return
        
        # Иначе — загружаем в фоне
        self.lang_loading = True
        self.language_combo.config(state='disabled')
        self.voice_combo.config(state='disabled')
        self.progress.pack(pady=5, before=self.settings_header)
        self.progress.start()
        
        threading.Thread(target=self._load_model_async,
                        args=(lang_display,), daemon=True).start()
    
    def _on_voice_change(self, event=None):
        voices = self.engine.get_voices(self.language_var.get())
        voice_name = self.voice_var.get()
        if voice_name in voices:
            self.engine.current_speaker = voices[voice_name]
        self._save_settings()
    
    def _on_device_change(self, event=None):
        self._save_settings()
    
    def _get_selected_device_id(self):
        sel = self.device_var.get()
        if not sel:
            return None
        try:
            return int(sel.split(':')[0])
        except:
            return None
    
    def _get_monitor_device_id(self):
        sel = self.monitor_device_var.get()
        if not sel:
            return None
        try:
            return int(sel.split(':')[0])
        except:
            return None
    
    def _load_model_async(self, language_display):
        """Загрузка модели в отдельном потоке"""
        def progress(msg):
            self.root.after(0, lambda m=msg: self.status_label.config(text=f"Статус: {m}"))
        
        try:
            self.engine.load_model(language_display, progress_callback=progress)
            self.root.after(0, lambda: self.status_label.config(
                text=f"✓ {language_display} готов", foreground='#66bb6a'))
            self.root.after(0, lambda: self.progress.stop())
            self.root.after(0, lambda: self.progress.pack_forget())
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda msg=error_msg: messagebox.showerror(
                "Ошибка", f"Не удалось загрузить модель:\n{msg}"))
            self.root.after(0, lambda msg=error_msg: self.status_label.config(
                text=f"Ошибка: {msg[:50]}...", foreground='red'))
        finally:
            self.lang_loading = False
            self.root.after(0, lambda: self.language_combo.config(state='readonly'))
            self.root.after(0, lambda: self.voice_combo.config(state='readonly'))
    
    def _on_enter(self, event):
        if event.state & 0x1:
            return
        self._speak()
        if self.opened_by_hotkey and self.previous_window:
            try:
                win32gui.SetForegroundWindow(self.previous_window)
            except Exception as e:
                print(f"Не удалось вернуть фокус: {e}")
            self.opened_by_hotkey = False
        return "break"
    
    def _on_escape(self, event):
        prev = self.previous_window
        self.opened_by_hotkey = False
        self.root.withdraw()
        if prev:
            try:
                win32gui.SetForegroundWindow(prev)
            except Exception as e:
                print(f"Не удалось вернуть фокус по Escape: {e}")
        return "break"
    
    def _speak(self):
        if self.is_playing:
            return
        
        text = self.text_entry.get("1.0", tk.END).strip()
        if not text:
            return
        
        device_id = self._get_selected_device_id()
        if device_id is None:
            messagebox.showwarning("Внимание", "Выберите аудиоустройство")
            return
        
        lang_display = self.language_var.get()
        lang_code = self.engine.get_language_code(lang_display)
        
        if not self.engine.is_loaded(lang_code):
            messagebox.showerror("Ошибка", f"Модель {lang_display} не загружена! Подождите...")
            return
        
        self.is_playing = True
        self.speak_btn.config(state=tk.DISABLED)
        self.text_entry.delete("1.0", tk.END)
        
        threading.Thread(target=self._synthesize_and_play,
                        args=(text, device_id, lang_display), daemon=True).start()
    
    def _synthesize_and_play(self, text, device_id, language_display):
        try:
            self.root.after(0, lambda: self.status_label.config(text="🔄 Генерация речи..."))
            
            lang_code = self.engine.get_language_code(language_display)
            
            # Обрабатываем текст в зависимости от языка
            if lang_code == "ru":
                text_processed = number_to_words(text)
                text_processed = add_emotion_tags(
                    text_processed,
                    self.replacements,
                    language="ru"
                )
            else:
                # Для других языков — только замены из файла + точка
                text_processed = add_emotion_tags(
                    text,
                    self.replacements_en if lang_code == "en" else None,
                    language=lang_code
                )
            
            audio = self.engine.synthesize(
                text_processed,
                speaker=self.engine.current_speaker,
                language_display=language_display
            )
            
            self.root.after(0, lambda: self.status_label.config(text="🔊 Воспроизведение..."))
            
            monitor_enabled = self.monitor_enabled_var.get()
            
            if monitor_enabled:
                monitor_device_id = self._get_monitor_device_id()
                monitor_volume = self.monitor_volume_var.get() / 100.0
                monitor_audio = audio * monitor_volume
                
                def play_main():
                    sd.play(audio, samplerate=self.engine.sample_rate, device=device_id)
                    sd.wait()
                
                def play_monitor():
                    sd.play(monitor_audio, samplerate=self.engine.sample_rate, device=monitor_device_id)
                    sd.wait()
                
                t1 = threading.Thread(target=play_main, daemon=True)
                t2 = threading.Thread(target=play_monitor, daemon=True)
                t1.start()
                t2.start()
                t1.join()
                t2.join()
            else:
                sd.play(audio, samplerate=self.engine.sample_rate, device=device_id)
                sd.wait()
            
            self.root.after(0, lambda: self.status_label.config(text="✓ Готово", foreground='#66bb6a'))
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Ошибка", msg))
            self.root.after(0, lambda msg=error_msg: self.status_label.config(
                text=f"Ошибка: {msg[:30]}...", foreground='red'))
        finally:
            self.is_playing = False
            self.root.after(0, lambda: self.speak_btn.config(state=tk.NORMAL))
    
    def _stop(self):
        sd.stop()
        self.is_playing = False
        self.speak_btn.config(state=tk.NORMAL)
        self.status_label.config(text="⏹ Остановлено", foreground='yellow')
    
    def _on_closing(self):
        self._save_settings()
        try:
            keyboard.unhook_all_hotkeys()
        except:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = TTS_App(root)
    root.mainloop()
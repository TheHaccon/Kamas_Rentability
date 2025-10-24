# -*- coding: utf-8 -*-
import re
import sys
import time
import unicodedata
import pyperclip
import tkinter as tk
from tkinter import ttk

# --- Optional deps ---
try:
    from PIL import ImageGrab, ImageTk
except Exception:
    raise SystemExit("Pillow is required: pip install pillow")

try:
    import pytesseract
    HAS_TESS = True
except Exception:
    HAS_TESS = False

try:
    import keyboard
    HAS_KEYBOARD = True
except Exception:
    HAS_KEYBOARD = False

TESSERACT_CMD = None
if HAS_TESS and TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# ================== App State / Settings ==================
history = []
items = []

# capture box sizes
RECT_W = 120
RECT_H = 30
MIN_W, MIN_H = 100, 30
PREVIEW_SIZE = 220

# debounce
is_snipping = False
last_trigger_ts = 0.0
DEBOUNCE_SEC = 0.6

# running capture numbers (cumulative)
captured_values = []  # list[int]

# ================== Calculator UI =======================
class ItemFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent, width=150, height=150)
        self.frame.pack(side="left", padx=5, pady=5)

        self.item_name_var = tk.StringVar()
        tk.Label(self.frame, text="Item Name:").pack()
        tk.Entry(self.frame, textvariable=self.item_name_var, width=10).pack()

        self.prix_payer_var = tk.StringVar()
        tk.Label(self.frame, text="Prix Payé:").pack()
        tk.Entry(self.frame, textvariable=self.prix_payer_var, width=10).pack()

        self.prix_brise_var = tk.StringVar()
        tk.Label(self.frame, text="Prix Brisé:").pack()
        tk.Entry(self.frame, textvariable=self.prix_brise_var, width=10).pack()

        self.profit_label = tk.Label(self.frame, text="Profit %: ")
        self.profit_label.pack()
        self.result_label = tk.Label(self.frame, text="Profitability: ")
        self.result_label.pack()

        tk.Button(self.frame, text="Calculate", command=self.calculate_profit).pack(pady=5)
        tk.Button(self.frame, text="Refresh", command=self.update_total).pack(pady=5)
        tk.Button(self.frame, text="Cancel", command=self.remove_item).pack(pady=5)

        self.frame.after(100, self.update_total)

    def calculate_profit(self):
        try:
            item_name = self.item_name_var.get()
            prix_payer = int(self.prix_payer_var.get())
            prix_brise = int(self.prix_brise_var.get())

            if prix_payer == 0:
                self.profit_label.config(text="Profit %: N/A")
                self.result_label.config(text="Profitability: Invalid")
                return

            profit_percentage = ((prix_brise - prix_payer) / prix_payer) * 100
            self.profit_label.config(text=f"Profit %: {profit_percentage:.2f}%")

            if profit_percentage > 0:
                self.result_label.config(text="Profitable ✅", fg="green")
                history.append(f"{item_name}: {profit_percentage:.2f}% ✅")
            else:
                self.result_label.config(text="Not Profitable ❌", fg="red")
                history.append(f"{item_name}: {profit_percentage:.2f}% ❌")

            update_history()
        except ValueError:
            self.profit_label.config(text="Profit %: Invalid Input")
            self.result_label.config(text="Profitability: Error")

    def update_total(self):
        total = extract_kamas()
        if total > 0:
            self.prix_payer_var.set(total)

    def remove_item(self):
        self.frame.destroy()
        try:
            items.remove(self)
        except ValueError:
            pass

def extract_kamas():
    data = pyperclip.paste()
    total = 0
    for line in data.splitlines():
        matches = re.findall(r'(\d[\d\xa0 ]*) kamas', line)
        for match in matches:
            nombre = match.replace('\xa0', '').replace(' ', '')
            try:
                total += int(nombre)
            except ValueError:
                pass
    return total

def update_history():
    history_text.set("\n".join(history[-10:]))

def add_item():
    item = ItemFrame(items_frame)
    items.append(item)

def on_exit():
    try:
        if HAS_KEYBOARD:
            keyboard.unhook_all_hotkeys()
    except Exception:
        pass
    root.destroy()
    sys.exit(0)

# ================== Follow-the-Mouse OCR =======================
class FollowSnipOverlay(tk.Toplevel):
    def __init__(self, master, on_text_ready):
        super().__init__(master)
        self.on_text_ready = on_text_ready
        self.cur_w, self.cur_h = RECT_W, RECT_H

        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.state("zoomed")
        except Exception:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.config(bg="black")
        self.attributes("-alpha", 0.20)

        self.canvas = tk.Canvas(self, cursor="cross", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.preview = tk.Toplevel(self)
        self.preview.overrideredirect(True)
        self.preview.attributes("-topmost", True)
        self.preview_label = tk.Label(self.preview, bg="black")
        self.preview_label.pack()
        self._pimg = None

        self.bind("<Motion>", self.on_mouse_move)
        self.bind("<Button-1>", self.on_click_capture)
        self.bind("<Button-3>", lambda e: self.close_overlay())
        self.bind("<Escape>", lambda e: self.close_overlay())
        self.bind("<MouseWheel>", self.on_wheel)

        self.bind("<Destroy>", lambda e: release_snip_flag())

        self.deiconify()
        self.grab_set()
        self.update_frame()

    def screen_bbox_centered_at(self, cx, cy):
        half_w, half_h = self.cur_w // 2, self.cur_h // 2
        left = max(0, cx - half_w)
        top = max(0, cy - half_h)
        right = min(self.winfo_screenwidth(), cx + half_w)
        bottom = min(self.winfo_screenheight(), cy + half_h)
        return (left, top, right, bottom)

    def update_frame(self):
        x = self.winfo_pointerx()
        y = self.winfo_pointery()
        left, top, right, bottom = self.screen_bbox_centered_at(x, y)
        self.canvas.delete("rect")
        self.canvas.create_rectangle(left, top, right, bottom, outline="white", width=2, tags="rect")

        try:
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
            img.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE))
            self._pimg = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self._pimg)
            self.preview.geometry(f"+{x + 24}+{y + 24}")
        except Exception:
            pass

    def on_mouse_move(self, event):
        self.update_frame()

    def on_wheel(self, event):
        step = 10 if event.delta > 0 else -10
        self.cur_w = max(MIN_W, self.cur_w + step)
        self.cur_h = max(MIN_H, self.cur_h + step)
        self.update_frame()

    def on_click_capture(self, event):
        x = self.winfo_pointerx()
        y = self.winfo_pointery()
        left, top, right, bottom = self.screen_bbox_centered_at(x, y)
        self.withdraw()
        self.update_idletasks()

        img = ImageGrab.grab(bbox=(left, top, right, bottom))
        if HAS_TESS:
            try:
                text = pytesseract.image_to_string(img)
            except Exception as e:
                text = f"[OCR error] {e}"
        else:
            text = "[OCR not available]"
        self.on_text_ready((text or "").strip())
        self.close_overlay()

    def close_overlay(self):
        try:
            self.preview.destroy()
        except Exception:
            pass
        self.destroy()

# ================== OCR Parsing & Cumulative Display =======================
def release_snip_flag():
    global is_snipping
    is_snipping = False

def clean_and_split_numbers(text):
    """
    Normalise OCR, fusionne les espaces entre chiffres (ex: '16 000' -> '16000'),
    supprime les symboles, puis extrait les entiers.
    """
    cleaned_lines = []
    for line in (text or "").splitlines():
        # normalize unicode
        line = unicodedata.normalize("NFKC", line)
        # unify special spaces
        line = line.replace("\u00A0", " ").replace("\u202F", " ")
        # collapse ANY space sitting BETWEEN digits -> treat as thousands sep
        line = re.sub(r'(?<=\d)[\s\u00A0\u202F]+(?=\d)', '', line)
        # remove everything that isn't a digit or whitespace (leftover symbols)
        line = re.sub(r"[^0-9\s]", " ", line)
        # shrink extra spaces
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            cleaned_lines.append(line)

    cleaned_text = " ".join(cleaned_lines)  # now has groups like "16000 2500"
    nums = re.findall(r"\d+", cleaned_text)
    return [int(n) for n in nums] if nums else []

def refresh_numbers_view():
    """Update the listbox and the total label from captured_values."""
    numbers_listbox.delete(0, tk.END)
    for idx, n in enumerate(captured_values, 1):
        numbers_listbox.insert(tk.END, f"{idx}. {n}")
    sum_text_var.set(str(sum(captured_values) if captured_values else 0))
    extracted_text_var.set(" ".join(map(str, captured_values)) if captured_values else "(aucun)")

def on_snip_text_once(text):
    """After each capture, add ALL found numbers to the cumulative list + update sum + copy last capture digits."""
    global is_snipping
    nums = clean_and_split_numbers(text)

    try:
        pyperclip.copy(" ".join(map(str, nums)))
    except Exception:
        pass

    if nums:
        captured_values.extend(nums)
        refresh_numbers_view()
    is_snipping = False

def start_snip(event=None):
    global is_snipping, last_trigger_ts
    now = time.time()
    if is_snipping or (now - last_trigger_ts) < DEBOUNCE_SEC:
        return
    is_snipping = True
    last_trigger_ts = now
    try:
        notebook.select(other_tab)
    except Exception:
        pass
    FollowSnipOverlay(root, on_text_ready=on_snip_text_once)

# ================== UI Setup =======================
root = tk.Tk()
root.title("Kamas Rentabilité")
root.geometry("1100x760")

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

# --- Calculator ---
calculator_tab = tk.Frame(notebook)
notebook.add(calculator_tab, text="Calculator")

top_bar = tk.Frame(calculator_tab)
top_bar.pack(fill="x", pady=5)
tk.Button(top_bar, text="Add Item", command=add_item).pack(side="left", padx=5)
tk.Button(top_bar, text="Exit", command=on_exit).pack(side="right", padx=5)

content_area = tk.Frame(calculator_tab)
content_area.pack(fill="both", expand=True)
items_frame = tk.Frame(content_area)
items_frame.pack(fill="both", expand=True, side="left")

history_panel = tk.Frame(content_area)
history_panel.pack(fill="y", side="right", padx=10)
tk.Label(history_panel, text="History:", font=("Arial", 12)).pack(anchor="w")
history_text = tk.StringVar()
tk.Label(history_panel, textvariable=history_text, font=("Arial", 10), justify="left").pack(anchor="w")

# --- OCR  (cumulative + editable) ---
other_tab = tk.Frame(notebook)
notebook.add(other_tab, text="Price Check")

tk.Label(
    other_tab,
    text=("Ctrl + Numpad 9 → capture;"),
    font=("Arial", 11)
).pack(pady=8)

# list + edit area
list_frame = tk.Frame(other_tab)
list_frame.pack(fill="both", expand=False, padx=10, pady=(0,8))

left_col = tk.Frame(list_frame)
left_col.pack(side="left", fill="y")

tk.Label(left_col, text="Nombres :", font=("Arial", 11)).pack(anchor="w")
numbers_listbox = tk.Listbox(left_col, height=12, width=34)
numbers_listbox.pack(side="left", padx=(0,8))
scroll = tk.Scrollbar(left_col, command=numbers_listbox.yview)
scroll.pack(side="left", fill="y")
numbers_listbox.config(yscrollcommand=scroll.set)

def on_listbox_double_click(event=None):
    sel = numbers_listbox.curselection()
    if not sel:
        return
    idx = sel[0]
    edit_var.set(str(captured_values[idx]))

numbers_listbox.bind("<Double-Button-1>", on_listbox_double_click)

right_col = tk.Frame(list_frame)
right_col.pack(side="left", fill="both", expand=True)

tk.Label(right_col, text="Aperçu compact :", font=("Arial", 10)).pack(anchor="w")
extracted_text_var = tk.StringVar(value="(aucun)")
tk.Label(right_col, textvariable=extracted_text_var, wraplength=700, justify="left").pack(anchor="w", pady=(2,6))

# editor
edit_row = tk.Frame(right_col)
edit_row.pack(anchor="w", pady=(0,6))
tk.Label(edit_row, text="Éditer / Ajouter :", font=("Arial", 10)).pack(side="left")
edit_var = tk.StringVar()
edit_entry = tk.Entry(edit_row, textvariable=edit_var, width=16)
edit_entry.pack(side="left", padx=6)

def parse_int_from_entry():
    s = edit_var.get().strip()
    if not s:
        return None
    # normalize + collapse thousands separators inside entry, just like OCR
    s = unicodedata.normalize("NFKC", s).replace("\u00A0", " ").replace("\u202F", " ")
    s = re.sub(r'(?<=\d)[\s\u00A0\u202F]+(?=\d)', '', s)  # collapse digit-space-digit
    s = re.sub(r'[^0-9]', '', s)  # keep digits only
    return int(s) if s.isdigit() else None

def edit_selected():
    sel = numbers_listbox.curselection()
    if not sel:
        return
    n = parse_int_from_entry()
    if n is None:
        return
    idx = sel[0]
    captured_values[idx] = n
    refresh_numbers_view()

def remove_selected():
    sel = numbers_listbox.curselection()
    if not sel:
        return
    idx = sel[0]
    del captured_values[idx]
    refresh_numbers_view()

def add_manual():
    n = parse_int_from_entry()
    if n is None:
        return
    captured_values.append(n)
    refresh_numbers_view()
    edit_var.set("")

btn_bar = tk.Frame(right_col)
btn_bar.pack(anchor="w")
tk.Button(btn_bar, text="Modifier sélection", command=edit_selected).pack(side="left", padx=4)
tk.Button(btn_bar, text="Supprimer sélection", command=remove_selected).pack(side="left", padx=4)
tk.Button(btn_bar, text="Ajouter", command=add_manual).pack(side="left", padx=4)

# sum row
row_sum = tk.Frame(other_tab)
row_sum.pack(fill="x", padx=10, pady=(6, 10))
tk.Label(row_sum, text="Somme cumulée :", font=("Arial", 12, "bold")).pack(side="left")
sum_text_var = tk.StringVar(value="0")
tk.Label(row_sum, textvariable=sum_text_var, font=("Arial", 12)).pack(side="left", padx=8)

# buttons
btns = tk.Frame(other_tab)
btns.pack(pady=6)
tk.Button(btns, text="manuel OCR", command=start_snip).pack(side="left", padx=6)

def clear_ocr():
    captured_values.clear()
    refresh_numbers_view()
    try:
        pyperclip.copy("")
    except Exception:
        pass

tk.Button(btns, text="Clear", command=clear_ocr).pack(side="left", padx=6)

# ================== Hotkeys =======================
def register_hotkeys():
    if HAS_KEYBOARD:
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        ok = False
        try:
            keyboard.add_hotkey("ctrl+numpad 9", lambda: root.after(0, start_snip)); ok = True
        except Exception:
            pass
        try:
            keyboard.add_hotkey("ctrl+page up", lambda: root.after(0, start_snip)); ok = True
        except Exception:
            pass
        if ok:
            print("[hotkeys] Global Ctrl+Num9 / Ctrl+PageUp active.")
            return
    # fallback local
    root.bind_all("<Control-KeyPress-KP_9>", start_snip)
    root.bind_all("<Control-KeyPress-Prior>", start_snip)
    print("[hotkeys] Local (focus) Ctrl+Num9 active.")

# init
root.after(0, lambda: edit_entry.focus_set())
history_text = tk.StringVar()
def refresh_numbers_view_init_safe():
    # in case first paint happens before vars are defined
    try:
        refresh_numbers_view()
    except Exception:
        pass

refresh_numbers_view_init_safe()
update_history()
register_hotkeys()
root.mainloop()

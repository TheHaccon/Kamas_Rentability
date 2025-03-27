import pyperclip
import re
import tkinter as tk

# Store previous calculations
history = []
items = []

class ItemFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent,width=150,height=150)
        self.frame.pack(side="left", padx=5, pady=5)

        self.item_name_var = tk.StringVar()
        tk.Label(self.frame, text="Item Name:").pack()
        self.item_name_entry = tk.Entry(self.frame, textvariable=self.item_name_var, width=10)
        self.item_name_entry.pack()

        self.prix_payer_var = tk.StringVar()
        tk.Label(self.frame, text="Prix Payé:").pack()
        self.prix_payer_entry = tk.Entry(self.frame, textvariable=self.prix_payer_var, width=10)
        self.prix_payer_entry.pack()

        self.prix_brise_var = tk.StringVar()
        tk.Label(self.frame, text="Prix Brisé:").pack()
        self.prix_brise_entry = tk.Entry(self.frame, textvariable=self.prix_brise_var, width=10)
        self.prix_brise_entry.pack()

        self.profit_label = tk.Label(self.frame, text="Profit %: ")
        self.profit_label.pack()

        self.result_label = tk.Label(self.frame, text="Profitability: ")
        self.result_label.pack()

        self.calculate_button = tk.Button(self.frame, text="Calculate", command=self.calculate_profit)
        self.calculate_button.pack(pady=5)

        self.refresh_button = tk.Button(self.frame, text="Refresh", command=self.update_total)
        self.refresh_button.pack(pady=5)

        self.cancel_button = tk.Button(self.frame, text="Cancel", command=self.remove_item)
        self.cancel_button.pack(pady=5)

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
        items.remove(self)

def extract_kamas():
    data = pyperclip.paste()
    splited_data = data.splitlines()
    total = 0

    for i in splited_data:
        matches = re.findall(r'(\d[\d\xa0 ]*) kamas', i) 
        for match in matches:
            nombre = match.replace('\xa0', '').replace(' ', '')
            try:
                total += int(nombre)
            except ValueError:
                print(f"Skipping invalid number: {nombre}")

    return total

def update_history():
    history_text.set("\n".join(history[-10:])) 

def add_item():
    item = ItemFrame(items_frame)
    items.append(item)

def on_exit():
    root.destroy()

# GUI Setup
root = tk.Tk()
root.title("Kamas Rentabilité")
root.geometry("800x400")

add_item_button = tk.Button(root, text="Add Item", command=add_item)
add_item_button.pack(pady=5)

items_frame = tk.Frame(root)
items_frame.pack(fill="both", expand=True, side="left")

history_label = tk.Label(root, text="History:", font=("Arial", 12))
history_label.pack()

history_text = tk.StringVar()
history_display = tk.Label(root, textvariable=history_text, font=("Arial", 10))
history_display.pack()

exit_button = tk.Button(root, text="Exit", command=on_exit)
exit_button.pack(pady=5)

update_history()
root.mainloop()

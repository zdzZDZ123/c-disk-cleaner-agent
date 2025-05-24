import tkinter as tk
from tkinter import ttk

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("C Disk Cleaner Agent")
        self.geometry("800x600")

        # Placeholder for main content
        label = ttk.Label(self, text="Welcome to C Disk Cleaner Agent UI!")
        label.pack(pady=20, padx=20)

if __name__ == "__main__":
    app = App()
    app.mainloop()
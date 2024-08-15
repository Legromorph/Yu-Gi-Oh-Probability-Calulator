import tkinter as tk
from gui import YugiohProbabilityCalculatorGUI

def main():
    root = tk.Tk()
    app = YugiohProbabilityCalculatorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
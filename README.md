<p align="center">
<img src="https://i.nuuls.com/hWIoU.png">
</p>

## About
Educational digital logic simulator.

Achieves fast simulation using LLVM JIT.

Thanks to Logisim for inspiration.

## Dependencies
- Python 3
- PySide 2
- bidict
- llvmlite (optional)

I recommend using Python 3.8 for now, because llvmlite
wheels for 3.9 aren't available yet.

If llvmlite cannot be imported, the simulator will
use the custom interpreter (which is very slow).

## Running
1. install dependencies: `pip install -r requirements.txt`
2. run: `python main.py`

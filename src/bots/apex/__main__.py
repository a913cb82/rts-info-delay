"""python -m bots.apex"""
from .protocol import *
from .brain import decide_orders

if __name__ == "__main__":
    bot_main(decide_orders)

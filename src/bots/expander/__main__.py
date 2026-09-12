"""python -m bots.expander"""
from .core import bot_main
from .brain import decide_orders

if __name__ == "__main__":
    bot_main(decide_orders)
